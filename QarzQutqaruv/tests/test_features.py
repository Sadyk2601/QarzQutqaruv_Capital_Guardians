import pytest
from model.features import make_features

def test_stable_payer():
    # Стабильный плательщик: paid_last_vs_norm ≈ 1 и cover_drop ≈ 0
    due = [1000, 1000, 1000, 1000, 1000, 1000]
    paid = [1000, 1000, 1000, 1000, 1000, 1000]
    delay = [0, 0, 0, 0, 0, 0]
    
    feats = make_features(due, paid, delay)
    assert abs(feats["paid_last_vs_norm"] - 1.0) < 0.05
    assert abs(feats["cover_drop"] - 0.0) < 0.05

def test_declining_payer():
    # Падающий плательщик
    due = [1000, 1000, 1000, 1000, 1000, 1000]
    paid = [1000, 1000, 1000, 1000, 500, 200]
    delay = [0, 0, 0, 0, 1, 2]
    
    feats = make_features(due, paid, delay)
    assert feats["paid_last_vs_norm"] < 0.6
    assert feats["decline_streak"] >= 2

def test_zero_due_is_not_missed():
    # Если due == 0 везде, то cover = 1, и это не "пропуск"
    due = [0, 0, 0, 0, 0, 0]
    paid = [0, 0, 0, 0, 0, 0]
    delay = [0, 0, 0, 0, 0, 0]
    
    feats = make_features(due, paid, delay)
    assert feats["cover_mean"] == 1.0
    assert feats["zero_pay_months"] == 0