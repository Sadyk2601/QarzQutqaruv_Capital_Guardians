import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AUDIT_DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test_audit.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import audit, nba  # noqa: E402
from app.actions import annuity, rescue_plan  # noqa: E402
from app.main import app  # noqa: E402
from model.features import make_features  # noqa: E402

client = TestClient(app)
client.__enter__()  # run startup (loads the demo portfolio)


def test_features_own_norm():
    stable = make_features([1000] * 6, [1000] * 6, [0] * 6)
    assert abs(stable["paid_last_vs_norm"] - 1) < 0.01 and abs(stable["cover_drop"]) < 0.01
    falling = make_features([1000] * 6, [1000, 1000, 1000, 1000, 500, 200], [0, 0, 0, 0, 1, 2])
    assert falling["paid_last_vs_norm"] < 0.6 and falling["decline_streak"] >= 2
    nothing_due = make_features([0] * 6, [0] * 6, [0] * 6)
    assert nothing_due["cover_mean"] == 1 and nothing_due["zero_pay_months"] == 0


def test_annuity_and_rescue_plan_is_bank_neutral():
    assert abs(annuity(1_000_000, 0.24, 12) - 1_000_000 * 0.02 / (1 - 1.02 ** -12)) < 1
    plan = rescue_plan(41_000_000, 0.22, 22, 6_500_000, "tailoring")
    assert plan["feasible"]
    assert abs(plan["pv_check"] - 41_000_000) <= 1
    assert plan["max_burden_after_pct"] <= 30.0
    # a borrower with plenty of income needs no extension at all
    assert rescue_plan(41_000_000, 0.22, 22, 50_000_000, "tailoring")["extension_months"] == 0
    # a borrower with almost no income has no affordable plan
    assert not rescue_plan(41_000_000, 0.22, 22, 500_000, "tailoring")["feasible"]


def test_audit_chain_detects_tampering():
    audit.log_event("SCORE", "test", "DEMO-001", {"x": 1}, "v1")
    audit.log_event("DECISION", "officer", "DEMO-001", {"a": "call"}, "v1")
    assert audit.verify()["ok"]
    conn = sqlite3.connect(audit.DB_PATH)
    first = conn.execute("SELECT MIN(id) FROM audit").fetchone()[0]
    conn.execute("UPDATE audit SET payload = '{\"x\": 999}' WHERE id = ?", (first,))
    conn.commit()
    conn.close()
    bad = audit.verify()
    assert not bad["ok"] and bad["first_bad_id"] == first


def test_model2_rules_and_learning():
    f = make_features([2_290_000] * 4 + [3_080_000, 4_170_000], [2_290_000] * 4 + [1_200_000, 920_000], [0, 0, 0, 0, 1, 2])
    assert nba.problem_type(f) == "cannot_pay"
    b = {"outstanding": 41_000_000, "has_app": True, "last_app_login_days": 19, "has_guarantor": True,
         "assigned_officer": "Kamola T."}
    _, opts_yellow = nba.options(b, "yellow", 0.4, f)
    assert all(o["action"] not in ("visit", "restructure_offer", "guarantor_call", "push") for o in opts_yellow)
    before = nba.p_resolve("slipping", "sms")
    for _ in range(10):
        audit.add_outcome("slipping", "sms", True)
    assert nba.p_resolve("slipping", "sms") > before


def test_api_endpoints():
    assert client.get("/api/health").json()["status"] == "ok"
    p = client.get("/api/portfolio").json()
    assert p["summary"]["red"] + p["summary"]["yellow"] + p["summary"]["green"] == 500
    card = client.get("/api/borrower/DEMO-001?lang=uz").json()
    assert card["band"] in ("red", "yellow") and card["reasons"]
    plan = client.get("/api/daily-plan?minutes=240").json()
    assert plan["minutes_used"] <= 240
    good = {"annual_rate": 0.22, "term_months": 36, "months_elapsed": 14, "outstanding": 41_000_000,
            "history": [{"due": 2_290_000, "paid": 2_290_000, "days_late": 0}] * 6}
    assert client.post("/api/score", json=good).status_code == 200
    assert client.post("/api/score", json={**good, "history": good["history"][:2]}).status_code == 422
    assert client.post("/api/score", json={**good, "outstanding": -5}).status_code == 422
    assert client.post("/api/score", json={**good, "lang": "fr"}).status_code == 422
    # mass assignment (workshop lesson): unknown fields are rejected, not silently applied
    assert client.post("/api/score", json={**good, "status": "approved"}).status_code == 422
    assert client.post("/api/decision", json={"borrower_id": "DEMO-001", "action_code": "call",
                                              "officer": "x", "role": "admin"}).status_code == 422
    assert client.get("/api/audit/verify").status_code == 200
