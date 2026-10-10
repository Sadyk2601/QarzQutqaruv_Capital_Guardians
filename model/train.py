"""Train Model 1: probability that a borrower defaults next month.

Data: public UCI "Default of credit card clients" (30,000 anonymised borrowers,
CC BY 4.0). Demographic columns (SEX, EDUCATION, MARRIAGE, AGE) are NOT used by
the model; SEX and AGE are kept aside only for the fairness check.

Rules (our teacher's review of the elimination round):
- untouched 20% hold-out, evaluated once at the end;
- model chosen by 5-fold CV; calibration and zone thresholds fitted on
  out-of-fold predictions, never on the hold-out;
- features use only the past months.

Run from the repository root: python model/train.py
"""
import datetime
import json
import sys
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             precision_recall_curve, roc_auc_score)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.features import FEATURES, MONOTONE, make_features  # noqa: E402

DATA = ROOT / "data" / "raw" / "uci_credit.csv"
ART = ROOT / "model" / "artifacts"
MODEL_VERSION = "lgbm-mono-uci-v2-2026-10-10"
SEED = 42
LGB_PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=100,
                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5,
                  random_state=SEED, verbose=-1)
# Monotone: e.g. more months of delay can never LOWER the risk. Safer to transfer to
# MKBANK installment loans and easier to explain to a regulator.
MONO_PARAMS = dict(LGB_PARAMS, monotone_constraints=[MONOTONE[f] for f in FEATURES])
RED_PRECISION, YELLOW_PRECISION = 0.60, 0.35


def build_features(df, trim=0):
    """trim=k drops the k newest months: we then predict k+1 months ahead."""
    bills = df[[f"BILL_AMT{i}" for i in (6, 5, 4, 3, 2, 1)]].clip(lower=0).to_numpy(float)
    pays = df[[f"PAY_AMT{i}" for i in (6, 5, 4, 3, 2, 1)]].to_numpy(float)
    delays = df[["PAY_6", "PAY_5", "PAY_4", "PAY_3", "PAY_2", "PAY_0"]].clip(lower=0).to_numpy(float)
    if trim:
        bills, pays, delays = bills[:, :-trim], pays[:, :-trim], delays[:, :-trim]
    rows = [make_features(b, p, d) for b, p, d in zip(bills, pays, delays)]
    return pd.DataFrame(rows)[FEATURES]


def min_threshold_for_precision(y, p, target):
    prec, _, thr = precision_recall_curve(y, p)
    ok = np.where(prec[:-1] >= target)[0]
    return float(thr[ok[0]]) if len(ok) else float(np.quantile(p, 0.95))


def zone_stats(y, p, thr):
    mask = p >= thr
    return {"threshold": thr, "flagged_share": float(mask.mean()),
            "precision": float(y[mask].mean()) if mask.any() else 0.0,
            "recall": float(y[mask].sum() / y.sum())}


