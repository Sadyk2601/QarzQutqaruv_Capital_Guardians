import os
import sqlite3
import pytest
import app.audit  # Импортируем сам модуль, чтобы поменять его переменную напрямую
from app.audit import log_event, verify

def test_audit_chain():
    # Явно указываем модулю использовать тестовую базу
    app.audit.AUDIT_DB_PATH = "test_audit.db"
    
    if os.path.exists("test_audit.db"):
        os.remove("test_audit.db")
        
    # Записываем два легальных события
    log_event("SCORE", "TEST", "DEMO-001", {"x": 1}, "v1")
    log_event("DECISION", "OFFICER", "DEMO-001", {"action": "A1"}, "v1")
    
    # Цепочка должна быть валидной
    res = verify()
    assert res["ok"] is True
    assert res["n"] == 2
    
    # Имитируем хакерскую подмену данных прямо в SQLite
    conn = sqlite3.connect("test_audit.db")
    c = conn.cursor()
    c.execute("UPDATE audit SET payload = '{\"x\": 999}' WHERE id = 1")
    conn.commit()
    conn.close()
    
    # Теперь верификация должна вернуть false
    res_bad = verify()
    assert res_bad["ok"] is False
    assert res_bad["first_bad_id"] == 1
    
    # Убираем за собой
    if os.path.exists("test_audit.db"):
        os.remove("test_audit.db")