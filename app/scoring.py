"""Model 1: risk of default next month + plain-language reasons."""
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np

from app.reasons import NO_RISK, reason_text
from model.features import FEATURES, make_features

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model" / "artifacts"


def delay_months(days_late: int) -> int:
    return int(min(9, -(-int(days_late) // 30)))  # ceil(days / 30), capped at 9


class ScoringEngine:
    def __init__(self, artifacts=ART):
        self.booster = lgb.Booster(model_file=str(artifacts / "model.txt"))
        self.meta = json.loads((artifacts / "meta.json").read_text(encoding="utf-8"))
        cal = json.loads((artifacts / "calibration.json").read_text(encoding="utf-8"))
        self.cal_x, self.cal_y = np.array(cal["x"]), np.array(cal["y"])
        self.policy = json.loads((Path(__file__).parent / "risk_policy.json").read_text(encoding="utf-8"))
        self.version = self.meta["model_version"]

    def thresholds(self, segment: str = "micro_business") -> dict:
        shift = self.policy["segments"].get(segment, {"shift": 0.0})["shift"]
        t = self.meta["thresholds"]
        return {"red": round(t["red"] + shift, 4), "yellow": round(t["yellow"] + shift, 4), "segment_shift": shift}

    def band(self, prob: float, segment: str = "micro_business") -> str:
        t = self.thresholds(segment)
        return "red" if prob >= t["red"] else ("yellow" if prob >= t["yellow"] else "green")

    def score_many(self, feature_rows) -> list:
        """Score many borrowers in one call. One thread: small cloud instances have a
        fraction of a CPU, and many OpenMP threads would fight over it."""
        X = np.array([[f[name] for name in FEATURES] for f in feature_rows])
        raw = self.booster.predict(X, num_threads=1)
        probs = np.clip(np.interp(raw, self.cal_x, self.cal_y), 0, 1)
        contribs = self.booster.predict(X, pred_contrib=True, num_threads=1)[:, :-1]  # last column = bias
        return [{"prob": float(p), "features": f, "contrib": dict(zip(FEATURES, map(float, c)))}
                for p, f, c in zip(probs, feature_rows, contribs)]

    def score(self, due, paid, delay) -> dict:
        return self.score_many([make_features(due, paid, delay)])[0]

    @staticmethod
    def history_features(history) -> dict:
        h = history[-6:]
        return make_features([x["due"] for x in h], [x["paid"] for x in h], [delay_months(x["days_late"]) for x in h])

    def score_history(self, history) -> dict:
        return self.score_many([self.history_features(history)])[0]

    @staticmethod
    def reasons(features: dict, contrib: dict, lang: str = "en", k: int = 3) -> list:
        top = sorted(((f, c) for f, c in contrib.items() if c > 0), key=lambda x: -x[1])[:k]
        if not top:
            return [{"feature": None, "contribution": 0.0, "text": NO_RISK.get(lang, NO_RISK["en"])}]
        return [{"feature": f, "contribution": round(c, 4), "value": round(features[f], 4),
                 "text": reason_text(f, features[f], lang)} for f, c in top]
