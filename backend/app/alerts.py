"""Risk Alerts: generated from deterministic conditions only.
No LLM. Alerts fire when thresholds are crossed.
"""
from __future__ import annotations
import sqlite3, json
from contextlib import closing
from datetime import datetime, timezone
from . import config


def _conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_alerts():
    with closing(_conn()) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT, assessment_id INTEGER,
            alert_type TEXT, severity TEXT,
            title TEXT, message TEXT,
            trigger_value TEXT, threshold TEXT,
            product_id TEXT, recommended_action TEXT,
            is_read INTEGER DEFAULT 0,
            ts TEXT)""")
        c.commit()


def generate_alerts(customer: dict, product: dict, assessment: dict, audit_id: int) -> list[dict]:
    """Generate deterministic alerts from the assessment result."""
    alerts = []
    rules_result = assessment.get("rules", [])
    metrics = assessment.get("metrics", {})
    bp = assessment.get("breaking_point", {})
    decision = assessment.get("decision", "SUITABLE")

    # Alert 1: Suitability status not SUITABLE
    if decision == "MISMATCH":
        alerts.append(_make(customer["id"], audit_id, "SUITABILITY", "HIGH",
                            "Suitability Mismatch",
                            "This product has been assessed as MISMATCH under your current profile and the configured suitability rules.",
                            decision, "SUITABLE",
                            "Review the product with your Relationship Manager before proceeding."))
    elif decision == "REVIEW":
        alerts.append(_make(customer["id"], audit_id, "SUITABILITY", "WARNING",
                            "Suitability Under Review",
                            "This product requires review under your current profile.",
                            decision, "SUITABLE",
                            "Discuss the flagged rules with your Relationship Manager."))

    # Alert 2: Concentration
    from .engines.suitability import evaluate
    conc_rule = next((r for r in rules_result if r.get("rule_id") == "R4_CONCENTRATION"), None)
    if conc_rule and conc_rule.get("status") != "SUITABLE":
        msg = conc_rule.get("message") or conc_rule.get("description") or ""
        val = str(conc_rule.get("customer_value", ""))
        alerts.append(_make(customer["id"], audit_id, "CONCENTRATION", "WARNING",
                            "Portfolio Concentration Alert",
                            f"Adding this product increases your {product.get('underlying', 'asset')} exposure above the configured limit. {msg}".strip(),
                            val, "50%",
                            "Consider reducing notional or diversifying the portfolio."))

    # Alert 3: Loss tolerance
    tail_loss = metrics.get("tail_loss_pct", 0)
    loss_tol = customer.get("loss_tolerance_pct", 5)
    if tail_loss > loss_tol:
        alerts.append(_make(customer["id"], audit_id, "LOSS_TOLERANCE", "WARNING",
                            "Loss Tolerance Exceeded",
                            f"The modeled tail loss ({tail_loss:.1f}%) exceeds your configured loss tolerance ({loss_tol:.1f}%).",
                            f"{tail_loss:.1f}%", f"{loss_tol:.1f}%",
                            "Review the product parameters or your risk profile with your RM."))

    # Alert 4: Breaking point proximity
    suitable_until = bp.get("suitable_until_pct")
    if suitable_until is not None and suitable_until > -15:
        alerts.append(_make(customer["id"], audit_id, "BREAKING_POINT", "INFO",
                            "Suitability Breaks at Shallow Decline",
                            f"The suitability status changes at a market movement of only {suitable_until:g}%, which is a relatively shallow decline.",
                            f"{suitable_until:g}%", "-15%",
                            "Ask your RM about repair options to improve resilience."))

    return alerts


def _make(customer_id, assessment_id, alert_type, severity, title, message, trigger, threshold, action):
    return {
        "customer_id": customer_id,
        "assessment_id": assessment_id,
        "alert_type": alert_type,
        "severity": severity,
        "title": title,
        "message": message,
        "trigger_value": str(trigger),
        "threshold": str(threshold),
        "recommended_action": action,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def save_alerts(alerts: list[dict]) -> list[int]:
    init_alerts()
    ids = []
    with closing(_conn()) as c:
        for a in alerts:
            existing = c.execute(
                "SELECT id FROM alerts WHERE customer_id=? AND title=? AND is_read=0",
                (a["customer_id"], a["title"])).fetchone()
            if existing:
                c.execute(
                    "UPDATE alerts SET assessment_id=?, message=?, trigger_value=?, threshold=?, ts=? WHERE id=?",
                    (a["assessment_id"], a["message"], a["trigger_value"], a["threshold"], a["ts"], existing[0]))
                ids.append(existing[0])
            else:
                cur = c.execute(
                    "INSERT INTO alerts(customer_id,assessment_id,alert_type,severity,title,message,trigger_value,threshold,recommended_action,ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (a["customer_id"], a["assessment_id"], a["alert_type"], a["severity"],
                     a["title"], a["message"], a["trigger_value"], a["threshold"],
                     a["recommended_action"], a["ts"]))
                ids.append(cur.lastrowid)
        c.commit()
    return ids


def get_alerts(customer_id: str | None = None, unread_only: bool = False) -> list[dict]:
    init_alerts()
    with closing(_conn()) as c:
        if customer_id and customer_id not in ("all", "*", ""):
            q = "SELECT * FROM alerts WHERE customer_id=?"
            params = [customer_id]
            if unread_only:
                q += " AND is_read=0"
        else:
            q = "SELECT * FROM alerts WHERE 1=1"
            params = []
            if unread_only:
                q += " AND is_read=0"
        q += " ORDER BY id DESC LIMIT 50"
        rows = c.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def mark_read(alert_id: int):
    init_alerts()
    with closing(_conn()) as c:
        c.execute("UPDATE alerts SET is_read=1 WHERE id=?", (alert_id,))
        c.commit()


def mark_all_read(customer_id: str | None = None):
    init_alerts()
    with closing(_conn()) as c:
        if customer_id and customer_id not in ("all", "*", ""):
            c.execute("UPDATE alerts SET is_read=1 WHERE customer_id=?", (customer_id,))
        else:
            c.execute("UPDATE alerts SET is_read=1")
        c.commit()


def unread_count(customer_id: str | None = None) -> int:
    init_alerts()
    with closing(_conn()) as c:
        if customer_id and customer_id not in ("all", "*", ""):
            return c.execute("SELECT COUNT(*) FROM alerts WHERE customer_id=? AND is_read=0", (customer_id,)).fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM alerts WHERE is_read=0").fetchone()[0]