def main():
    t0 = time.time()
    df = pd.read_csv(DATA)
    n_all = len(df)
    # Domain alignment: keep borrowers who owed money in every one of the 6 months,
    # like an installment loan (inactive cards look like "perfect payers" otherwise).
    df = df[(df[[f"BILL_AMT{i}" for i in range(1, 7)]] > 0).all(axis=1)].reset_index(drop=True)
    y = df["default"].to_numpy()
    X = build_features(df)

    idx = np.arange(len(df))
    tr, te = train_test_split(idx, test_size=0.2, stratify=y, random_state=SEED)
    X_tr, y_tr, X_te, y_te = X.iloc[tr], y[tr], X.iloc[te], y[te]

    # 1. Model choice by 5-fold CV on the training part only.
    oof_lr, oof_gb, oof_free = np.zeros(len(tr)), np.zeros(len(tr)), np.zeros(len(tr))
    for f_tr, f_va in StratifiedKFold(5, shuffle=True, random_state=SEED).split(X_tr, y_tr):
        lr = Pipeline([("scale", StandardScaler()), ("lr", LogisticRegression(max_iter=2000))])
        lr.fit(X_tr.iloc[f_tr], y_tr[f_tr])
        oof_lr[f_va] = lr.predict_proba(X_tr.iloc[f_va])[:, 1]
        gb = lgb.LGBMClassifier(**MONO_PARAMS).fit(X_tr.iloc[f_tr], y_tr[f_tr])
        oof_gb[f_va] = gb.predict_proba(X_tr.iloc[f_va])[:, 1]
        free = lgb.LGBMClassifier(**LGB_PARAMS).fit(X_tr.iloc[f_tr], y_tr[f_tr])
        oof_free[f_va] = free.predict_proba(X_tr.iloc[f_va])[:, 1]
    cv_lr, cv_gb, cv_free = (roc_auc_score(y_tr, oof_lr), roc_auc_score(y_tr, oof_gb),
                             roc_auc_score(y_tr, oof_free))

    # 2. Calibration + zone thresholds on out-of-fold predictions.
    iso = IsotonicRegression(out_of_bounds="clip").fit(oof_gb, y_tr)
    oof_cal = iso.predict(oof_gb)
    red_thr = min_threshold_for_precision(y_tr, oof_cal, RED_PRECISION)
    yellow_thr = min_threshold_for_precision(y_tr, oof_cal, YELLOW_PRECISION)

    # 3. Final model on the whole training part, ONE evaluation on the hold-out.
    final = lgb.LGBMClassifier(**MONO_PARAMS).fit(X_tr, y_tr)
    p_te = iso.predict(final.predict_proba(X_te)[:, 1])
    n_def = int(y_te.sum())

    top10_thr, top20_thr = np.quantile(p_te, 0.90), np.quantile(p_te, 0.80)
    not_late = X_te["delay_last"].to_numpy() == 0
    hidden_def = int(y_te[not_late].sum())
    # Inside the group a "missed payment" rule cannot see at all (not late yet):
    y_nl, p_nl = y_te[not_late], p_te[not_late]
    top_nl = p_nl >= np.quantile(p_nl, 0.90)
    hidden = {
        "n_test_defaulters": n_def,
        "n_defaulters_not_late_yet": hidden_def,
        "share_of_defaulters_not_late_yet": hidden_def / n_def,
        "n_not_late": int(not_late.sum()),
        "default_rate_not_late": float(y_nl.mean()),
        "auc_within_not_late": float(roc_auc_score(y_nl, p_nl)),
        "top10_within_not_late_default_rate": float(y_nl[top_nl].mean()),
        "top10_within_not_late_lift": float(y_nl[top_nl].mean() / y_nl.mean()),
        "top10_within_not_late_capture": float(y_nl[top_nl].sum() / y_nl.sum()),
        "found_in_overall_top20": float(y_te[not_late & (p_te >= top20_thr)].sum() / hidden_def),
    }

    rules = {}
    order = np.argsort(-p_te)
    for name, months in (("missed_1_month", 1), ("missed_2_months", 2)):
        rule = X_te["delay_last"].to_numpy() >= months
        n = int(rule.sum())
        model_mask = np.zeros(len(p_te), bool)
        model_mask[order[:n]] = True
        rules[name] = {"alerts": n,
                       "rule_precision": float(y_te[rule].mean()), "rule_recall": float(y_te[rule].sum() / n_def),
                       "model_precision": float(y_te[model_mask].mean()),
                       "model_recall": float(y_te[model_mask].sum() / n_def)}

    # 4. How early we see risk: drop the newest months and predict further ahead.
    horizon = {"1_month_ahead": float(roc_auc_score(y_te, p_te))}
    for trim in (1, 2, 3):
        Xh = build_features(df, trim)
        mh = lgb.LGBMClassifier(**MONO_PARAMS).fit(Xh.iloc[tr], y_tr)
        horizon[f"{trim + 1}_months_ahead"] = float(roc_auc_score(y_te, mh.predict_proba(Xh.iloc[te])[:, 1]))

    # 5. Reference: what we would gain with absolute (non-transferable) columns.
    raw_cols = (["LIMIT_BAL", "PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
                + [f"BILL_AMT{i}" for i in range(1, 7)] + [f"PAY_AMT{i}" for i in range(1, 7)])
    ref = lgb.LGBMClassifier(**LGB_PARAMS).fit(df[raw_cols].iloc[tr], y_tr)
    ref_auc = roc_auc_score(y_te, ref.predict_proba(df[raw_cols].iloc[te])[:, 1])

    # 6. Fairness check: the model never sees sex or age; we only measure.
    sex, age = df["SEX"].to_numpy()[te], df["AGE"].to_numpy()[te]
    groups = {"female": sex == 2, "male": sex == 1,
              "age_under_30": age < 30, "age_30_45": (age >= 30) & (age <= 45), "age_over_45": age > 45}
    fairness = {g: {"n": int(m.sum()), "auc": float(roc_auc_score(y_te[m], p_te[m])),
                    "red_share": float((p_te[m] >= red_thr).mean()), "default_rate": float(y_te[m].mean())}
                for g, m in groups.items()}

    # 7. Speed of one score (single borrower, like the API).
    booster = final.booster_
    row = X_te.iloc[[0]].to_numpy()
    t = time.perf_counter()
    for _ in range(300):
        booster.predict(row)
    latency_ms = (time.perf_counter() - t) / 300 * 1000

    prob_true, prob_pred = calibration_curve(y_te, p_te, n_bins=10, strategy="quantile")
    gain = booster.feature_importance("gain")
    metrics = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "data": (f"UCI Default of credit card clients (CC BY 4.0): {len(df):,} of {n_all:,} borrowers who owed "
                 "money in all 6 months (installment-like); demographics removed"),
        "n_train": int(len(tr)), "n_test": int(len(te)), "base_rate": float(y.mean()),
        "cv_auc_lightgbm": float(cv_gb), "cv_auc_lightgbm_unconstrained": float(cv_free),
        "cv_auc_logreg": float(cv_lr), "monotone_constraints": MONOTONE,
        "holdout_auc": float(roc_auc_score(y_te, p_te)),
        "holdout_pr_auc": float(average_precision_score(y_te, p_te)),
        "holdout_brier": float(brier_score_loss(y_te, p_te)),
        "red": zone_stats(y_te, p_te, red_thr),
        "yellow_or_red": zone_stats(y_te, p_te, yellow_thr),
        "top10_capture": float(y_te[p_te >= top10_thr].sum() / n_def),
        "hidden_defaulters": hidden,
        "rule_vs_model": rules,
        "horizon_auc": horizon,
        "reference_auc_with_absolute_columns": float(ref_auc),
        "fairness": fairness,
        "latency_ms_per_score": float(latency_ms),
        "feature_importance_gain": {f: float(g / gain.sum()) for f, g in zip(FEATURES, gain)},
        "reliability": {"predicted": prob_pred.tolist(), "observed": prob_true.tolist()},
    }
    meta = {"model_version": MODEL_VERSION, "features": FEATURES,
            "thresholds": {"red": red_thr, "yellow": yellow_thr}, "horizon_months": 1}
    grid = np.linspace(0, 1, 201)
    calibration = {"x": grid.tolist(), "y": iso.predict(grid).tolist()}

    ART.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(ART / "model.txt"))
    (ART / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (ART / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (ART / "calibration.json").write_text(json.dumps(calibration), encoding="utf-8")

    print(f"CV AUC  LightGBM monotone {cv_gb:.4f} | unconstrained {cv_free:.4f} | LogReg {cv_lr:.4f} | n={len(df)}")
    print(f"Hold-out AUC {metrics['holdout_auc']:.4f} | PR-AUC {metrics['holdout_pr_auc']:.4f}")
    print(f"Red  thr {red_thr:.3f}: {metrics['red']}")
    print(f"Yel+ thr {yellow_thr:.3f}: {metrics['yellow_or_red']}")
    print("Hidden defaulters:", hidden)
    print("Rule vs model:", rules)
    print("Horizon:", horizon, "| reference AUC", round(ref_auc, 4))
    print(f"Latency {latency_ms:.3f} ms | done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
