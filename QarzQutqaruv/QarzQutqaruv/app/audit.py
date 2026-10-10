import sqlite3
import os
import json
import hashlib
from datetime import datetime, timezone

# Путь для базы данных (можно переопределить через env для Hugging Face)
AUDIT_DB_PATH = os.environ.get("AUDIT_DB_PATH", "/tmp/audit.db")

# Фикс для локальной работы на Windows: 
# если папки /tmp нет, сохраняем базу в текущую директорию
db_dir = os.path.dirname(AUDIT_DB_PATH)
if db_dir and not os.path.exists(db_dir):
    AUDIT_DB_PATH = "audit.db"

def init_db():
    conn = sqlite3.connect(AUDIT_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT,
            event TEXT,
            actor TEXT,
            borrower_id TEXT,
            payload TEXT,
            model_version TEXT,
            prev_hash TEXT,
            hash TEXT
        )
    ''')
    conn.commit()
    conn.close()

def compute_hash(record_dict, prev_hash):
    # Копируем запись, удаляем 'hash', если есть
    rec = record_dict.copy()
    rec.pop('hash', None)
    
    # Сериализуем данные строго для стабильности хеша
    payload_str = json.dumps(rec, sort_keys=True, ensure_ascii=False)
    data_to_hash = prev_hash + payload_str
    return hashlib.sha256(data_to_hash.encode('utf-8')).hexdigest()

def log_event(event, actor, borrower_id, payload_dict, model_version):
    init_db()
    conn = sqlite3.connect(AUDIT_DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    prev_hash = row[0] if row else "GENESIS"
    
    ts_utc = datetime.now(timezone.utc).isoformat()
    payload_str = json.dumps(payload_dict, ensure_ascii=False)
    
    record = {
        "ts_utc": ts_utc,
        "event": event,
        "actor": actor,
        "borrower_id": borrower_id,
        "payload": payload_str,
        "model_version": model_version,
        "prev_hash": prev_hash
    }
    
    new_hash = compute_hash(record, prev_hash)
    
    c.execute('''
        INSERT INTO audit (ts_utc, event, actor, borrower_id, payload, model_version, prev_hash, hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ts_utc, event, actor, borrower_id, payload_str, model_version, prev_hash, new_hash))
    
    conn.commit()
    inserted_id = c.lastrowid
    
    c.execute("SELECT * FROM audit WHERE id = ?", (inserted_id,))
    columns = [desc[0] for desc in c.description]
    saved_record = dict(zip(columns, c.fetchone()))
    
    conn.close()
    return saved_record

def verify():
    init_db()
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT * FROM audit ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    
    if not rows:
        return {"ok": True, "n": 0, "first_bad_id": None}
        
    expected_prev_hash = "GENESIS"
    
    for row in rows:
        record = dict(row)
        stored_hash = record.pop('hash', None)
        record_id = record.pop('id', None)  # Убираем id из данных для проверки хеша
        stored_prev_hash = record['prev_hash']
        
        if stored_prev_hash != expected_prev_hash:
            return {"ok": False, "n": len(rows), "first_bad_id": record_id}
            
        calculated_hash = compute_hash(record, stored_prev_hash)
        if calculated_hash != stored_hash:
            return {"ok": False, "n": len(rows), "first_bad_id": record_id}
            
        expected_prev_hash = stored_hash
        
    return {"ok": True, "n": len(rows), "first_bad_id": None}

def get_recent_logs(limit=50):
    init_db()
    conn = sqlite3.connect(AUDIT_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows