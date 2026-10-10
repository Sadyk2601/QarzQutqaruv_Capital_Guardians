import numpy as np

# Порядок фиксирован, сохраняется в meta.json
FEATURES = [
    "delay_last", "delay_max_recent", "n_delay_months", "delay_trend",
    "paid_last_vs_norm", "paid_recent_vs_norm", "cover_last", "cover_mean",
    "cover_drop", "due_growth", "paid_cv", "zero_pay_months", "decline_streak",
]

def make_features(due: list, paid: list, delay: list) -> dict:
    """Генерирует признаки из истории платежей."""
    due = np.array(due, dtype=float)
    paid = np.array(paid, dtype=float)
    delay = np.array(delay, dtype=float)

    # Берем последние min(L, 6) месяцев
    L = len(due)
    use_len = min(L, 6)
    due = due[-use_len:]
    paid = paid[-use_len:]
    delay = delay[-use_len:]

    # recent = последние 2 месяца, old = все месяцы до них
    recent_due, old_due = due[-2:], due[:-2]
    recent_paid, old_paid = paid[-2:], paid[:-2]
    recent_delay, old_delay = delay[-2:], delay[:-2]

    eps = 1.0

    # Вспомогательный массив cover (покрытие)
    cover = np.zeros_like(due)
    for i in range(len(due)):
        if due[i] == 0:
            cover[i] = 1.0
        else:
            cover[i] = np.clip(paid[i] / due[i], 0, 2)
            
    recent_cover, old_cover = cover[-2:], cover[:-2]

    # Расчет признаков
    delay_last = delay[-1]
    delay_max_recent = np.max(recent_delay)
    n_delay_months = np.sum(delay > 0)
    delay_trend = np.mean(recent_delay) - np.mean(old_delay)

    paid_last_vs_norm = np.clip((paid[-1] + eps) / (np.median(old_paid) + eps), 0, 10)
    paid_recent_vs_norm = np.clip((np.mean(recent_paid) + eps) / (np.mean(old_paid) + eps), 0, 10)

    cover_last = cover[-1]
    cover_mean = np.mean(cover)
    cover_drop = np.mean(old_cover) - np.mean(recent_cover)

    due_growth = np.clip((due[-1] + eps) / (np.mean(old_due) + eps), 0, 10)
    paid_cv = np.clip(np.std(paid) / (np.mean(paid) + eps), 0, 5)
    zero_pay_months = np.sum((paid == 0) & (due > 0))

    # decline_streak: сколько месяцев подряд в конце платёж уменьшался
    decline_streak = 0
    for i in range(len(paid) - 1, 0, -1):
        if paid[i] < paid[i - 1]:
            decline_streak += 1
        else:
            break

    # Возвращаем словарь строго в порядке FEATURES
    return {
        "delay_last": float(delay_last),
        "delay_max_recent": float(delay_max_recent),
        "n_delay_months": float(n_delay_months),
        "delay_trend": float(delay_trend),
        "paid_last_vs_norm": float(paid_last_vs_norm),
        "paid_recent_vs_norm": float(paid_recent_vs_norm),
        "cover_last": float(cover_last),
        "cover_mean": float(cover_mean),
        "cover_drop": float(cover_drop),
        "due_growth": float(due_growth),
        "paid_cv": float(paid_cv),
        "zero_pay_months": float(zero_pay_months),
        "decline_streak": float(decline_streak)
    }