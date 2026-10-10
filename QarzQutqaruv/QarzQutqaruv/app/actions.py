import numpy as np

AFFORDABILITY_MAX = 0.30  # Константа допущения посильности кредита

def annuity(B, r_annual, n):
    """Расчет аннуитетного платежа"""
    if n <= 0: return 0
    r = r_annual / 12
    return B * r / (1 - (1 + r)**-n)

def check_affordability(payment_schedule, mean_turnover, s_indices):
    """Проверка посильности платежа, возвращает список флагов (True если > 30%)"""
    flags = []
    for m, pmt in enumerate(payment_schedule):
        s = s_indices[m % len(s_indices)]
        expected_turnover = mean_turnover * s
        ratio = pmt / expected_turnover if expected_turnover > 0 else 1.0
        flags.append(ratio > AFFORDABILITY_MAX)
    return flags

def generate_actions(band, outstanding, annual_rate, remaining_months, turnover=None):
    if band == "green":
        return [{
            "code": "A0", "level": "soft", "needs_committee": False,
            "title": "Monitor", "details": "Borrower is in the green zone. No action required."
        }]

    actions = []
    r = annual_rate / 12
    B = outstanding
    n = remaining_months
    current_pmt = annuity(B, annual_rate, n)

    # A1: Позвонить (желтая и красная зоны)
    actions.append({
        "code": "A1", "level": "soft", "needs_committee": False,
        "title": "Call and investigate",
        "details": "EN: Call to find out the reason. RU: Позвонить, узнать причину. UZ: Qo'ng'iroq qilib sababini bilish."
    })

    if turnover and len(turnover) == 12:
        mean_turnover = np.mean(turnover)
        if mean_turnover > 0:
            s_indices = [t / mean_turnover for t in turnover]
            
            # A2: Досрочное погашение в сильные месяцы (желтая и красная)
            strong_months = [i for i, s in enumerate(s_indices) if s >= 1.15]
            if strong_months:
                extra_pmt = current_pmt * 0.5
                actions.append({
                    "code": "A2", "level": "soft", "needs_committee": False,
                    "title": "Prepay in strong months",
                    "details": f"Offer to pay extra {int(extra_pmt):,} UZS during strong seasonal months to build a buffer. Contract remains unchanged."
                })

            if band == "red":
                # A5: Сезонный график
                w_m = [np.clip(s, 0.5, 1.6) for s in s_indices]
                # Приведенная стоимость для сохранения нейтральности для банка
                pv_factors = sum([w_m[m] / ((1 + r)**(m + 1)) for m in range(min(12, n))])
                base = B / pv_factors if pv_factors > 0 else 0
                
                if base > 0:
                    schedule = [base * w_m[m] for m in range(min(12, n))]
                    affordability = check_affordability(schedule, mean_turnover, s_indices)
                    
                    table_data = [{"month": m+1, "payment": int(pmt), "warning": warn} 
                                  for m, (pmt, warn) in enumerate(zip(schedule, affordability))]
                    
                    actions.append({
                        "code": "A5", "level": "hard", "needs_committee": True,
                        "title": "Seasonal Schedule",
                        "details": f"Adjust payments to match business seasonality. PV equals outstanding amount. Assumption: max affordability = {AFFORDABILITY_MAX*100}%.",
                        "table": table_data
                    })

    if band == "red":
        # A3: Кредитные каникулы (1 или 2 месяца)
        for h in [1, 2]:
            B_h = B * (1 + r)**h
            new_pmt = annuity(B_h, annual_rate, n)
            extra_interest = ((new_pmt * n) - (current_pmt * n)) / B * 100 if B > 0 else 0
            
            actions.append({
                "code": f"A3_{h}M", "level": "medium", "needs_committee": True,
                "title": f"Payment Holiday ({h} months)",
                "details": f"New payment: {int(new_pmt):,} UZS. Client will overpay by {extra_interest:.1f}% extra."
            })

        # A4: Продление срока (6 или 12 месяцев)
        for k in [6, 12]:
            new_pmt = annuity(B, annual_rate, n + k)
            extra_interest = ((new_pmt * (n + k)) - (current_pmt * n)) / B * 100 if B > 0 else 0
            
            if new_pmt < current_pmt: # Продление имеет смысл только если платеж падает
                actions.append({
                    "code": f"A4_{k}M", "level": "medium", "needs_committee": True,
                    "title": f"Extend Term (+{k} months)",
                    "details": f"New payment: {int(new_pmt):,} UZS. Client will overpay by {extra_interest:.1f}% extra."
                })

    return actions