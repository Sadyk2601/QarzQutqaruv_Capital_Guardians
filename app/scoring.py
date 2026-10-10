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

    def score(self, due, paid, delay) -> dict:
        feats = make_features(due, paid, delay)
        X = np.array([[feats[f] for f in FEATURES]])
        raw = float(self.booster.predict(X)[0])
        prob = float(np.clip(np.interp(raw, self.cal_x, self.cal_y), 0, 1))
        contrib = self.booster.predict(X, pred_contrib=True)[0][:-1]  # last column = bias
        return {"prob": prob, "features": feats, "contrib": dict(zip(FEATURES, map(float, contrib)))}

    def score_history(self, history) -> dict:
        h = history[-6:]
        return self.score([x["due"] for x in h], [x["paid"] for x in h], [delay_months(x["days_late"]) for x in h])

    @staticmethod
    def reasons(features: dict, contrib: dict, lang: str = "en", k: int = 3) -> list:
        top = sorted(((f, c) for f, c in contrib.items() if c > 0), key=lambda x: -x[1])[:k]
        if not top:
            return [{"feature": None, "contribution": 0.0, "text": NO_RISK.get(lang, NO_RISK["en"])}]
        return [{"feature": f, "contribution": round(c, 4), "value": round(features[f], 4),
                 "text": reason_text(f, features[f], lang)} for f, c in top]
