import pytest
from app.schemas import ProductSpec, CustomerProfile
from app.engines.twin import find_twin, DISCLAIMER
from app.engines.portfolio import portfolio_impact, rupee_impact
from app.engines.stress import regime_stress, stress_ladder
from app.engines.teachback import get_questions, score_answers
from app.alerts import generate_alerts
from app.engines.market_data import get_prices
from app import config

ELN = ProductSpec(product_type="ELN", tenor_months=12, coupon_pct=12, barrier_pct=70, notional=1_000_000)
C101 = CustomerProfile(
    id="C101",
    name="Rahul Gupta",
    risk_appetite="conservative",
    loss_tolerance_pct=5,
    horizon_months=24,
    portfolio_value=10_000_000,
    annual_income=3_000_000,
    existing_exposures={"NIFTY 50": 45}
)


def test_twin_engine():
    prices, source = get_prices(ELN.underlying)
    result = find_twin(ELN, prices)
    assert "twin" in result
    twin = result["twin"]
    assert "start_date" in twin
    assert "end_date" in twin
    assert "similarity_score" in twin
    assert 0 <= twin["similarity_score"] <= 1.0
    assert result["disclaimer"] == DISCLAIMER


def test_portfolio_impact_engine():
    impact = portfolio_impact(C101, ELN)
    assert "before" in impact
    assert "after" in impact
    assert impact["before"]["exposures"]["NIFTY 50"]["pct"] == 45.0
    assert impact["concentration_pct"] > 45.0
    assert impact["concentration_flag"] is True
    assert "delta_loss_pct" in impact
    assert "delta_loss_inr" in impact


def test_rupee_impact_engine():
    impact = rupee_impact(ELN.model_dump(), tail_loss_pct=25.0, customer={"annual_income_inr": 3_000_000})
    assert impact["notional"] == 1_000_000
    assert impact["loss_inr"] == 250_000
    assert "₹2,50,000" in impact["loss_inr_text"]
    assert impact["months_equivalent"] == 1.0


def test_stress_ladder_and_regimes():
    rules = config.load_rules()
    ladder = stress_ladder(ELN, C101, rules)
    assert len(ladder) >= 5
    for row in ladder:
        assert "shock_pct" in row
        assert "loss_pct" in row
        assert "loss_inr" in row
        assert "loss_rule" in row
        assert "overall" in row

    regimes = regime_stress(ELN, C101, rules)
    assert len(regimes) >= 3
    assert any(r["regime"] == "Bull" for r in regimes)
    assert any(r["regime"] == "Crash" for r in regimes)


def test_teachback_engine():
    assessment = {"decision": "MISMATCH", "tail_loss_pct": 28.0}
    questions = get_questions(ELN.model_dump(), assessment)
    assert len(questions) == 3
    for q in questions:
        assert "id" in q
        assert "question" in q
        assert len(q["options"]) >= 3

    # All correct scoring
    answers_all_correct = [q["correct_index"] for q in questions]
    score_res = score_answers(questions, answers_all_correct)
    assert score_res["score"] == 3
    assert score_res["understanding_flag"] is False

    # One wrong answer scoring
    answers_one_wrong = [q["correct_index"] for q in questions]
    answers_one_wrong[0] = (answers_one_wrong[0] + 1) % len(questions[0]["options"])
    score_wrong_res = score_answers(questions, answers_one_wrong)
    assert score_wrong_res["score"] == 2
    assert score_wrong_res["understanding_flag"] is True


def test_alerts_engine():
    assessment = {
        "decision": "MISMATCH",
        "rules": [
            {"rule_id": "R1_RISK_APPETITE", "status": "MISMATCH", "description": "Risk mismatch"},
            {"rule_id": "R4_CONCENTRATION", "status": "MISMATCH", "description": "High concentration"}
        ],
        "metrics": {"tail_loss_pct": 35.0}
    }
    alerts = generate_alerts(C101.model_dump(), ELN.model_dump(), assessment, audit_id=999)
    assert len(alerts) >= 1
    assert any(a["severity"] == "HIGH" for a in alerts)
