"""QarzQutqaruv API + website.

Model 1 (risk, LightGBM on public UCI data) -> Model 2 (next best action) ->
officer decision -> hash-chained audit log -> outcomes teach Model 2.
"""
import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import audit, nba
from app.actions import annuity, ladder, offer_letter
from app.counterfactual import path_to_green
from app.reasons import own_norm_facts
from app.schemas import DecisionRequest, OutcomeRequest, ScoreRequest
from app.scoring import ScoringEngine

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).parent / "static"
POST_LIMIT_PER_MIN = 60
CAL = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
       "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]

engine = ScoringEngine()
PORTFOLIO = {}
_hits = defaultdict(deque)


@asynccontextmanager
async def lifespan(_app):
    load_portfolio()
    yield


app = FastAPI(title="QarzQutqaruv API", version="1.0", lifespan=lifespan)


@app.middleware("http")
async def guard(request: Request, call_next):
    """Rate-limit POSTs per client IP (behind a proxy the first X-Forwarded-For entry)."""
    if request.method == "POST":
        ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
        now, q = time.time(), _hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= POST_LIMIT_PER_MIN:
            return JSONResponse({"detail": "Too many requests, try again in a minute"}, status_code=429)
        q.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _apply(b, s):
    b.update(prob=s["prob"], features=s["features"], contrib=s["contrib"],
             band=engine.band(s["prob"], b.get("segment", "micro_business")))
    b["money_at_risk"] = b["prob"] * b["outstanding"]
    return b


def _score(b):
    return _apply(b, engine.score_history(b["history"]))


def load_portfolio():
    """Score the whole demo portfolio in one batch (2 model calls instead of 1,000)."""
    PORTFOLIO.clear()
    borrowers = json.loads((ROOT / "data" / "demo_portfolio.json").read_text(encoding="utf-8"))
    scores = engine.score_many([engine.history_features(b["history"]) for b in borrowers])
    for b, s in zip(borrowers, scores):
        PORTFOLIO[b["id"]] = _apply(b, s)


def card(b, lang="en"):
    """Everything the officer sees for one borrower."""
    remaining = b["term_months"] - b["months_elapsed"]
    inst = b.get("installment") or int(annuity(b["outstanding"], b["annual_rate"], remaining))
    reasons = engine.reasons(b["features"], b["contrib"], lang)
    rec = nba.recommend(b, b["band"], b["prob"], b["features"])
    acts = ladder(b["band"], b["outstanding"], b["annual_rate"], remaining, inst, b["business_type"], b.get("turnover"))
    plan = next((a.get("plan") for a in acts if a["code"] == "rescue_plan"), None)
    ptg = path_to_green(engine, b["history"], inst, b.get("segment", "micro_business"), b["prob"], lang) \
        if b["band"] != "green" else None
    keep = ("id", "name", "region", "business_type", "segment", "loan_amount", "annual_rate", "term_months",
            "months_elapsed", "outstanding", "installment", "client_since_months", "prior_loans_repaid",
            "has_guarantor", "has_app", "assigned_officer", "last_app_login_days", "calendar_months", "history",
            "turnover", "card_txn_count", "app_logins")
    return {**{k: b.get(k) for k in keep}, "installment": inst,
            "prob": round(b["prob"], 4), "band": b["band"], "money_at_risk": int(b["money_at_risk"]),
            "thresholds": engine.thresholds(b.get("segment", "micro_business")),
            "reasons": reasons, "early_signals": nba.early_signals(b), "path_to_green": ptg,
            "own_norm_facts": own_norm_facts(b["features"], lang, skip={r["feature"] for r in reasons}),
            "next_best_action": rec, "actions": acts,
            "letter": offer_letter(b["name"], plan, b.get("assigned_officer"), lang),
            "model_version": engine.version, "synthetic": b["id"].startswith("DEMO")}


@app.get("/api/health")
def health():
    return {"status": "ok", "model_version": engine.version, "borrowers": len(PORTFOLIO)}


