"""Action ladder (soft -> hard), the optimized rescue plan and the offer letter.

All money in UZS. Every action is a recommendation; hard steps need the
credit committee. Assumptions are named in the output, not hidden.
"""
import numpy as np

AFFORDABILITY_MAX = 0.30  # ASSUMPTION: loan payment should not exceed 30% of monthly income
EXTENSIONS = [0, 3, 6, 9, 12]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
LAST_MONTH_IDX = 8  # history ends in Sep 2026 -> the plan starts in Oct 2026

# Typical seasonality (Jan..Dec) by business type; same table as the demo generator.
SEASONALITY = {
    "tailoring":        [0.8, 0.8, 1.25, 1.25, 1.2, 0.9, 0.85, 1.2, 1.2, 1.0, 0.8, 0.75],
    "greenhouse":       [0.7, 1.2, 1.3, 1.3, 1.25, 1.0, 0.55, 0.5, 0.8, 0.95, 0.85, 0.6],
    "livestock":        [0.85, 0.85, 0.9, 0.9, 0.95, 1.2, 1.25, 1.2, 0.9, 0.9, 0.9, 1.2],
    "retail_shop":      [0.9, 0.9, 1.2, 0.95, 0.95, 0.95, 0.95, 0.95, 1.0, 1.0, 1.05, 1.2],
    "bakery":           [1.0, 1.0, 1.05, 1.0, 1.0, 0.95, 0.95, 0.95, 1.0, 1.0, 1.0, 1.1],
    "wedding_services": [0.45, 0.45, 0.8, 0.95, 1.35, 1.35, 1.0, 1.1, 1.35, 1.35, 0.95, 0.9],
    "other":            [1.0] * 12,
}


def annuity(B, annual_rate, n):
    if n <= 0:
        return 0.0
    r = annual_rate / 12
    return B / n if r == 0 else B * r / (1 - (1 + r) ** -n)


def season(biz):
    return SEASONALITY.get(biz, SEASONALITY["other"])


def future_months(n, start=LAST_MONTH_IDX + 1):
    return [(start + m) % 12 for m in range(n)]


def income_level(turnover, biz, last_idx=LAST_MONTH_IDX):
    """Deseasonalised income level = average of the last 6 months.
    ASSUMPTION: income returns to its last-6-month level, with the usual seasonality."""
    if not turnover:
        return None
    s = season(biz)
    t = list(turnover)[-6:]
    idx = [(last_idx - (len(t) - 1 - i)) % 12 for i in range(len(t))]
    return float(np.mean([v / s[m] for v, m in zip(t, idx)]))


def burden(payments, level, biz, start=LAST_MONTH_IDX + 1):
    s = season(biz)
    return [p / (level * s[m]) for p, m in zip(payments, future_months(len(payments), start))]


def rescue_plan(B, annual_rate, n, level, biz):
    """Smallest term extension k where a season-shaped schedule keeps every
    payment <= AFFORDABILITY_MAX of expected income, with present value = B
    (bank-neutral at the contract rate)."""
    r = annual_rate / 12
    current = annuity(B, annual_rate, n)
    before = max(burden([current] * min(12, n), level, biz))
    for k in EXTENSIONS:
        N = n + k
        s = np.array([season(biz)[m] for m in future_months(N)])
        w = np.clip(s / s.mean(), 0.5, 1.6)
        disc = (1 + r) ** -np.arange(1, N + 1)
        base = B / float((w * disc).sum())
        pay = base * w
        ratios = burden(pay.tolist(), level, biz)
        if max(ratios) <= AFFORDABILITY_MAX:
            months = future_months(12)
            table = [{"month": MONTHS[m], "expected_income": int(level * season(biz)[m]),
                      "payment": int(pay[i]), "burden_pct": round(ratios[i] * 100, 1)} for i, m in enumerate(months)]
            return {"feasible": True, "extension_months": k, "new_term_months": N,
                    "max_burden_before_pct": round(before * 100, 1), "max_burden_after_pct": round(max(ratios) * 100, 1),
                    "pv_check": round(float((pay * disc).sum())), "outstanding": int(B),
                    "extra_interest": int(pay.sum() - current * n), "table": table}
    return {"feasible": False, "max_burden_before_pct": round(before * 100, 1),
            "text": "No affordable plan within +12 months -> credit committee: deeper restructuring / collateral review."}


