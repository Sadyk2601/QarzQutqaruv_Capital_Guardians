"""Generate the SYNTHETIC MKBANK-style demo portfolio (no real people, seed 42).

Every borrower gets 12 months (Oct 2025 - Sep 2026) of: amount due, amount paid,
days late, business turnover, card transactions and app logins, plus profile
fields (segment, client tenure, guarantor, app). Scenarios: healthy, seasonal
stress, deteriorating (card and app activity fall 1-2 months BEFORE payments),
and sudden shock (a known blind spot of any model).
DEMO-001 "Dilnoza R." is a fixed, hand-written story used in the pitch.
Run from the repository root: python scripts/make_demo_portfolio.py
"""
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "demo_portfolio.json"
N = 500
CAL = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03",
       "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
MONTH_IDX = [9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7, 8]  # calendar month (0 = Jan) of each column

# Seasonal turnover multipliers, Jan..Dec (mean ~1). Assumptions for the demo.
SEASONALITY = {
    "tailoring":        [0.8, 0.8, 1.25, 1.25, 1.2, 0.9, 0.85, 1.2, 1.2, 1.0, 0.8, 0.75],
    "greenhouse":       [0.7, 1.2, 1.3, 1.3, 1.25, 1.0, 0.55, 0.5, 0.8, 0.95, 0.85, 0.6],
    "livestock":        [0.85, 0.85, 0.9, 0.9, 0.95, 1.2, 1.25, 1.2, 0.9, 0.9, 0.9, 1.2],
    "retail_shop":      [0.9, 0.9, 1.2, 0.95, 0.95, 0.95, 0.95, 0.95, 1.0, 1.0, 1.05, 1.2],
    "bakery":           [1.0, 1.0, 1.05, 1.0, 1.0, 0.95, 0.95, 0.95, 1.0, 1.0, 1.0, 1.1],
    "wedding_services": [0.45, 0.45, 0.8, 0.95, 1.35, 1.35, 1.0, 1.1, 1.35, 1.35, 0.95, 0.9],
}
REGIONS = ["Tashkent", "Tashkent region", "Samarkand", "Bukhara", "Andijan", "Namangan", "Fergana",
           "Kashkadarya", "Surkhandarya", "Khorezm", "Navoi", "Syrdarya", "Jizzakh", "Karakalpakstan"]
FIRST = ["Aziz", "Malika", "Jamshid", "Rustam", "Nodira", "Bekzod", "Shahzod", "Gulnoza", "Timur",
         "Sardor", "Madina", "Otabek", "Zarina", "Farrukh", "Kamola", "Ulugbek", "Dildora", "Sherzod",
         "Nilufar", "Javlon", "Feruza", "Akmal", "Sevara", "Bobur", "Lola", "Dilshod", "Munisa"]
OFFICERS = ["Kamola T.", "Sanjar M.", "Dilfuza A.", "Rustam Y.", "Oybek N.", "Shahnoza K."]
SCENARIOS, WEIGHTS = ["healthy", "seasonal_stress", "deteriorating", "shock"], [0.72, 0.10, 0.15, 0.03]


def annuity(B, annual_rate, n):
    r = annual_rate / 12
    return B * r / (1 - (1 + r) ** -n)


def balance_after(B, annual_rate, n, k):
    """Outstanding principal of an annuity loan after k payments."""
    r, p = annual_rate / 12, annuity(B, annual_rate, n)
    return B * (1 + r) ** k - p * ((1 + r) ** k - 1) / r


def segment_of(loan):
    return "household" if loan <= 30_000_000 else ("micro_business" if loan <= 100_000_000 else "sme")


def dilnoza():
    inst = 2_290_000
    turnover_shape = [1, 1, 1, 1, 1, 1, 1, 1, 0.75, 0.6, 0.5, 0.45]
    seas = SEASONALITY["tailoring"]
    turnover = [int(9_100_000 * seas[m] * f) for m, f in zip(MONTH_IDX, turnover_shape)]
    history = [{"due": inst, "paid": inst, "days_late": 0} for _ in range(9)]
    # Payments go to the oldest arrears first, so "days late" counts the oldest unpaid part.
    history += [{"due": 2_290_000, "paid": 1_500_000, "days_late": 9},
                {"due": 3_080_000, "paid": 1_200_000, "days_late": 24},
                {"due": 4_170_000, "paid": 920_000, "days_late": 35}]
    return {
        "id": "DEMO-001", "name": "Dilnoza R.", "region": "Samarkand", "business_type": "tailoring",
        "segment": "micro_business", "loan_amount": 60_000_000, "annual_rate": 0.22, "term_months": 36,
        "months_elapsed": 14, "outstanding": 41_000_000, "installment": inst,
        "client_since_months": 52, "prior_loans_repaid": 1, "has_guarantor": True, "has_app": True,
        "assigned_officer": "Kamola T.", "last_app_login_days": 19,
        "calendar_months": CAL, "history": history, "turnover": turnover,
        "card_txn_count": [118, 121, 117, 115, 119, 124, 126, 122, 96, 78, 61, 49],
        "app_logins": [18, 17, 19, 16, 18, 20, 19, 18, 15, 9, 4, 2],
        "scenario": "deteriorating",
    }


