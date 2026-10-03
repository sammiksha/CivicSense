from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
P = {"product_type": "ELN", "underlying": "NIFTY 50", "tenor_months": 12, "coupon_pct": 12, "barrier_pct": 70, "notional": 1000000}


def test_health_and_customers():
    assert c.get("/health").json()["llm_mode"] == "offline"
    assert len(c.get("/api/v1/customers").json()) >= 3


def test_assessment_audit_report():
    r = c.post("/api/v1/assessment", json={"product": P, "customer_id": "C101", "mode": "rm"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] in ("REVIEW", "MISMATCH") and j["flags"] and j["result"]["data_source"] in ("synthetic_fallback", "cached_real")
    aid = j["audit_id"]
    assert c.get(f"/api/v1/audit/{aid}").json()["decision"] == j["status"]
    pdf = c.get(f"/api/v1/report/{aid}")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert "client" in c.get(f"/api/v1/audit/{aid}").json()["explanations"]


def test_payoff_extract_copilot_kb():
    assert len(c.post("/api/v1/payoff", json={"product": P}).json()["curve"]) > 50
    assert c.post("/api/v1/product/extract-text", json={"text": "ELN NIFTY 12 months coupon 12% barrier 70% notional 10 lakh"}).json()["valid"]
    r = c.post("/api/v1/copilot", json={"session_id": "x", "message": "what if NIFTY falls 40%?", "product": P, "customer_id": "C101"})
    assert r.json()["tool_trace"][0]["tool"] == "run_scenario"
    assert c.get("/api/v1/knowledge/search", params={"q": "dual currency deposit risk"}).json()[0]["doc"] == "dcd"
    assert c.post("/api/v1/assessment", json={"product": P, "customer_id": "nope"}).status_code == 404