def ladder(band, B, annual_rate, n, installment, biz, turnover=None):
    if band == "green":
        return [{"code": "monitor", "level": "soft", "needs_committee": False, "title": "Monitor",
                 "details": "Green zone: no action, the system keeps watching."}]
    level = income_level(turnover, biz)
    current = annuity(B, annual_rate, n)
    acts = [{"code": "call", "level": "soft", "needs_committee": False, "title": "Call and find out the reason",
             "details": "Ask what changed in the business; agree on the next payment date."}]

    if level:
        s = season(biz)
        nxt = future_months(12)
        strong = [MONTHS[m] for m in nxt if s[m] >= 1.15]
        weak = [MONTHS[m] for m in nxt if s[m] <= 0.85]
        if strong:
            extra = int(installment * 0.5)
            acts.append({"code": "prepay_strong_months", "level": "soft", "needs_committee": False,
                         "title": "Pay ahead in strong months",
                         "details": f"In the strong months ({', '.join(strong)}) pay +{extra:,} UZS extra each "
                                    f"to build a buffer{' for the weak months (' + ', '.join(weak) + ')' if weak else ''}. "
                                    "Contract unchanged."})

    if band == "red":
        for h in (1, 2):
            new = annuity(B * (1 + annual_rate / 12) ** h, annual_rate, n)
            acts.append({"code": f"holiday_{h}m", "level": "medium", "needs_committee": True,
                         "title": f"Payment holiday ({h} month{'s' if h > 1 else ''})",
                         "details": f"No payment for {h} month(s), then {int(new):,} UZS/month (now {int(current):,}). "
                                    f"Extra interest {int(new * n - current * n):,} UZS."})
        for k in (6, 12):
            new = annuity(B, annual_rate, n + k)
            acts.append({"code": f"extend_{k}m", "level": "hard", "needs_committee": True,
                         "title": f"Extend term (+{k} months)",
                         "details": f"Payment {int(current):,} -> {int(new):,} UZS/month. "
                                    f"Extra interest {int(new * (n + k) - current * n):,} UZS."})
        if level:
            plan = rescue_plan(B, annual_rate, n, level, biz)
            act = {"code": "rescue_plan", "level": "hard", "needs_committee": True,
                   "title": "Optimized rescue plan (season-shaped, bank-neutral)", "plan": plan}
            if plan["feasible"]:
                act["details"] = (f"+{plan['extension_months']} months, payments follow the business season. "
                                  f"Max burden {plan['max_burden_before_pct']}% -> {plan['max_burden_after_pct']}% of income. "
                                  f"Bank: present value unchanged ({plan['pv_check']:,} = outstanding {plan['outstanding']:,}).")
            else:
                act["details"] = plan["text"]
            acts.append(act)
    return acts


LETTER = {
    "en": ("Dear {name},\n\nWe noticed that paying your loan has become harder in recent months. "
           "MKBANK can offer you a new schedule: the term is extended by {k} months and your payments follow "
           "the season of your business ({first}).\n\nPlease contact your loan officer {officer} to discuss it. "
           "The offer takes effect after approval by the credit committee.\n\nMKBANK"),
    "ru": ("Уважаемый(ая) {name}!\n\nМы заметили, что в последние месяцы вам стало труднее платить по кредиту. "
           "MKBANK может предложить новый график: срок продлевается на {k} мес., а платежи подстраиваются "
           "под сезон вашего бизнеса ({first}).\n\nСвяжитесь, пожалуйста, с вашим кредитным специалистом {officer}. "
           "Предложение вступает в силу после одобрения кредитного комитета.\n\nMKBANK"),
    "uz": ("Hurmatli {name}!\n\nSo'nggi oylarda kredit to'lovlarini to'lash siz uchun qiyinlashganini ko'rdik. "
           "MKBANK sizga yangi to'lov jadvalini taklif qilishi mumkin: muddat {k} oyga uzaytiriladi, to'lovlar esa "
           "biznesingiz mavsumiga moslashtiriladi ({first}).\n\nIltimos, kredit xodimingiz {officer} bilan bog'laning. "
           "Taklif kredit qo'mitasi tasdiqlaganidan keyin kuchga kiradi.\n\nMKBANK"),
}


def offer_letter(name, plan, officer, lang="en"):
    if not plan or not plan.get("feasible"):
        return None
    first = "; ".join(f"{row['month']}: {row['payment']:,} UZS" for row in plan["table"][:3])
    return LETTER.get(lang, LETTER["en"]).format(name=name, k=plan["extension_months"], first=first,
                                                 officer=officer or "-")
