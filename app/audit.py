"""Hash-chained audit log (SQLite) + recorded action outcomes for Model 2.

Each record stores sha256(prev_hash + record). Changing any old record breaks
the chain, and verify() shows where. Production: append-only storage kept 5+ years.
"""
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = os.environ.get("AUDIT_DB_PATH") or str(Path(tempfile.gettempdir()) / "qarzqutqaruv_audit.db")
_outcomes_cache = None


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT, event TEXT, actor TEXT, borrower_id TEXT,
        payload TEXT, model_version TEXT, prev_hash TEXT, hash TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS outcomes (
        problem_type TEXT, action TEXT, success INTEGER DEFAULT 0, failure INTEGER DEFAULT 0,
        PRIMARY KEY (problem_type, action))""")
    return conn


def _hash(record: dict, prev_hash: str) -> str:
    body = json.dumps({k: record[k] for k in sorted(record) if k not in ("hash", "id")},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()


def log_event(event, actor, borrower_id, payload, model_version):
    with _conn() as conn:
        row = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = row[0] if row else "GENESIS"
        rec = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event,
               "actor": actor, "borrower_id": borrower_id,
               "payload": json.dumps(payload, ensure_ascii=False, sort_keys=True),
               "model_version": model_version, "prev_hash": prev}
        rec["hash"] = _hash(rec, prev)
        cur = conn.execute("INSERT INTO audit (ts_utc, event, actor, borrower_id, payload, model_version, prev_hash, hash) "
                           "VALUES (:ts_utc, :event, :actor, :borrower_id, :payload, :model_version, :prev_hash, :hash)", rec)
        rec["id"] = cur.lastrowid
    return rec


def verify():
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id")]
    prev = "GENESIS"
    for r in rows:
        if r["prev_hash"] != prev or _hash(r, prev) != r["hash"]:
            return {"ok": False, "n": len(rows), "first_bad_id": r["id"]}
        prev = r["hash"]
    return {"ok": True, "n": len(rows), "first_bad_id": None}


def recent(limit=50):
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))]


def add_outcome(problem_type, action, resolved: bool):
    global _outcomes_cache
    col = "success" if resolved else "failure"
    with _conn() as conn:
        conn.execute("INSERT OR IGNORE INTO outcomes (problem_type, action) VALUES (?, ?)", (problem_type, action))
        conn.execute(f"UPDATE outcomes SET {col} = {col} + 1 WHERE problem_type = ? AND action = ?",
                     (problem_type, action))
    _outcomes_cache = None


def outcome_counts():
    global _outcomes_cache
    if _outcomes_cache is None:
        with _conn() as conn:
            _outcomes_cache = {(t, a): (s, f) for t, a, s, f in conn.execute("SELECT * FROM outcomes")}
    return _outcomes_cache
