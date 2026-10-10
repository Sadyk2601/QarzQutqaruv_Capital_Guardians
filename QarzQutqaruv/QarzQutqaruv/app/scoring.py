import os
import json
import numpy as np
import lightgbm as lgb
from model.features import make_features, FEATURES
from app.reasons import REASONS

class ScoringEngine:
    def __init__(self, artifacts_dir="model/artifacts"):
        self.model_path = os.path.join(artifacts_dir, "model.txt")
        self.meta_path = os.path.join(artifacts_dir, "meta.json")
        self.cal_path = os.path.join(artifacts_dir, "calibration.json")
        
        self.booster = lgb.Booster(model_file=self.model_path)
        
        with open(self.meta_path, "r", encoding="utf-8") as f:
            self.meta = json.load(f)
            
        with open(self.cal_path, "r", encoding="utf-8") as f:
            self.cal = json.load(f)
            
        self.red_th = self.meta["thresholds"]["red"]
        self.yellow_th = self.meta["thresholds"]["yellow"]

    def score(self, due: list, paid: list, delay: list, lang: str = "en", outstanding: float = 0.0) -> dict:
        # 1. Генерация признаков
        feats_dict = make_features(due, paid, delay)
        X = np.array([[feats_dict[f] for f in FEATURES]])
        
        # 2. Предсказание сырой вероятности
        raw_pred = self.booster.predict(X)[0]
        
        # 3. Калибровка вероятности через интерполяцию
        prob = float(np.interp(raw_pred, self.cal["x"], self.cal["y"]))
        prob = np.clip(prob, 0.0, 1.0)
        
        # 4. Определение зоны риска
        if prob >= self.red_th:
            band = "red"
        elif prob >= self.yellow_th:
            band = "yellow"
        else:
            band = "green"
            
        # 5. Получение вклада признаков (SHAP-like через pred_contrib)
        contribs = self.booster.predict(X, pred_contrib=True)[0]
        # Последний элемент в contribs — это базовое смещение модели, отбрасываем его
        feature_contribs = list(zip(FEATURES, contribs[:-1]))
        # Сортируем по силе положительного вклада в риск (наиболее опасные факторы сверху)
        feature_contribs.sort(key=lambda x: x[1], reverse=True)
        
        top_reasons = []
        for feat_name, val in feature_contribs[:3]:
            if val <= 0 and len(top_reasons) > 0:
                break # Берем топ факторов риска
            
            raw_val = feats_dict[feat_name]
            template_dict = REASONS.get(feat_name, {"en": f"{feat_name}: {raw_val}"})
            template = template_dict.get(lang, template_dict["en"])
            
            # Подставляем форматированные значения
            if "pct" in template:
                formatted_val = round(raw_val * 100, 1)
                text = template.format(pct=formatted_val)
            else:
                text = template.format(val=round(raw_val, 2))
                
            top_reasons.append({
                "feature": feat_name,
                "contribution": float(val),
                "text": text
            })
            
        money_at_risk = float(prob * outstanding)
        
        return {
            "probability": prob,
            "band": band,
            "money_at_risk": money_at_risk,
            "features": feats_dict,
            "reasons": top_reasons
        }