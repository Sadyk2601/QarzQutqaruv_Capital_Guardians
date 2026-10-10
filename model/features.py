"""Own-norm features: compare a borrower with their OWN payment history.

One function is shared by training (UCI data) and the server (demo portfolio,
jury input), so the model always sees features computed the same way.
Input arrays go from the oldest month to the newest one.
"""
import numpy as np

FEATURES = [
    "delay_last", "delay_max_recent", "n_delay_months", "delay_trend",
    "paid_last_vs_norm", "paid_recent_vs_norm", "cover_last", "cover_mean",
    "cover_drop", "due_growth", "zero_pay_months", "decline_streak",
]
# Direction of each feature for the monotone model: +1 = more of it can only raise risk.
MONOTONE = {
    "delay_last": 1, "delay_max_recent": 1, "n_delay_months": 1, "delay_trend": 1,
    "paid_last_vs_norm": -1, "paid_recent_vs_norm": -1, "cover_last": -1, "cover_mean": -1,
    "cover_drop": 1, "due_growth": 1, "zero_pay_months": 1, "decline_streak": 1,
}
# paid_cv (payment variability) is computed but not used: a constant payment is normal
# for an installment loan but unusual for a credit card, so it does not transfer.

EPS = 1.0
WINDOW = 6


def make_features(due, paid, delay) -> dict:
    """due / paid in money, delay in whole months overdue (0..9). Length 3..12."""
    due = np.asarray(due, dtype=float)[-WINDOW:]
    paid = np.asarray(paid, dtype=float)[-WINDOW:]
    delay = np.asarray(delay, dtype=float)[-WINDOW:]
    if len(due) < 3:
        raise ValueError("at least 3 months of history are needed")

    old, recent = slice(None, -2), slice(-2, None)

    # Share of the amount due that was paid; nothing due counts as fully covered.
    with np.errstate(divide="ignore", invalid="ignore"):
        cover = np.where(due > 0, np.clip(paid / np.where(due > 0, due, 1.0), 0, 2), 1.0)

    decline_streak = 0
    for i in range(len(paid) - 1, 0, -1):
        if paid[i] < paid[i - 1]:
            decline_streak += 1
        else:
            break

    return {
        "delay_last": float(delay[-1]),
        "delay_max_recent": float(delay[recent].max()),
        "n_delay_months": float((delay > 0).sum()),
        "delay_trend": float(delay[recent].mean() - delay[old].mean()),
        "paid_last_vs_norm": float(np.clip((paid[-1] + EPS) / (np.median(paid[old]) + EPS), 0, 10)),
        "paid_recent_vs_norm": float(np.clip((paid[recent].mean() + EPS) / (paid[old].mean() + EPS), 0, 10)),
        "cover_last": float(cover[-1]),
        "cover_mean": float(cover.mean()),
        "cover_drop": float(cover[old].mean() - cover[recent].mean()),
        "due_growth": float(np.clip((due[-1] + EPS) / (due[old].mean() + EPS), 0, 10)),
        "paid_cv": float(np.clip(paid.std() / (paid.mean() + EPS), 0, 5)),
        "zero_pay_months": float(((paid == 0) & (due > 0)).sum()),
        "decline_streak": float(decline_streak),
    }
