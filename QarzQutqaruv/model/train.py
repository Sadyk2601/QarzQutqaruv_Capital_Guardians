import os
import json
import datetime
import numpy as np
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, precision_recall_curve
from sklearn.calibration import calibration_curve

# Импортируем нашу функцию признаков
from features import make_features, FEATURES

def prep_data_for_horizon(df, h_trim=0):
    """Преобразует строку UCI в признаки с отрезанием h_trim месяцев с конца."""
    records = []
    for _, row in df.iterrows():
        # Месяцы от старого (6) к новому (1)
        due = [max(row[f'BILL_AMT{i}'], 0) for i in [6, 5, 4, 3, 2, 1]]
        paid = [row[f'PAY_AMT{i}'] for i in [6, 5, 4, 3, 2, 1]]
        delay = [max(row['PAY_6'], 0), max(row['PAY_5'], 0), max(row['PAY_4'], 0), 
                 max(row['PAY_3'], 0), max(row['PAY_2'], 0), max(row['PAY_0'], 0)]
        
        if h_trim > 0:
            due = due[:-h_trim]
            paid = paid[:-h_trim]
            delay = delay[:-h_trim]
            
        feats = make_features(due, paid, delay)
        records.append(feats)
    return pd.DataFrame(records)

def main():
    print("Загрузка данных и генерация признаков (это займет ~10-15 сек)...")
    df = pd.read_csv('../data/raw/uci_credit.csv')
    
    # Сохраняем демографию для теста на справедливость
    SEX = df['SEX']
    AGE = df['AGE']
    y = df['default']
    
    # Референсные колонки (абсолютные суммы и лимит) для сравнения
    ref_cols = ['LIMIT_BAL', 'BILL_AMT1', 'BILL_AMT2', 'BILL_AMT3', 'BILL_AMT4', 'BILL_AMT5', 'BILL_AMT6',
                'PAY_AMT1', 'PAY_AMT2', 'PAY_AMT3', 'PAY_AMT4', 'PAY_AMT5', 'PAY_AMT6']
    X_ref = df[ref_cols]

    X = prep_data_for_horizon(df, h_trim=0)

    print("Разделение на Train и отложенный Test (80/20)...")
    idx = np.arange(len(df))
    idx_train, idx_test = train_test_split(idx, test_size=0.2, stratify=y, random_state=42)
    
    X_train, y_train = X.iloc[idx_train].reset_index(drop=True), y.iloc[idx_train].reset_index(drop=True)
    X_test, y_test = X.iloc[idx_test].reset_index(drop=True), y.iloc[idx_test].reset_index(drop=True)
    
    # Кросс-валидация для выбора модели и калибровки
    print("Кросс-валидация (5 фолдов)...")
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    
    oof_logreg = np.zeros(len(X_train))
    oof_lgbm = np.zeros(len(X_train))
    
    lgb_params = {
        'n_estimators': 400, 'learning_rate': 0.03, 'num_leaves': 15, 
        'min_child_samples': 100, 'subsample': 0.8, 'subsample_freq': 1, 
        'colsample_bytree': 0.8, 'reg_lambda': 5, 'random_state': 42, 'verbose': -1
    }
    
    for train_idx, val_idx in kf.split(X_train, y_train):
        X_tr, y_tr = X_train.iloc[train_idx], y_train.iloc[train_idx]
        X_val = X_train.iloc[val_idx]
        
        # LogReg
        pipe = Pipeline([('scaler', StandardScaler()), ('lr', LogisticRegression(max_iter=1000))])
        pipe.fit(X_tr, y_tr)
        oof_logreg[val_idx] = pipe.predict_proba(X_val)[:, 1]
        
        # LightGBM
        model = lgb.LGBMClassifier(**lgb_params)
        model.fit(X_tr, y_tr)
        oof_lgbm[val_idx] = model.predict_proba(X_val)[:, 1]

    cv_auc_logreg = roc_auc_score(y_train, oof_logreg)
    cv_auc_lgbm = roc_auc_score(y_train, oof_lgbm)
    print(f"CV AUC: LogReg = {cv_auc_logreg:.4f}, LightGBM = {cv_auc_lgbm:.4f}")

    print("Калибровка и поиск порогов на Out-Of-Fold предсказаниях...")
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof_lgbm, y_train)
    
    cal_x = np.linspace(0, 1, 101)
    cal_y = iso.predict(cal_x)
    
    oof_cal = iso.predict(oof_lgbm)
    precisions, recalls, thresholds = precision_recall_curve(y_train, oof_cal)
    
    # Пороги (с защитой от пустых массивов)
    red_th = thresholds[np.argmax(precisions[:-1] >= 0.60)] if any(precisions[:-1] >= 0.60) else 0.5
    yellow_th = thresholds[np.argmax(precisions[:-1] >= 0.35)] if any(precisions[:-1] >= 0.35) else 0.3

    print("Обучение финальной модели на всём Train...")
    final_model = lgb.LGBMClassifier(**lgb_params)
    final_model.fit(X_train, y_train)
    
    # --- ОЦЕНКА НА ОТЛОЖЕННОМ ТЕСТЕ ---
    raw_preds = final_model.predict_proba(X_test)[:, 1]
    test_preds = iso.predict(raw_preds)
    
    holdout_auc = roc_auc_score(y_test, test_preds)
    
    # Метрики зон
    red_mask = test_preds >= red_th
    yellow_or_red_mask = test_preds >= yellow_th
    
    # Top 10% capture
    q90 = np.percentile(test_preds, 90)
    top10_mask = test_preds >= q90
    top10_capture = y_test[top10_mask].sum() / y_test.sum()
    
    # Hidden Defaulters
    hidden_mask = X_test['delay_last'] == 0
    hidden_y = y_test[hidden_mask]
    hidden_preds = test_preds[hidden_mask]
    q80 = np.percentile(test_preds, 80)
    
    hd_top10 = hidden_y[hidden_preds >= q90].sum() / hidden_y.sum() if hidden_y.sum() > 0 else 0
    hd_top20 = hidden_y[hidden_preds >= q80].sum() / hidden_y.sum() if hidden_y.sum() > 0 else 0

    # Rule vs Model
    rule_mask = X_test['delay_last'] >= 1
    N_rule = rule_mask.sum()
    rule_prec = y_test[rule_mask].mean()
    rule_rec = y_test[rule_mask].sum() / y_test.sum()
    
    topN_th = np.sort(test_preds)[::-1][N_rule-1] if N_rule > 0 else 1.0
    model_mask = test_preds >= topN_th
    model_prec = y_test[model_mask].mean() if model_mask.sum() > 0 else 0
    model_rec = y_test[model_mask].sum() / y_test.sum()
    
    # Fairness
    sex_test, age_test = SEX.iloc[idx_test].reset_index(drop=True), AGE.iloc[idx_test].reset_index(drop=True)
    age_groups = np.digitize(age_test, bins=[30, 46]) # 0: <30, 1: 30-45, 2: >45
    fairness = {
        "sex_1_auc": roc_auc_score(y_test[sex_test==1], test_preds[sex_test==1]),
        "sex_2_auc": roc_auc_score(y_test[sex_test==2], test_preds[sex_test==2]),
        "age_under_30_auc": roc_auc_score(y_test[age_groups==0], test_preds[age_groups==0]),
        "age_30_45_auc": roc_auc_score(y_test[age_groups==1], test_preds[age_groups==1]),
        "age_over_45_auc": roc_auc_score(y_test[age_groups==2], test_preds[age_groups==2])
    }
    
    # Feature Importance & Reliability
    fi = (final_model.feature_importances_ / final_model.feature_importances_.sum()).tolist()
    prob_true, prob_pred = calibration_curve(y_test, test_preds, n_bins=10)
    
    # Horizon AUC
    print("Расчет горизонта риска (1, 2, 3 месяца)...")
    horizons_auc = {}
    for h in [1, 2, 3]:
        X_h = prep_data_for_horizon(df, h_trim=h)
        X_h_tr, y_h_tr = X_h.iloc[idx_train], y.iloc[idx_train]
        m_h = lgb.LGBMClassifier(**lgb_params).fit(X_h_tr, y_h_tr)
        preds_h = m_h.predict_proba(X_h.iloc[idx_test])[:, 1]
        horizons_auc[f"horizon_{h}"] = roc_auc_score(y.iloc[idx_test], preds_h)

    # Референсная модель с LIMIT и абсолютными суммами (только справка)
    ref_m = lgb.LGBMClassifier(**lgb_params).fit(X_ref.iloc[idx_train], y_train)
    ref_preds = ref_m.predict_proba(X_ref.iloc[idx_test])[:, 1]
    
    # Подготовка файлов к сохранению
    metrics = {
        "model_version": "lgbm-uci-v1-2026-10-10",
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "n_train": len(X_train), "n_test": len(X_test), "base_rate": float(y_train.mean()),
        "cv_auc_lgbm": cv_auc_lgbm, "cv_auc_logreg": cv_auc_logreg,
        "holdout_auc": holdout_auc,
        "holdout_pr_auc": average_precision_score(y_test, test_preds),
        "holdout_brier": brier_score_loss(y_test, test_preds),
        "red": {"threshold": red_th, "precision": y_test[red_mask].mean(), "recall": y_test[red_mask].sum()/y_test.sum(), "flagged_ratio": red_mask.mean()},
        "yellow_or_red": {"threshold": yellow_th, "precision": y_test[yellow_or_red_mask].mean(), "recall": y_test[yellow_or_red_mask].sum()/y_test.sum(), "flagged_ratio": yellow_or_red_mask.mean()},
        "top10_capture": top10_capture,
        "hidden_defaulters": {"capture_in_top10": hd_top10, "capture_in_top20": hd_top20},
        "rule_vs_model": {"rule_prec": rule_prec, "rule_rec": rule_rec, "model_prec": model_prec, "model_rec": model_rec},
        "horizon": horizons_auc,
        "reference_with_limit_and_levels": roc_auc_score(y_test, ref_preds),
        "fairness": fairness,
        "feature_importance": dict(zip(FEATURES, fi)),
        "reliability": {"pred": prob_pred.tolist(), "true": prob_true.tolist()}
    }

    meta = {
        "model_version": "lgbm-uci-v1-2026-10-10",
        "features": FEATURES,
        "thresholds": {"red": red_th, "yellow": yellow_th},
        "horizon_months": 1
    }

    calibration = {"x": cal_x.tolist(), "y": cal_y.tolist()}

    print("Сохранение артефактов...")
    os.makedirs('artifacts', exist_ok=True)
    final_model.booster_.save_model('artifacts/model.txt')
    
    with open('artifacts/metrics.json', 'w') as f: json.dump(metrics, f, indent=2)
    with open('artifacts/meta.json', 'w') as f: json.dump(meta, f, indent=2)
    with open('artifacts/calibration.json', 'w') as f: json.dump(calibration, f, indent=2)

    print(f"Готово! Holdout AUC: {holdout_auc:.4f}, Red Precision: {y_test[red_mask].mean():.2f}")
    print("Артефакты сохранены в model/artifacts/")

if __name__ == "__main__":
    main()