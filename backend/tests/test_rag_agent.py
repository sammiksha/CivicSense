from app.rag.store import get_kb
from app.agent.grounding import ungrounded_numbers
from app.agent.session import Session
from app.agent import copilot
from app.agent.tools import find_customer
from app.extraction.term_sheet import extract_product
from app.schemas import ProductSpec
from app import config


def test_rag_retrieval():
    top = get_kb().search("what is a barrier in an equity linked note", k=3)
    assert top and top[0]["doc"] == "eln"
    pol = get_kb().search("concentration limit policy", k=2)
    assert pol[0]["doc"] == "suitability_policy"


def test_grounding_guard():
    src = {"a": 28.4, "b": [12.0]}
    assert ungrounded_numbers("Loss about 28% and coupon 12%. [kb:eln#1]", src) == []
    assert ungrounded_numbers("Loss about 41% [kb:eln#1]", src) == ["41"]


def test_offline_extraction_sample_term_sheet():
    text = (config.DATA_DIR / "samples" / "sample_term_sheet.txt").read_text()
    r = extract_product(text)
    assert r["valid"], r
    p = r["product"]
    assert (p["product_type"], p["underlying"], p["tenor_months"], p["coupon_pct"], p["barrier_pct"], p["notional"]) == \
           ("ELN", "NIFTY 50", 12, 12.0, 70.0, 1_000_000.0)


def test_extraction_flags_missing_not_guesses():
    r = extract_product("one-year NIFTY equity linked note, 12% coupon")
    assert not r["valid"] and "barrier_pct" in r["missing"] and "notional" in r["missing"]


def test_copilot_offline_tools():
    s = Session("t")
    s.product = ProductSpec(product_type="ELN", tenor_months=12, coupon_pct=12, barrier_pct=70, notional=1_000_000)
    s.customer = find_customer("C101")
    out = copilot.ask(s, "What happens if NIFTY falls 25%?", "client")
    assert out["tool_trace"][0]["tool"] == "run_scenario" and "1,120,000" in out["answer"].replace(" ", "") or "1,120,000" in out["answer"]
    out = copilot.ask(s, "when does it stop being suitable?", "rm")
    assert out["tool_trace"][0]["tool"] == "find_breaking_point"
    out = copilot.ask(Session("empty"), "is it suitable?", "rm")
    assert "Select a customer" in out["answer"]
