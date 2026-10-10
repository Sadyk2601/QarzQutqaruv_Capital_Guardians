import json
import random

def annuity(B, r_annual, n):
    """Расчет аннуитетного платежа"""
    r = r_annual / 12
    return B * r / (1 - (1 + r)**-n)

def main():
    random.seed(42) # Фиксируем seed, чтобы данные были стабильны
    
    regions = ["Tashkent", "Samarkand", "Bukhara", "Andijan", "Namangan", "Fergana", 
               "Kashkadarya", "Surkhandarya", "Khorezm", "Navoi", "Syrdarya", "Jizzakh", "Karakalpakstan", "Tashkent Region"]
    first_names = ["Aziz", "Malika", "Jamshid", "Rustam", "Nodira", "Bekzod", "Shahzod", "Gulnoza", "Timur"]
    
    # 12 множителей сезонности (январь .. декабрь)
    seasonality = {
        "tailoring": [0.8, 0.8, 1.2, 1.2, 1.2, 1.0, 0.9, 1.2, 1.2, 1.0, 0.9, 0.8],
        "greenhouse": [0.7, 1.2, 1.2, 1.2, 1.2, 1.0, 0.5, 0.5, 0.8, 0.9, 0.9, 0.8],
        "livestock": [0.9, 0.9, 0.9, 0.9, 0.9, 1.2, 1.2, 1.2, 0.9, 0.9, 0.9, 1.2],
        "retail_shop": [0.9, 0.9, 1.2, 0.9, 0.9, 0.9, 0.9, 0.9, 1.0, 1.0, 1.1, 1.3],
        "bakery": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        "wedding_services": [0.4, 0.4, 0.8, 0.9, 1.3, 1.3, 1.0, 1.1, 1.3, 1.3, 0.8, 0.6]
    }
    
    scenarios = ["healthy", "seasonal_stress", "deteriorating", "shock"]
    weights = [0.72, 0.10, 0.15, 0.03]
    
    # Месяцы: от октября 2025 до сентября 2026. Индексы от 0 (янв) до 11 (дек)
    calendar_months = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", 
                       "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
    month_indices = [9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7, 8]
    
    portfolio = []
    
    for i in range(500):
        is_dilnoza = (i == 0)
        borrower_id = f"DEMO-{i+1:03d}"
        
        # DEMO-001 - это всегда Дильноза из примера, остальные - случайные
        name = "Dilnoza R." if is_dilnoza else f"{random.choice(first_names)} {random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}."
        region = "Samarkand" if is_dilnoza else random.choice(regions)
        biz_type = "tailoring" if is_dilnoza else random.choice(list(seasonality.keys()))
        scenario = "deteriorating" if is_dilnoza else random.choices(scenarios, weights=weights)[0]
        
        if is_dilnoza:
            loan_amount, annual_rate, term_months, months_elapsed = 60000000, 0.22, 36, 14
            outstanding, inst = 41000000, 2290000
            base_turnover = 9100000
        else:
            loan_amount = random.randint(20, 200) * 1000000
            annual_rate = round(random.uniform(0.14, 0.28), 4)
            term_months = random.choice([24, 36])
            months_elapsed = random.randint(6, 20)
            inst = int(annuity(loan_amount, annual_rate, term_months))
            outstanding = int(loan_amount * (1 - months_elapsed/term_months))
            base_turnover = inst * random.uniform(3.0, 5.0)
            
        history = []
        turnover = []
        past_unpaid, days_late = 0, 0
        
        for m_idx, cal_str in zip(month_indices, calendar_months):
            s = seasonality[biz_type][m_idx]
            t_m = base_turnover * s * random.uniform(0.95, 1.05)
            
            # Применение сценариев
            is_recent = cal_str >= "2026-06"
            if scenario == "deteriorating" and is_recent:
                t_m *= random.uniform(0.4, 0.7) # Падение выручки на 30-60%
            elif scenario == "shock" and cal_str == "2026-09":
                t_m *= 0.1 # Внезапный обрыв
                
            turnover.append(int(t_m))
            
            due = inst + past_unpaid
            capacity = random.uniform(0.4, 0.6)
            
            if scenario == "healthy":
                paid = due
            elif scenario == "seasonal_stress":
                paid = min(due, int(t_m * capacity)) if s < 1.0 else due
            else:
                paid = min(due, int(t_m * capacity))
                
            if paid < due:
                past_unpaid = due - paid
                days_late = min(365, days_late + 30)
            else:
                past_unpaid = 0
                days_late = 0
                
            history.append({"due": int(due), "paid": int(paid), "days_late": int(days_late)})
            
        portfolio.append({
            "id": borrower_id, "name": name, "region": region, "business_type": biz_type,
            "loan_amount": loan_amount, "annual_rate": annual_rate, "term_months": term_months, 
            "months_elapsed": months_elapsed, "outstanding": outstanding, "installment": inst,
            "calendar_months": calendar_months, "history": history, "turnover": turnover, "scenario": scenario
        })
        
    with open("data/demo_portfolio.json", "w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
    print("Демо-портфель успешно сгенерирован: data/demo_portfolio.json")

if __name__ == "__main__":
    main()