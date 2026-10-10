"""Model 2: next best action.

Model 1 says WHO is at risk and WHY. Model 2 decides WHAT to do for each
borrower: it estimates how much loss each allowed action prevents, minus its
cost, plans the officers' limited time, and learns from recorded outcomes
(Bayesian Beta model per problem type x action; Thompson sampling in pilot mode).
"""
import json
import random
from pathlib import Path

import numpy as np

from app import audit
from app.actions import LAST_MONTH_IDX, season

LGD = 0.45  # ASSUMPTION: Basel II foundation-IRB value for senior unsecured claims
PRIORS = json.loads((Path(__file__).parent / "action_priors.json").read_text(encoding="utf-8"))
CATALOG = PRIORS["catalog"]
TYPES = ("slipping", "cannot_pay", "silent")

PROBLEM_TEXT = {
    "cannot_pay": "Cannot pay: pays far below own norm -> the payment size is the problem",
    "silent": "Silent: stopped paying or deep delay -> needs personal contact",
    "slipping": "Slipping: small, recent drift -> a reminder is usually enough",
}


def problem_type(f):
    if f["paid_recent_vs_norm"] < 0.7 and f["cover_drop"] > 0.2:
        return "cannot_pay"
    if f["zero_pay_months"] >= 1 or f["delay_last"] >= 2:
        return "silent"
    return "slipping"


def prior_ab(ptype, action):
    w = PRIORS["prior_weight"]
    base = PRIORS["base"][ptype]
    if action == "none":
        mean = base
    else:
        lift = PRIORS["lifts_pp"][action][ptype]
        if lift is None:
            return None
        mean = base + lift / 100
    return mean * w, (1 - mean) * w


def posterior(ptype, action):
    ab = prior_ab(ptype, action)
    if ab is None:
        return None
    a, b = ab
    s, f = audit.outcome_counts().get((ptype, action), (0, 0))
    return a + s, b + f, s + f


def p_resolve(ptype, action, sample=False, rng=None):
    post = posterior(ptype, action)
    if post is None:
        return None
    a, b, _ = post
    return (rng or random).betavariate(a, b) if sample else a / (a + b)


def allowed(action, band, ptype, b):
    if band == "green":
        return False
    if PRIORS["lifts_pp"][action][ptype] is None:
        return False
    if action == "push" and not (b.get("has_app") and b.get("last_app_login_days", 99) <= 7):
        return False
    if action == "personal_sms" and not b.get("assigned_officer"):
        return False
    if action in ("guarantor_call", "visit") and band != "red":
        return False
    if action == "guarantor_call" and not b.get("has_guarantor"):
        return False
    if action == "restructure_offer" and not (band == "red" and ptype == "cannot_pay"):
        return False
    return True


def options(b, band, prob, features, sample=False, rng=None):
    ptype = problem_type(features)
    base = p_resolve(ptype, "none", sample, rng)
    ead = float(b.get("outstanding", 0))
    out = []
    for action, info in CATALOG.items():
        if not allowed(action, band, ptype, b):
            continue
        uplift = max(0.0, p_resolve(ptype, action, sample, rng) - base)
        # Share of borrowers who would NOT resolve on their own that the action converts,
        # applied to this borrower's default probability: saved = PD x conversion x EAD x LGD.
        conversion = uplift / (1 - base) if base < 1 else 0.0
        saved = prob * conversion * ead * LGD
        out.append({"action": action, "title": info["title"], "minutes": info["minutes"], "cost": info["cost"],
                    "uplift_pp": round(uplift * 100, 1), "conversion": round(conversion, 3), "expected_saved": int(saved),
                    "value": int(saved - info["cost"]), "source": PRIORS["lifts_pp"][action]["source"]})
    out.sort(key=lambda o: -o["value"])
    return ptype, out


