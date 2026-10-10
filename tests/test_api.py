import pytest
from fastapi.testclient import TestClient
from app.main import app, portfolio_data

client = TestClient(app)

def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200

def test_portfolio_and_borrower():
    # Заполняем память фейковым заемщиком со всеми нужными полями
    if not portfolio_data:
        portfolio_data.append({
            "id": "DEMO-001", 
            "name": "Test",
            "region": "Test",
            "business_type": "other",
            "prob": 0.5,
            "band": "yellow",
            "money_at_risk": 1000,
            "reasons": [{"text": "test"}]
        })
    assert client.get("/api/portfolio").status_code == 200
    assert client.get("/api/borrower/DEMO-001").status_code == 200

def test_score_valid():
    payload = {
        "lang": "en", "business_type": "tailoring",
        "loan_amount": 60000000, "annual_rate": 0.22, "term_months": 36, "months_elapsed": 14,
        "outstanding": 41000000,
        "history": [{"due": 1000, "paid": 1000, "days_late": 0} for _ in range(6)]
    }
    res = client.post("/api/score", json=payload)
    assert res.status_code == 200
    assert "band" in res.json()

def test_score_invalid_history_length():
    payload = {
        "lang": "en", "business_type": "tailoring",
        "loan_amount": 60000000, "annual_rate": 0.22, "term_months": 36, "months_elapsed": 14,
        "outstanding": 41000000,
        "history": [{"due": 1000, "paid": 1000, "days_late": 0} for _ in range(2)] # Длина 2 вместо 6-12
    }
    res = client.post("/api/score", json=payload)
    assert res.status_code == 422 # Ошибка валидации

def test_score_negative_sum():
    payload = {
        "lang": "en", "business_type": "tailoring",
        "loan_amount": 60000000, "annual_rate": 0.22, "term_months": 36, "months_elapsed": 14,
        "outstanding": -5000, # Отрицательный долг
        "history": [{"due": 1000, "paid": 1000, "days_late": 0} for _ in range(6)]
    }
    res = client.post("/api/score", json=payload)
    assert res.status_code == 422