def borrower(i, rng):
    biz = rng.choice(list(SEASONALITY))
    scenario = rng.choices(SCENARIOS, WEIGHTS)[0]
    loan = rng.choice([15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200]) * 1_000_000
    rate = round(rng.uniform(0.14, 0.28), 4)
    term = rng.choice([24, 36])
    elapsed = rng.randint(6, min(20, term - 4))
    inst = int(annuity(loan, rate, term))
    outstanding = int(balance_after(loan, rate, term, elapsed))
    base_turn = inst * rng.uniform(3.0, 5.5)
    seas = SEASONALITY[biz]

    drop_start = rng.randint(7, 9)       # month index where turnover starts falling
    drop = rng.uniform(0.35, 0.65)       # depth of the fall
    turnover, history, cards, logins = [], [], [], []
    arrears, days_late = 0, 0
    base_cards, base_logins = rng.randint(40, 160), rng.randint(6, 25)
    has_app = rng.random() < 0.7

    for j, m in enumerate(MONTH_IDX):
        f = 1.0
        if scenario == "deteriorating" and j >= drop_start:
            f = 1 - drop * min(1.0, (j - drop_start + 1) / 2)
        if scenario == "shock" and j == 11:
            f = 0.15
        t = base_turn * seas[m] * f * rng.uniform(0.93, 1.07)
        turnover.append(int(t))
        cards.append(max(0, int(base_cards * seas[m] * f * rng.uniform(0.9, 1.1))))
        lag = 1 if scenario == "deteriorating" and j >= drop_start + 1 else 0
        logins.append(max(0, int(base_logins * (f if lag else 1) * rng.uniform(0.8, 1.2))) if has_app else 0)

        due = inst + arrears
        if scenario == "healthy":
            paid = due
        elif scenario == "seasonal_stress":
            paid = due if seas[m] >= 1.0 else min(due, int(inst * rng.uniform(0.55, 0.9)))
        elif scenario == "shock" and j == 11:
            paid = 0
        else:  # deteriorating (and shock before the shock month): pay what the business allows
            paid = min(due, int(t * rng.uniform(0.40, 0.55)))
        arrears = due - paid
        if arrears > 0:
            days_late = days_late + 30 if days_late else rng.randint(5, 20)
        else:
            days_late = 0
        history.append({"due": int(due), "paid": int(paid), "days_late": int(min(days_late, 365))})

    last_login = rng.randint(0, 6) if has_app else 99
    if has_app and scenario == "deteriorating":
        last_login = rng.randint(10, 35)
    return {
        "id": f"DEMO-{i:03d}", "name": f"{rng.choice(FIRST)} {rng.choice('ABDFGKMNORSTUXYZ')}.",
        "region": rng.choice(REGIONS), "business_type": biz, "segment": segment_of(loan),
        "loan_amount": loan, "annual_rate": rate, "term_months": term, "months_elapsed": elapsed,
        "outstanding": outstanding, "installment": inst,
        "client_since_months": rng.randint(6, 120), "prior_loans_repaid": rng.choices([0, 1, 2, 3], [45, 30, 17, 8])[0],
        "has_guarantor": rng.random() < 0.6, "has_app": has_app, "assigned_officer": rng.choice(OFFICERS),
        "last_app_login_days": last_login, "calendar_months": CAL, "history": history, "turnover": turnover,
        "card_txn_count": cards, "app_logins": logins, "scenario": scenario,
    }


def main():
    rng = random.Random(42)
    portfolio = [dilnoza()] + [borrower(i, rng) for i in range(2, N + 1)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(portfolio, ensure_ascii=False), encoding="utf-8")
    counts = {s: sum(b["scenario"] == s for b in portfolio) for s in SCENARIOS}
    print(f"Saved {len(portfolio)} synthetic borrowers to {OUT} | scenarios {counts}")


if __name__ == "__main__":
    main()
