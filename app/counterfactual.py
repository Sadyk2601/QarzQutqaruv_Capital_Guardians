"""Path back to green: the smallest next payment that moves the borrower out of risk.

A model-based what-if (not a guarantee): we add a hypothetical next month and
re-score with the same Model 1.
"""
from app.scoring import delay_months

TEXT = {
    "en": {"ok": "If next month's payment is at least {x:,} UZS ({detail}) and on time, risk drops from {a}% to {b}% ({band}).",
           "partial": " Green is not reachable with one payment -> the payment size itself is the problem: offer the rescue plan.",
           "no": "Even a full on-time payment of {x:,} UZS ({detail}) keeps risk at {b}% -> the payment size is the problem: offer the rescue plan.",
           "inst": "the installment {i:,}", "arr": "the installment {i:,} + {r:,} of arrears"},
    "ru": {"ok": "Если в следующем месяце заплатить не меньше {x:,} сум ({detail}) и вовремя, риск упадёт с {a}% до {b}% ({band}).",
           "partial": " Одним платежом до зелёной зоны не дойти -> проблема в размере платежа: предложите план спасения.",
           "no": "Даже полный платёж {x:,} сум ({detail}) вовремя оставляет риск {b}% -> проблема в размере платежа: предложите план спасения.",
           "inst": "обычный платёж {i:,}", "arr": "обычный платёж {i:,} + {r:,} долга"},
    "uz": {"ok": "Agar keyingi oy kamida {x:,} so'm ({detail}) o'z vaqtida to'lansa, xavf {a}% dan {b}% gacha tushadi ({band}).",
           "partial": " Bitta to'lov bilan yashil zonaga chiqib bo'lmaydi -> muammo to'lov miqdorida: qutqaruv rejasini taklif qiling.",
           "no": "Hatto {x:,} so'm ({detail}) to'liq va o'z vaqtida to'langanda ham xavf {b}% bo'lib qoladi -> muammo to'lov miqdorida: qutqaruv rejasini taklif qiling.",
           "inst": "odatiy to'lov {i:,}", "arr": "odatiy to'lov {i:,} + {r:,} qarz"},
}


def _detail(t, x, installment):
    return t["inst"].format(i=x) if x <= installment else t["arr"].format(i=installment, r=x - installment)


def path_to_green(engine, history, installment, segment, prob_now, lang="en"):
    last = history[-1]
    arrears = max(0, last["due"] - last["paid"])
    due_next = installment + arrears
    t = TEXT.get(lang, TEXT["en"])
    payments, rows = [], []
    for step in range(0, 21):
        x = int(due_next * step / 20)
        if x >= due_next:
            days = 0
        elif x >= installment:
            days = last["days_late"]
        else:
            days = min(365, last["days_late"] + 30)
        payments.append(x)
        rows.append(engine.history_features(history + [{"due": due_next, "paid": x, "days_late": days}]))
    probs = [s["prob"] for s in engine.score_many(rows)]  # one batch call for all 21 what-ifs
    best = {}
    for step, (x, p) in enumerate(zip(payments, probs)):
        band = engine.band(p, segment)
        if band == "green" and "green" not in best:
            best["green"] = (x, p)
        if band in ("green", "yellow") and "yellow" not in best:
            best["yellow"] = (x, p)
        if step == 20:
            best["full"] = (x, p, band)
    target = "green" if "green" in best else ("yellow" if "yellow" in best else None)
    if target and best[target][1] <= prob_now - 0.02:
        x, p = best[target]
        text = t["ok"].format(x=x, detail=_detail(t, x, installment), a=int(round(prob_now * 100)),
                              b=int(round(p * 100)), band=target)
        if target != "green":
            text += t["partial"]
        return {"possible": target == "green", "target_band": target, "min_payment": x,
                "risk_now": round(prob_now, 4), "risk_after": round(p, 4), "text": text,
                "note": "Model-based what-if, not a guarantee."}
    x, p, _ = best["full"]
    return {"possible": False, "min_payment": x, "risk_now": round(prob_now, 4), "risk_after": round(p, 4),
            "text": t["no"].format(x=x, detail=_detail(t, x, installment), b=int(round(p * 100))),
            "note": "Model-based what-if, not a guarantee."}
