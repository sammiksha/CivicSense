from __future__ import annotations
import hashlib, json, sqlite3
from contextlib import closing
from datetime import datetime, timezone
from . import config


def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with closing(_conn()) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS audit(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, customer_id TEXT, inputs_hash TEXT,
            product_json TEXT, decision TEXT, rules_json TEXT, data_source TEXT, data_window TEXT,
            model_version TEXT, result_json TEXT, explanations_json TEXT)""")
        c.commit()


def log(result: dict, explanation: dict | None = None, mode: str = "rm") -> int:
    init()
    inputs = json.dumps({"p": result["product"], "c": result["customer"]}, sort_keys=True)
    expl = {mode: explanation} if explanation else {}
    with closing(_conn()) as c:
        cur = c.execute(
            "INSERT INTO audit(ts,customer_id,inputs_hash,product_json,decision,rules_json,data_source,data_window,model_version,result_json,explanations_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), result["customer"]["id"], hashlib.sha256(inputs.encode()).hexdigest()[:16],
             json.dumps(result["product"]), result["decision"], json.dumps(result["rules"]), result["data_source"],
             json.dumps(result["data_window"]), config.model_version(), json.dumps(result), json.dumps(expl)))
        c.commit()
        return cur.lastrowid


def get(audit_id: int) -> dict | None:
    init()
    with closing(_conn()) as c:
        r = c.execute("SELECT * FROM audit WHERE id=?", (audit_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["result"] = json.loads(d.pop("result_json"))
    d["explanations"] = json.loads(d.pop("explanations_json") or "{}")
    return d


def set_explanation(audit_id: int, mode: str, explanation: dict):
    rec = get(audit_id)
    ex = rec["explanations"]
    ex[mode] = explanation
    with closing(_conn()) as c:
        c.execute("UPDATE audit SET explanations_json=? WHERE id=?", (json.dumps(ex), audit_id))
        c.commit()


def list_recent(n: int = 20) -> list[dict]:
    init()
    with closing(_conn()) as c:
        rows = c.execute("SELECT id,ts,customer_id,decision,data_source,model_version,inputs_hash FROM audit ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return [dict(r) for r in rows]
