import time
import json
import os
import math
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas import ScoreRequest, DecisionRequest
from app.scoring import ScoringEngine
from app.actions import generate_actions
from app.audit import log_event, verify, get_recent_logs

app = FastAPI(title="QarzQutqaruv API")

# --- Лимит запросов (Rate Limiter) ---
ip_records = defaultdict(list)
RATE_LIMIT = 30 # максимум 30 POST-запросов в минуту

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "POST":
            client_ip = request.client.host
            now = time.time()
            ip_records[client_ip] = [ts for ts in ip_records[client_ip] if now - ts < 60]
            if len(ip_records[client_ip]) >= RATE_LIMIT:
                return JSONResponse(status_code=429, content={"detail": "Too many requests"})
            ip_records[client_ip].append(now)
        
        start_time = time.time()
        response = await call_next(request)
        process_time = int((time.time() - start_time) * 1000)
        response.headers["X-Process-Time-ms"] = str(process_time)
        return response

app.add_middleware(RateLimitMiddleware)

# --- Инициализация в памяти ---
engine = ScoringEngine()
portfolio_data = []

def calc_delay_months(days_late: int) -> int:
    return min(9, math.ceil(days_late / 30))

@app.on_event("startup")
def load_portfolio():
    global portfolio_data
    with open("data/demo_portfolio.json", "r", encoding="utf-8") as f:
        raw_portfolio = json.load(f)
    
    # Предрасчет всех 500 заемщиков при старте сервера
    for b in raw_portfolio:
        use_len = min(len(b["history"]), 6)
        hist = b["history"][-use_len:]
        
        due = [h["due"] for h in hist]
        paid = [h["paid"] for h in hist]
        delay = [calc_delay_months(h["days_late"]) for h in hist]
        
        res = engine.score(due, paid, delay, lang="en", outstanding=b["outstanding"])
        b["prob"] = res["probability"]
        b["band"] = res["band"]
        b["money_at_risk"] = res["money_at_risk"]
        b["reasons"] = res["reasons"]
        b["features"] = res["features"]
        
        rem_months = b["term_months"] - b["months_elapsed"]
        b["actions"] = generate_actions(b["band"], b["outstanding"], b["annual_rate"], rem_months, b.get("turnover"))
        portfolio_data.append(b)

# --- API Эндпоинты ---
@app.get("/api/health")
def health():
    return {"status": "ok", "model_version": engine.meta["model_version"]}

@app.get("/api/portfolio")
def get_portfolio(lang: str = "en", sort: str = "risk"):
    if sort == "money":
        sorted_data = sorted(portfolio_data, key=lambda x: x["money_at_risk"], reverse=True)
    else:
        sorted_data = sorted(portfolio_data, key=lambda x: x["prob"], reverse=True)
        
    summary = {"red": 0, "yellow": 0, "green": 0, "total_money_at_risk": 0.0}
    list_data = []
    
    for b in sorted_data:
        summary[b["band"]] += 1
        summary["total_money_at_risk"] += b["money_at_risk"]
        top_reason = b["reasons"][0]["text"] if b.get("reasons") else ""
        list_data.append({
            "id": b["id"], "name": b["name"], "region": b["region"],
            "business_type": b["business_type"], "prob": b["prob"],
            "band": b["band"], "money_at_risk": b["money_at_risk"],
            "top_reason": top_reason
        })
        
    return {"summary": summary, "borrowers": list_data}

@app.get("/api/borrower/{borrower_id}")
def get_borrower(borrower_id: str, lang: str = "en"):
    for b in portfolio_data:
        if b["id"] == borrower_id:
            return b
    raise HTTPException(status_code=404, detail="Borrower not found")

@app.post("/api/score")
def score_borrower(req: ScoreRequest):
    start_t = time.time()
    due = [h.due for h in req.history]
    paid = [h.paid for h in req.history]
    delay = [calc_delay_months(h.days_late) for h in req.history]
    
    res = engine.score(due, paid, delay, lang=req.lang, outstanding=req.outstanding)
    rem_months = req.term_months - req.months_elapsed
    res["actions"] = generate_actions(res["band"], req.outstanding, req.annual_rate, rem_months, req.turnover)
    
    # Записываем событие оценки в аудит-журнал
    payload = req.model_dump()
    payload.update({"prob": res["probability"], "band": res["band"], "reasons": res["reasons"]})
    log_event("SCORE", "API", "EXTERNAL", payload, engine.meta["model_version"])
    
    res["latency_ms"] = int((time.time() - start_t) * 1000)
    return res

@app.post("/api/decision")
def record_decision(req: DecisionRequest):
    return log_event("DECISION", req.officer, req.borrower_id, req.model_dump(), engine.meta["model_version"])

@app.get("/api/audit")
def get_audit(limit: int = 50):
    return get_recent_logs(limit)

@app.get("/api/audit/verify")
def verify_audit():
    return verify()

@app.get("/api/model-card")
def get_model_card():
    with open("model/artifacts/metrics.json", "r") as f:
        metrics = json.load(f)
    with open("model/artifacts/meta.json", "r") as f:
        meta = json.load(f)
    return {"metrics": metrics, "meta": meta}

# --- Статика (Сайт) ---
os.makedirs("app/static", exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def read_index():
    try:
        with open("app/static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<html><body><h1>Site is building... (Proceed to Step 12)</h1></body></html>"

app.mount("/static", StaticFiles(directory="app/static"), name="static")