def recommend(b, band, prob, features):
    if band == "green":
        return {"problem_type": None, "best": None, "options": [],
                "text": "Green zone: no action, keep monitoring."}
    ptype, opts = options(b, band, prob, features)
    best = opts[0] if opts else None
    note = None
    if best and best["action"] == "restructure_offer" and b.get("prior_loans_repaid", 0) >= 1:
        note = "Retain a proven client: already repaid a loan with us."
    return {"problem_type": ptype, "problem_text": PROBLEM_TEXT[ptype], "best": best, "options": opts, "note": note}


def daily_plan(portfolio, minutes=240, pilot=False, seed=None):
    """Greedy knapsack: officer minutes go where each minute saves the most money;
    everyone else at risk gets the best zero-minute action (SMS / push).
    Pilot mode: Thompson sampling + 10% control group (no action) to measure effects."""
    rng = random.Random(seed)
    candidates, rest, control = [], [], []
    for b in portfolio:
        if b["band"] == "green":
            continue
        if pilot and rng.random() < 0.10:
            control.append(b["id"])
            continue
        _, opts = options(b, b["band"], b["prob"], b["features"], sample=pilot, rng=rng)
        timed = [o for o in opts if o["minutes"] > 0 and o["value"] > 0]
        free = [o for o in opts if o["minutes"] == 0 and o["value"] > 0]
        if timed:
            candidates.append((b, timed[0], free[0] if free else None))
        elif free:
            rest.append((b, free[0]))
    candidates.sort(key=lambda c: -c[1]["value"] / c[1]["minutes"])
    plan, used = [], 0
    for b, opt, fallback in candidates:
        if used + opt["minutes"] <= minutes:
            used += opt["minutes"]
            plan.append((b, opt))
        elif fallback:
            rest.append((b, fallback))
    rows = [{"borrower_id": b["id"], "name": b["name"], "band": b["band"], "prob": round(b["prob"], 4),
             "problem_type": problem_type(b["features"]), "action": o["action"], "title": o["title"],
             "minutes": o["minutes"], "cost": o["cost"], "expected_saved": o["expected_saved"]}
            for b, o in plan + rest]
    counts = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    return {"minutes_budget": minutes, "minutes_used": used, "pilot_mode": pilot,
            "control_group": len(control), "counts": counts,
            "expected_saved_total": int(sum(r["expected_saved"] for r in rows)),
            "cost_total": int(sum(r["cost"] for r in rows)), "rows": rows}


def knowledge():
    rows = []
    for t in TYPES:
        for action in ["none"] + list(CATALOG):
            post = posterior(t, action)
            if post is None:
                continue
            a, b, n = post
            rows.append({"problem_type": t, "action": action, "p_resolve": round(a / (a + b), 3), "n_local": n,
                         "source": "base rate (ASSUMPTION)" if action == "none" else PRIORS["lifts_pp"][action]["source"]})
    return {"lgd": LGD, "excluded": PRIORS["excluded"], "cost_source": PRIORS["cost_source"], "rows": rows}


def early_signals(b):
    """Card and app behaviour are EARLY signals (rule-based in the demo, learned in the pilot)."""
    out = []
    s = season(b.get("business_type", "other"))

    def deseason(series):  # remove the usual seasonality so a normal low season is not an alarm
        n = len(series)
        return [v / s[(LAST_MONTH_IDX - (n - 1 - i)) % 12] for i, v in enumerate(series)]

    t = deseason(b.get("turnover") or [])
    cards = deseason(b.get("card_txn_count") or [])
    logins = b.get("app_logins") or []

    def drop(series):
        if len(series) < 6:
            return None
        old, new = np.mean(series[:-3]), np.mean(series[-3:])
        return None if old <= 0 else (new - old) / old

    d = drop(t)
    if d is not None and d < -0.30:
        out.append(f"Card / account turnover {int(d * 100)}% vs own norm")
    d = drop(cards)
    if d is not None and d < -0.30:
        out.append(f"Card transactions {int(d * 100)}% vs own norm")
    if b.get("has_app") and b.get("last_app_login_days", 0) > 21:
        out.append(f"App silence: no login for {b['last_app_login_days']} days")
    elif b.get("has_app"):
        d = drop(logins)
        if d is not None and d < -0.50:
            out.append(f"App logins {int(d * 100)}% vs own norm")
    return out
