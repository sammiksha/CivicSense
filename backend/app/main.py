from __future__ import annotations
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from . import audit, config
from .agent import copilot
from .agent.session import get_session
from .agent.tools import find_customer, load_customers
from .engines.payoff import payoff_curve, scenario_table
from .extraction.term_sheet import extract_product, file_to_text
from .rag.store import get_kb
from .schemas import (AssessmentRequest, CopilotRequest, ExplainRequest, ProductSpec, ScenarioRequest, TextRequest)
from .services import report
from .services.assessment import assess
from .services.explain import explain
from .llm.client import get_llm

app = FastAPI(title="StructuraAI", version="0.1.0",
              description="Explainable structured-product suitability platform: deterministic engines + RAG + agentic LLM.")


@app.get("/health")
def health():
    return {"status": "ok", "llm_mode": "claude" if get_llm() else "offline", "model_version": config.model_version(),
            "kb_chunks": len(get_kb().chunks)}


@app.get("/api/v1/customers")
def customers():
    return [c.model_dump() for c in load_customers()]


@app.post("/api/v1/payoff")
def payoff(req: ScenarioRequest):
    """Lightweight (no simulation): used by the live barrier slider."""
    return {"curve": payoff_curve(req.product), "scenarios": scenario_table(req.product, req.moves)}


@app.post("/api/v1/product/extract-text")
def extract_text(req: TextRequest):
    return extract_product(req.text)


@app.post("/api/v1/product/extract-file")
async def extract_file(file: UploadFile = File(...)):
    text = file_to_text(file.filename or "", await file.read())
    if not text.strip():
        raise HTTPException(422, "no text could be read from the file")
    return {**extract_product(text), "chars_read": len(text)}


def _customer(req):
    c = req.customer or (find_customer(req.customer_id) if req.customer_id else None)
    if c is None:
        raise HTTPException(404, "customer not found; pass customer_id or customer")
    return c


@app.post("/api/v1/assessment")
def assessment(req: AssessmentRequest):
    c = _customer(req)
    try:
        a = assess(req.product, c)
    except ValueError as e:
        raise HTTPException(422, str(e))
    ex = explain(a, req.mode)
    aid = audit.log(a, ex, req.mode)
    return {"audit_id": aid, "status": a["decision"], "flags": [r for r in a["rules"] if r["status"] != "SUITABLE"],
            "explanation": ex, "result": a}


@app.post("/api/v1/explain")
def explain_again(req: ExplainRequest):
    rec = audit.get(req.audit_id)
    if not rec:
        raise HTTPException(404, "audit record not found")
    ex = explain(rec["result"], req.mode)
    audit.set_explanation(req.audit_id, req.mode, ex)
    return ex


@app.post("/api/v1/copilot")
def copilot_ask(req: CopilotRequest):
    s = get_session(req.session_id)
    if req.product is not None:
        s.product = req.product
    if req.customer_id:
        c = find_customer(req.customer_id)
        if c is None:
            raise HTTPException(404, "customer not found")
        s.customer = c
    return copilot.ask(s, req.message, req.mode)


@app.get("/api/v1/knowledge/search")
def kb_search(q: str, k: int = 4):
    return get_kb().search(q, k=k)


@app.get("/api/v1/audit")
def audit_list(n: int = 20):
    return audit.list_recent(n)


@app.get("/api/v1/audit/{audit_id}")
def audit_get(audit_id: int):
    rec = audit.get(audit_id)
    if not rec:
        raise HTTPException(404, "not found")
    return rec


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
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename=structuraai_{audit_id}.pdf"})


@app.get("/plotly.min.js")
def plotly_js():
    return FileResponse(config.FRONTEND_DIR / "plotly.min.js")


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")

