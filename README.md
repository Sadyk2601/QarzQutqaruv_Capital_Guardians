# QarzQutqaruv: early warning & rescue plans for MKBANK loan officers

**Live demo:** <https://qarzqutqaruv.onrender.com> (free instance: the first visit after a quiet period can take ~50 s to wake up) · **Team:** Capital Guardians (WIUT Hackathon 2026, FinTech / AI in Finance)
**Mode:** Partner product for **MKBANK**. Owner: Risk Management Department (portfolio monitoring). Users: loan officers and mahalla bankers.

> Banks learn that a borrower is in trouble 3 months too late, when the loan is already a problem loan.
> QarzQutqaruv finds borrowers 1–2 months **before** that, explains why in plain words (EN / RU / UZ), picks the best
> next action for each of them, plans the officers' day, and keeps a tamper-evident record of every decision.
> A person always decides.

## Why
- MKBANK's problem loans grew from **4.4% to 9.9%** of its portfolio between 1 Jan and 1 Aug 2026, reaching 2.28 trillion UZS. This is the third-highest ratio among all banks. Source: Central Bank of Uzbekistan, *Problem loans of commercial banks*: [1 Jan 2026](https://cbu.uz/ru/statistics/bankstats/3326242/), [1 Aug 2026](https://cbu.uz/ru/statistics/bankstats/4470299/).
- In a Central Bank survey of 5,800 people, **61% of borrowers** said they struggle to repay on time ([Kun.uz, Jul 2026](https://kun.uz/en/news/2026/07/21/six-in-10-borrowers-in-uzbekistan-struggle-to-repay-loans-on-time-central-bank-survey)).
- Scoring at loan issuance exists, and calls after a missed payment exist. The months **in between** are not watched.
- In our test data, **48% of next month's defaulters had not missed a single payment yet**, so a "missed payment" rule cannot see half of the problem.

## How it works
```
Payments history (+ card & app activity, profile)
   │
   ▼
Model 1  - risk of default next month
           LightGBM, monotone constraints, own-norm features, calibrated
           → probability, zone (policy thresholds by segment), top reasons, own-norm facts
   │
   ├─► Path back to green - the smallest next payment that moves the borrower out of risk (model what-if)
   │
   ▼
Model 2  - next best action
           Bayesian Beta model per (problem type × action): call, SMS, personal SMS,
           guarantor call, letter, visit, rescue offer
           expected loss prevented − cost
           → daily plan under the officers' time budget (greedy knapsack)
   │
   ├─► Optimized rescue plan - smallest term extension with a season-shaped schedule;
   │                          present value = outstanding (bank-neutral),
   │                          payment ≤ 30% of expected income
   ├─► Offer letter (EN / RU / UZ, template-based)
   ▼
Officer decides → SHA-256 hash-chained audit log → outcome (resolved / not) → Model 2 learns
```

| Part | File |
|---|---|
| Own-norm features (shared by training and the server) | [`model/features.py`](model/features.py) |
| Training, metrics, fairness check | [`model/train.py`](model/train.py) → `model/artifacts/` |
| Scoring and reasons | [`app/scoring.py`](app/scoring.py), [`app/reasons.py`](app/reasons.py) |
| Path back to green | [`app/counterfactual.py`](app/counterfactual.py) |
| Action ladder, rescue-plan optimizer, letter | [`app/actions.py`](app/actions.py) |
| Model 2 (next best action, daily plan, learning) | [`app/nba.py`](app/nba.py), [`app/action_priors.json`](app/action_priors.json) |
| Audit log | [`app/audit.py`](app/audit.py) |
| API and site | [`app/main.py`](app/main.py), [`app/static/`](app/static/) |

## Quality (measured by us, see `model/artifacts/metrics.json`)
Data: 22,384 borrowers from the public UCI dataset who owed money in all 6 months. An untouched 20% hold-out (4,477 borrowers) was evaluated once.

| Metric | Value |
|---|---|
| ROC-AUC, hold-out | **0.765** (CV 0.778; logistic-regression baseline 0.769) |
| Red zone | 18% of borrowers flagged; **62%** of them really default |
| Defaulters who were not late yet | 48% of all defaulters; our top-10% list among them has **2.1×** the average default rate |
| Seeing risk earlier | AUC 0.765 (1 month ahead) · 0.737 (2) · 0.707 (3) · 0.688 (4) |
| Officers' rule "missed 2 months" vs model at the same number of alerts | precision 70% vs 70%. Same as the rule where the rule works, and it also ranks the people the rule cannot see |
| Fairness (model never sees sex or age) | AUC 0.755–0.782 across sex and age groups |
| Speed | ≈ 0.07 ms per score on a laptop CPU |

How the numbers were produced (our teacher's review of our elimination round):
- The hold-out is never touched until the final evaluation.
- Calibration and zone thresholds are fitted on out-of-fold predictions.
- Features use the past only.
- Demographic columns are removed.

**Known limitations**
- The model is trained on credit-card borrowers (Taiwan, 2005), not MKBANK micro-loans. That's why we use only transferable own-norm behaviour features plus monotone constraints. The MKBANK pilot retrains the model inside the bank.
- Sudden shocks without earlier signals cannot be predicted.
- Loans with less than 6 months of history are not scored.
- Card and app early signals are rules in the demo (no public data exists); they become model features in the pilot.
- Action effects outside the cited experiments are assumptions until the pilot measures them with a 10% control group.

## Run locally
```bash
python -m venv .venv && .venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-train.txt
python scripts/download_uci.py        # public UCI data → data/raw/ (not committed)
python model/train.py                 # ~15 s, writes model/artifacts/
python scripts/make_demo_portfolio.py # synthetic demo portfolio
python -m pytest -q tests
uvicorn app.main:app --reload         # http://localhost:8000
```
The trained artifacts and the synthetic portfolio are committed, so `pip install -r requirements.txt && uvicorn app.main:app` is enough to run the site.

## Deployment
- **Prototype.** A Docker image (`Dockerfile`) is deployed on Render (Frankfurt) from this public repository. Each deploy is started from the Render dashboard for a specific commit of `main`, and Render keeps the deploy history with commit hashes. The deployed commit is the repository HEAD at submission. Tests run on every push (GitHub Actions, `.github/workflows/ci.yml`).
- **Production design (customer data never leaves the bank):**
  - one on-prem server inside MKBANK runs the same container;
  - **no external API is called**: the models are a few hundred KB, and letters are templates;
  - data comes from core banking, card processing, the mobile app, CRM and the KATM credit bureau into a feature store inside the perimeter;
  - the audit log goes to append-only storage, kept 5+ years.
- **Security basics:**
  - strict server-side validation (Pydantic);
  - per-IP rate limit on POST;
  - no secrets in the repository;
  - all text is rendered with `textContent` (XSS-safe).

## Data sources and licences
| Data | Use | Licence / status |
|---|---|---|
| UCI *Default of credit card clients*: Yeh, I. C. & Lien, C. H. (2009), *Expert Systems with Applications* 36(2), 2473–2480. <https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients> | Training and testing Model 1. Columns SEX, EDUCATION, MARRIAGE and AGE are not used by the model; SEX and AGE are used only for the fairness check | CC BY 4.0 |
| Synthetic MKBANK-style portfolio (`scripts/make_demo_portfolio.py`, seed 42) | Demo only | Generated by us; no real people |
| Action-effect priors: Cadena & Schoar (2011) NBER w17020; Karlan, Morten & Zinman (Philippines RCT); Laudenbach & Siegel (2025) *Journal of Finance*; Bursztyn et al. (2019) *JPE* | Model 2 starting knowledge | Published research, cited |
| Central Bank of Uzbekistan statistics, Kun.uz, Spot.uz, Daryo reports | Problem sizing (slides) | Public |

## Reuse and tools declaration
- **Reuse:** the idea of **own-norm features** (comparing a client with their own history) comes from our elimination-round project (Capital Guardians, AML alert prioritisation, WIUT Hackathon 2026). The code for this final was written during the final.
- **Libraries:** FastAPI, Uvicorn, Pydantic, LightGBM, scikit-learn, pandas, NumPy, pytest.
- **AI coding assistants** were used during development. The team reviewed the code and checked it with tests.

## Team
Behzod (product, business case), Sadik (ML and backend), Mirkomil (deployment and demo): Capital Guardians.