@app.get("/api/portfolio")
def portfolio(lang: str = "en", sort: str = "risk", band: str = "all"):
    key = "money_at_risk" if sort == "money" else "prob"
    rows = sorted(PORTFOLIO.values(), key=lambda b: -b[key])
    summary = {"red": 0, "yellow": 0, "green": 0, "money_at_risk": 0, "outstanding": 0}
    out = []
    for b in rows:
        summary[b["band"]] += 1
        summary["money_at_risk"] += int(b["money_at_risk"])
        summary["outstanding"] += int(b["outstanding"])
        if band != "all" and b["band"] != band:
            continue
        top = engine.reasons(b["features"], b["contrib"], lang, k=1)[0]["text"]
        out.append({"id": b["id"], "name": b["name"], "region": b["region"], "business_type": b["business_type"],
                    "segment": b["segment"], "prob": round(b["prob"], 4), "band": b["band"],
                    "money_at_risk": int(b["money_at_risk"]), "top_reason": top})
    return {"summary": summary, "borrowers": out}


@app.get("/api/borrower/{borrower_id}")
def borrower(borrower_id: str, lang: str = "en"):
    b = PORTFOLIO.get(borrower_id)
    if not b:
        raise HTTPException(404, "Borrower not found")
    return card(b, lang)


@app.post("/api/score")
def score(req: ScoreRequest):
    t = time.perf_counter()
    b = {"id": "JURY", "name": req.name, "region": "-", "business_type": req.business_type,
         "segment": req.segment, "loan_amount": None, "annual_rate": req.annual_rate,
         "term_months": req.term_months, "months_elapsed": req.months_elapsed, "outstanding": req.outstanding,
         "installment": req.installment, "history": [h.model_dump() for h in req.history],
         "calendar_months": CAL[-len(req.history):],
         "turnover": req.turnover, "has_app": req.has_app, "last_app_login_days": 0 if req.has_app else 99,
         "has_guarantor": req.has_guarantor, "prior_loans_repaid": req.prior_loans_repaid,
         "assigned_officer": "your officer", "client_since_months": None}
    _score(b)
    result = card(b, req.lang)
    result["latency_ms"] = round((time.perf_counter() - t) * 1000, 1)
    audit.log_event("SCORE", "jury/web", "JURY", {"input": req.model_dump(), "prob": result["prob"],
                    "band": result["band"]}, engine.version)
    return result


@app.post("/api/decision")
def decision(req: DecisionRequest):
    b = PORTFOLIO.get(req.borrower_id)
    payload = req.model_dump()
    if b:
        payload.update(prob=round(b["prob"], 4), band=b["band"])
    return audit.log_event("DECISION", req.officer, req.borrower_id, payload, engine.version)


@app.post("/api/outcome")
def outcome(req: OutcomeRequest):
    b = PORTFOLIO.get(req.borrower_id)
    if not b:
        raise HTTPException(404, "Borrower not found")
    if req.action_code not in nba.CATALOG:
        raise HTTPException(422, "Unknown action")
    ptype = nba.problem_type(b["features"])
    audit.add_outcome(ptype, req.action_code, req.resolved)
    rec = audit.log_event("OUTCOME", "officer", req.borrower_id,
                          {"action": req.action_code, "resolved": req.resolved, "problem_type": ptype}, engine.version)
    post = nba.posterior(ptype, req.action_code)
    return {"logged": rec, "problem_type": ptype, "p_resolve_now": round(post[0] / (post[0] + post[1]), 3),
            "n_local": post[2]}


@app.get("/api/daily-plan")
def daily_plan(minutes: int = 240, pilot: bool = False, limit: int = 30):
    minutes = max(0, min(minutes, 5000))
    plan = nba.daily_plan(PORTFOLIO.values(), minutes, pilot, seed=7 if pilot else None)
    plan["rows"] = plan["rows"][:max(1, min(limit, 500))]
    return plan


@app.get("/api/nba/knowledge")
def nba_knowledge():
    return nba.knowledge()


@app.get("/api/audit")
def audit_log(limit: int = 50):
    return audit.recent(max(1, min(limit, 200)))


@app.get("/api/audit/verify")
def audit_verify():
    return audit.verify()


@app.get("/api/model-card")
def model_card():
    art = ROOT / "model" / "artifacts"
    return {"metrics": json.loads((art / "metrics.json").read_text(encoding="utf-8")),
            "meta": json.loads((art / "meta.json").read_text(encoding="utf-8")),
            "policy": engine.policy}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
