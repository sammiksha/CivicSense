from __future__ import annotations
from fastapi import FastAPI, File, HTTPException, UploadFile, Header
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from . import audit, config, auth, alerts as alert_store
from .agent import copilot
from .agent.session import get_session
from .agent.tools import find_customer, load_customers
from .engines.payoff import payoff_curve, scenario_table
from .engines.market_data import get_prices
from .engines.portfolio import portfolio_impact as calc_portfolio_impact, rupee_impact as calc_rupee_impact
from .engines.stress import regime_stress, stress_ladder
from .engines.twin import find_twin
from .extraction.term_sheet import extract_product, file_to_text
from .rag.store import get_kb
from .schemas import (
    AssessmentRequest, CopilotRequest, CustomerProfile, ExplainRequest, LoginRequest,
    PortfolioImpactRequest, ProductSpec, ScenarioRequest,
    TextRequest, RMNoteRequest,
)
from .services import report
from .services.assessment import assess
from .services.explain import explain
from .llm.client import get_llm

app = FastAPI(
    title="FinVision",
    version="1.0.0",
    description="FinVision — Understand Before You Invest. Explainable structured-product suitability platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _customer(req):
    c = req.customer or (find_customer(req.customer_id) if req.customer_id else None)
    if c is None:
        raise HTTPException(404, "customer not found; pass customer_id or customer")
    return c


def _require_auth(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    token = authorization[7:]
    user = auth.get_user(token)
    if user is None:
        raise HTTPException(401, "Invalid or expired session")
    return user


def _require_rm(authorization: Optional[str] = Header(None)) -> dict:
    user = _require_auth(authorization)
    if user["role"] != "rm":
        raise HTTPException(403, "RM access required")
    return user


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "FinVision",
        "version": "1.0.0",
        "llm_mode": "claude" if get_llm() else "offline",
        "model_version": config.model_version(),
        "kb_chunks": len(get_kb().chunks),
    }


# ── auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest):
    result = auth.login(req.email, req.password)
    if result is None:
        raise HTTPException(401, "Invalid credentials")
    return result


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        auth.logout(authorization[7:])
    return {"ok": True}


@app.get("/api/auth/demo-credentials")
def demo_credentials():
    return auth.list_demo_credentials()


@app.get("/api/auth/me")
def me(authorization: Optional[str] = Header(None)):
    user = _require_auth(authorization)
    return user


# ── customers ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/customers")
def customers():
    return [c.model_dump() for c in load_customers()]


@app.post("/api/v1/customers")
def create_customer(c: CustomerProfile):
    import json
    path = config.DATA_DIR / "samples" / "customers.json"
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not c.id:
        c.id = f"C{len(raw) + 101}"
    for existing in raw:
        if existing.get("id") == c.id:
            raise HTTPException(400, f"Customer ID {c.id} already exists")
    raw.append(c.model_dump())
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return c.model_dump()


@app.get("/api/v1/customers/{customer_id}")
def customer_get(customer_id: str):
    c = find_customer(customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    return c.model_dump()


@app.get("/api/v1/customers/{customer_id}/portfolio")
def customer_portfolio(customer_id: str):
    c = find_customer(customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    d = c.model_dump()
    return {
        "customer_id": customer_id,
        "portfolio_value": d["portfolio_value"],
        "holdings": d.get("holdings", []),
        "existing_exposures": d.get("existing_exposures", {}),
        "annual_income_inr": d.get("annual_income_inr"),
    }


@app.get("/api/v1/customers/{customer_id}/alerts")
def customer_alerts(customer_id: str, unread_only: bool = False):
    return {
        "alerts": alert_store.get_alerts(customer_id, unread_only=unread_only),
        "unread_count": alert_store.unread_count(customer_id),
    }


@app.post("/api/v1/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int):
    alert_store.mark_read(alert_id)
    return {"ok": True}


@app.post("/api/v1/alerts/mark-all-read")
def mark_all_alerts_read(customer_id: Optional[str] = None):
    alert_store.mark_all_read(customer_id)
    return {"ok": True}


# ── payoff ────────────────────────────────────────────────────────────────────

@app.post("/api/v1/payoff")
def payoff(req: ScenarioRequest):
    """Lightweight (no simulation): used by the live barrier slider."""
    return {"curve": payoff_curve(req.product), "scenarios": scenario_table(req.product, req.moves)}


# ── product extraction ────────────────────────────────────────────────────────

@app.post("/api/v1/product/extract-text")
def extract_text(req: TextRequest):
    return extract_product(req.text)


@app.post("/api/v1/product/extract-file")
async def extract_file(file: UploadFile = File(...)):
    text = file_to_text(file.filename or "", await file.read())
    if not text.strip():
        raise HTTPException(422, "no text could be read from the file")
    return {**extract_product(text), "chars_read": len(text)}


# ── assessment ────────────────────────────────────────────────────────────────

@app.post("/api/v1/assessment")
def assessment(req: AssessmentRequest):
    c = _customer(req)
    try:
        a = assess(req.product, c)
    except ValueError as e:
        raise HTTPException(422, str(e))
    ex = explain(a, req.mode)
    aid = audit.log(a, ex, req.mode)

    # Auto-generate risk alerts
    try:
        new_alerts = _build_alerts(c.model_dump(), req.product.model_dump(), a, aid)
        alert_store.save_alerts(new_alerts)
    except Exception:
        pass

    return {
        "audit_id": aid,
        "status": a["decision"],
        "flags": [r for r in a["rules"] if r["status"] != "SUITABLE"],
        "explanation": ex,
        "result": a,
    }


def _build_alerts(customer: dict, product: dict, assessment_result: dict, audit_id: int) -> list[dict]:
    """Build alerts from deterministic conditions."""
    alerts = []
    decision = assessment_result.get("decision", "SUITABLE")
    metrics = assessment_result.get("metrics", {})
    bp = assessment_result.get("breaking_point", {})
    rules_result = assessment_result.get("rules", [])
    tail_loss = metrics.get("tail_loss_pct", 0)
    loss_tol = customer.get("loss_tolerance_pct", 5)

    if decision == "MISMATCH":
        alerts.append({
            "customer_id": customer["id"], "assessment_id": audit_id,
            "alert_type": "SUITABILITY", "severity": "HIGH",
            "title": "Suitability Mismatch",
            "message": f"This product is assessed as MISMATCH under your current profile.",
            "trigger_value": "MISMATCH", "threshold": "SUITABLE",
            "recommended_action": "Review with your Relationship Manager before proceeding.",
            "ts": _now(),
        })
    elif decision == "REVIEW":
        alerts.append({
            "customer_id": customer["id"], "assessment_id": audit_id,
            "alert_type": "SUITABILITY", "severity": "WARNING",
            "title": "Suitability Under Review",
            "message": "This product requires review under your current profile.",
            "trigger_value": "REVIEW", "threshold": "SUITABLE",
            "recommended_action": "Discuss flagged rules with your RM.",
            "ts": _now(),
        })

    if tail_loss > loss_tol:
        alerts.append({
            "customer_id": customer["id"], "assessment_id": audit_id,
            "alert_type": "LOSS_TOLERANCE", "severity": "WARNING",
            "title": "Modeled Loss Exceeds Tolerance",
            "message": f"Modeled tail loss {tail_loss:.1f}% exceeds your tolerance of {loss_tol:.1f}%.",
            "trigger_value": f"{tail_loss:.1f}%", "threshold": f"{loss_tol:.1f}%",
            "recommended_action": "Consider a lower-risk product or reduce the notional amount.",
            "ts": _now(),
        })

    conc_rule = next((r for r in rules_result if r["rule_id"] == "R4_CONCENTRATION"), None)
    if conc_rule and conc_rule["status"] != "SUITABLE":
        alerts.append({
            "customer_id": customer["id"], "assessment_id": audit_id,
            "alert_type": "CONCENTRATION", "severity": "WARNING",
            "title": "Portfolio Concentration Alert",
            "message": f"Adding this product causes concentration above the configured limit. {conc_rule['message']}",
            "trigger_value": conc_rule["customer_value"], "threshold": "50%",
            "recommended_action": "Consider reducing the investment amount.",
            "ts": _now(),
        })

    suitable_until = bp.get("suitable_until_pct")
    if suitable_until is not None and abs(suitable_until) < 15:
        alerts.append({
            "customer_id": customer["id"], "assessment_id": audit_id,
            "alert_type": "BREAKING_POINT", "severity": "INFO",
            "title": "Suitability Changes at Shallow Decline",
            "message": f"Suitability status changes at only {suitable_until:g}% market movement.",
            "trigger_value": f"{suitable_until:g}%", "threshold": "-15%",
            "recommended_action": "Ask your RM about repair options.",
            "ts": _now(),
        })

    return alerts


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── explain ───────────────────────────────────────────────────────────────────

@app.post("/api/v1/explain")
def explain_again(req: ExplainRequest):
    rec = audit.get(req.audit_id)
    if not rec:
        raise HTTPException(404, "audit record not found")
    ex = explain(rec["result"], req.mode)
    audit.set_explanation(req.audit_id, req.mode, ex)
    return ex


# ── copilot ───────────────────────────────────────────────────────────────────

@app.post("/api/v1/copilot")
def copilot_ask(req: CopilotRequest):
    s = get_session(req.session_id)
    if req.product is not None:
        s.product = req.product
    if req.customer_id:
        c = find_customer(req.customer_id)
        if c is not None:
            s.customer = c
    if req.history:
        s.history = req.history

    # Normalize page_context — frontend may send a dict or a plain string
    page_ctx = req.page_context
    if isinstance(page_ctx, dict):
        # Extract the most useful fields for the agent
        view = page_ctx.get("view", "")
        decision = page_ctx.get("decision")
        bp = page_ctx.get("breaking_point")
        conc = page_ctx.get("portfolio_concentration")
        parts = [f"view:{view}"]
        if decision:
            parts.append(f"decision:{decision}")
        if bp is not None:
            parts.append(f"breaking_point_pct:{bp}")
        if conc is not None:
            parts.append(f"concentration_pct:{conc}")
        page_ctx = " | ".join(parts)

    return copilot.ask(s, req.message, req.mode, page_context=page_ctx)


# ── portfolio impact ──────────────────────────────────────────────────────────

@app.post("/api/v1/portfolio-impact")
def portfolio_impact_endpoint(req: PortfolioImpactRequest):
    c = find_customer(req.customer_id)
    if c is None:
        raise HTTPException(404, "customer not found")
    return calc_portfolio_impact(c.model_dump(), req.product.model_dump(), req.stress_shock_pct)


# ── rupee impact ──────────────────────────────────────────────────────────────

@app.post("/api/v1/rupee-impact")
def rupee_impact_endpoint(req: AssessmentRequest):
    c = _customer(req)
    try:
        a = assess(req.product, c)
    except ValueError as e:
        raise HTTPException(422, str(e))
    tail_loss = a["metrics"]["tail_loss_pct"]
    return calc_rupee_impact(req.product.model_dump(), tail_loss, c.model_dump())


# ── stress & regime ───────────────────────────────────────────────────────────

@app.post("/api/v1/stress-ladder")
def stress_ladder_endpoint(req: AssessmentRequest):
    c = _customer(req)
    rules = config.load_rules()
    return {"ladder": stress_ladder(req.product, c, rules)}


@app.post("/api/v1/regime-stress")
def regime_stress_endpoint(req: AssessmentRequest):
    c = _customer(req)
    rules = config.load_rules()
    return {"regimes": regime_stress(req.product, c, rules)}


# ── historical twin ───────────────────────────────────────────────────────────

@app.post("/api/v1/historical-twin")
def historical_twin_endpoint(req: ScenarioRequest):
    try:
        prices, source = get_prices(req.product.underlying)
        result = find_twin(req.product, prices)
        result["data_source"] = source
        return result
    except Exception as e:
        raise HTTPException(422, str(e))


# ── RM note ───────────────────────────────────────────────────────────────────

@app.post("/api/v1/rm-note")
def rm_note(req: RMNoteRequest):
    rec = audit.get(req.audit_id)
    if not rec:
        raise HTTPException(404, "audit record not found")
    # Store RM decision
    if req.rm_decision or req.rm_comments:
        _store_rm_decision(req.audit_id, req.rm_decision, req.rm_comments)
    # Build the note text
    a = rec["result"]
    ex = rec["explanations"].get("rm") or explain(a, "rm")
    note = _build_rm_note(req.audit_id, a, ex, req.rm_decision, req.rm_comments)
    return {"note": note, "audit_id": req.audit_id}


def _store_rm_decision(audit_id: int, decision: str | None, comments: str | None):
    rec = audit.get(audit_id)
    if rec:
        r = rec["result"]
        r["rm_decision"] = decision
        r["rm_comments"] = comments
        import json, sqlite3
        from contextlib import closing
        with closing(audit._conn()) as c:
            c.execute("UPDATE audit SET result_json=?,decision=? WHERE id=?",
                      (json.dumps(r), decision or r.get("decision", ""), audit_id))
            c.commit()


def _build_rm_note(audit_id: int, a: dict, ex: dict, rm_decision: str | None, rm_comments: str | None) -> str:
    p, c = a["product"], a["customer"]
    m = a["metrics"]
    bp = a["breaking_point"]
    rules = a["rules"]
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    note = f"""FinVision — RM Justification Note
Audit #{audit_id} | Generated: {ts}

═══════════════════════════════════════════════════════════════
CUSTOMER
═══════════════════════════════════════════════════════════════
ID: {c['id']} | Name: {c.get('name','—')} | Risk: {c['risk_appetite']}
Loss tolerance: {c['loss_tolerance_pct']}% | Horizon: {c['horizon_months']} months
Portfolio: ₹{c['portfolio_value']:,.0f}

═══════════════════════════════════════════════════════════════
PRODUCT
═══════════════════════════════════════════════════════════════
Type: {p['product_type']} | Underlying: {p['underlying']}
Notional: ₹{p['notional']:,.0f} | Tenor: {p['tenor_months']} months
Coupon: {p['coupon_pct']}% | Barrier: {p.get('barrier_pct','n/a')}% | Strike: {p['strike_pct']}%

═══════════════════════════════════════════════════════════════
ASSESSMENT RESULT
═══════════════════════════════════════════════════════════════
Decision: {a['decision']}
Data source: {a['data_source']} | Window: {a['data_window'][0]} to {a['data_window'][1]}

RULES FIRED:
"""
    for r in rules:
        note += f"  {r['rule_id']}: {r['status']} — {r['message']}\n"

    note += f"""
HISTORICAL REPLAY:
  Windows: {m['historical']['n_windows']} | Best: {m['historical']['best_pct']}% | Worst: {m['historical']['worst_pct']}%
  Avg: {m['historical']['avg_pct']}% | Loss-making: {m['historical']['pct_windows_loss']}%

TAIL LOSS: {m['tail_loss_pct']}%

BREAKING POINT:
  Suitable until: {bp.get('suitable_until_pct','n/a')}%
  Review from: {bp.get('review_from_pct','n/a')}%
  Mismatch from: {bp.get('mismatch_from_pct','n/a')}%

REPAIR OPTIONS:
"""
    for rep in a.get("repairs", []):
        note += f"  • {rep['description']} → {rep.get('decision_after','SUITABLE')}\n"
    if not a.get("repairs"):
        note += "  None required / none found within configured bounds\n"

    teachback = a.get("teachback")
    if teachback:
        note += f"\nTEACH-BACK: {teachback.get('score_text','n/a')} — {teachback.get('flag_message','')}\n"

    note += f"""
═══════════════════════════════════════════════════════════════
AI EXPLANATION (RM MODE)
═══════════════════════════════════════════════════════════════
{ex.get('text','—')}
Engine: {ex.get('engine','—')}

═══════════════════════════════════════════════════════════════
RM DECISION  (to be completed by Relationship Manager)
═══════════════════════════════════════════════════════════════
Decision: {rm_decision or '[Proceed / Modify / Decline]'}
Comments: {rm_comments or '[RM comments here]'}

IMPORTANT: FinVision provides decision support, not investment advice.
The RM is responsible for the final decision and recommendation.
Model version: {config.model_version()}
═══════════════════════════════════════════════════════════════
"""
    return note


# ── audit ─────────────────────────────────────────────────────────────────────

@app.get("/api/v1/audit")
def audit_list(n: int = 20):
    return audit.list_recent(n)


@app.get("/api/v1/audit/{audit_id}")
def audit_get(audit_id: int):
    rec = audit.get(audit_id)
    if not rec:
        raise HTTPException(404, "not found")
    return rec


# ── knowledge ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/knowledge/search")
def kb_search(q: str, k: int = 4):
    return get_kb().search(q, k=k)


# ── reports ───────────────────────────────────────────────────────────────────

@app.get("/api/v1/report/{audit_id}")
def report_pdf(audit_id: int):
    rec = audit.get(audit_id)
    if not rec:
        raise HTTPException(404, "not found")
    ex = rec["explanations"].get("client")
    if ex is None:
        ex = explain(rec["result"], "client")
        audit.set_explanation(audit_id, "client", ex)
    pdf = report.build_pdf(rec, ex["text"])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=finvision_{audit_id}.pdf"})


# ── static files ──────────────────────────────────────────────────────────────

@app.get("/plotly.min.js")
def plotly_js():
    return FileResponse(config.FRONTEND_DIR / "plotly.min.js", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})


@app.get("/{path:path}")
def spa_fallback(path: str):
    """Serve index.html for all frontend routes (SPA)."""
    p = config.FRONTEND_DIR / path
    if p.exists() and p.is_file():
        return FileResponse(p, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})
    return FileResponse(config.FRONTEND_DIR / "index.html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})
