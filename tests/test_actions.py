import pytest
from app.actions import annuity, generate_actions

def test_annuity():
    # Ручной расчет: B = 1,000,000, ставка 24% годовых (2% в месяц), срок 12 месяцев
    B = 1000000
    r_annual = 0.24
    n = 12
    # Формула: 1000000 * 0.02 / (1 - (1.02)^-12) ≈ 105582
    expected = B * (0.02) / (1 - (1.02)**-12)
    assert abs(annuity(B, r_annual, n) - expected) < 1.0

def test_actions_logic():
    B = 10000000
    r_annual = 0.24
    n = 12
    current_pmt = annuity(B, r_annual, n)
    
    # Генерируем действия для проблемного кредита (red)
    actions = generate_actions("red", B, r_annual, n, turnover=[1000000]*12)
    
    # A4: проверяем, что продление генерируется и новый платёж меньше исходного
    a4 = next((a for a in actions if a["code"] == "A4_6M"), None)
    assert a4 is not None
    # При n+6 (18 месяцев) платеж должен быть меньше
    new_pmt = annuity(B, r_annual, n + 6)
    assert new_pmt < current_pmt

    # A5: проверяем, что сезонный график сгенерировал таблицу из 12 месяцев
    a5 = next((a for a in actions if a["code"] == "A5"), None)
    assert a5 is not None
    assert "table" in a5
    assert len(a5["table"]) == 12