"""Plain-language reasons for the top risk factors (EN / RU / UZ).

{v} = months or counts, {pct} = value x 100 as a percentage, {pp} = points.
"""
REASONS = {
    "delay_last": {
        "en": "Currently {v} month(s) behind on payments",
        "ru": "Сейчас просрочка {v} мес.",
        "uz": "Hozir to'lov {v} oyga kechikkan",
    },
    "delay_max_recent": {
        "en": "Up to {v} month(s) late in the last 2 months",
        "ru": "За последние 2 месяца просрочка доходила до {v} мес.",
        "uz": "Oxirgi 2 oyda kechikish {v} oygacha yetgan",
    },
    "n_delay_months": {
        "en": "Late in {v} of the last 6 months",
        "ru": "Просрочка в {v} из последних 6 месяцев",
        "uz": "Oxirgi 6 oyning {v} tasida kechikish bo'lgan",
    },
    "delay_trend": {
        "en": "Delays are growing: +{v} month(s) versus earlier months",
        "ru": "Просрочки растут: +{v} мес. по сравнению с прошлыми месяцами",
        "uz": "Kechikishlar o'smoqda: oldingi oylarga nisbatan +{v} oy",
    },
    "paid_last_vs_norm": {
        "en": "Last payment was {pct}% of this borrower's usual payment",
        "ru": "Последний платёж — {pct}% от обычного платежа этого заёмщика",
        "uz": "Oxirgi to'lov qarzdorning odatiy to'lovining {pct}% ini tashkil etdi",
    },
    "paid_recent_vs_norm": {
        "en": "Last 2 payments averaged {pct}% of the borrower's own norm",
        "ru": "Последние 2 платежа в среднем — {pct}% от собственной нормы заёмщика",
        "uz": "Oxirgi 2 ta to'lov o'rtacha qarzdorning o'z me'yorining {pct}% i",
    },
    "cover_last": {
        "en": "Last payment covered only {pct}% of the amount due",
        "ru": "Последний платёж покрыл лишь {pct}% суммы к оплате",
        "uz": "Oxirgi to'lov to'lanishi kerak bo'lgan summaning atigi {pct}% ini qopladi",
    },
    "cover_mean": {
        "en": "On average only {pct}% of the amount due was paid",
        "ru": "В среднем оплачивалось лишь {pct}% суммы к оплате",
        "uz": "O'rtacha to'lanishi kerak bo'lgan summaning atigi {pct}% i to'langan",
    },
    "cover_drop": {
        "en": "Share of the amount due that gets paid fell by {pp} points",
        "ru": "Доля оплачиваемой суммы упала на {pp} п.п.",
        "uz": "To'lanayotgan summa ulushi {pp} punktga kamaydi",
    },
    "due_growth": {
        "en": "Amount due grew to {pct}% of the usual level (arrears are building up)",
        "ru": "Сумма к оплате выросла до {pct}% от обычной (копится долг)",
        "uz": "To'lanishi kerak bo'lgan summa odatdagining {pct}% igacha o'sdi (qarz yig'ilmoqda)",
    },
    "paid_cv": {
        "en": "Payments are unstable (variation {pct}%)",
        "ru": "Платежи нестабильны (разброс {pct}%)",
        "uz": "To'lovlar beqaror (o'zgaruvchanlik {pct}%)",
    },
    "zero_pay_months": {
        "en": "{v} month(s) with no payment at all",
        "ru": "{v} мес. без единого платежа",
        "uz": "{v} oy umuman to'lov qilinmagan",
    },
    "decline_streak": {
        "en": "Payments have fallen {v} months in a row",
        "ru": "Платежи падают {v} мес. подряд",
        "uz": "To'lovlar ketma-ket {v} oy kamaymoqda",
    },
}

NO_RISK = {
    "en": "No significant risk signals in the payment history",
    "ru": "В истории платежей нет значимых сигналов риска",
    "uz": "To'lov tarixida jiddiy xavf belgilari yo'q",
}


FACT_RULES = [  # descriptive "own norm" facts shown next to the model's reasons
    ("paid_last_vs_norm", lambda v: v < 0.8),
    ("paid_recent_vs_norm", lambda v: v < 0.8),
    ("cover_last", lambda v: v < 0.8),
    ("decline_streak", lambda v: v >= 2),
    ("due_growth", lambda v: v > 1.2),
    ("zero_pay_months", lambda v: v >= 1),
]


def own_norm_facts(features: dict, lang: str = "en", skip=()) -> list:
    return [reason_text(f, features[f], lang) for f, rule in FACT_RULES
            if f not in skip and f in features and rule(features[f])]


def _num(v):
    return str(int(round(v))) if abs(v - round(v)) < 0.05 else f"{v:.1f}"


def reason_text(feature: str, value: float, lang: str = "en") -> str:
    tpl = REASONS.get(feature, {}).get(lang) or REASONS.get(feature, {}).get("en") or f"{feature}: {value}"
    return tpl.format(v=_num(value), pct=int(round(value * 100)), pp=int(round(value * 100)))
