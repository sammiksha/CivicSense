import pytest
from app.schemas import ProductSpec, CustomerProfile
from app.engines.payoff import value_fraction, scenario_table, loss_at_shock
from app.engines.suitability import evaluate, overall, breaking_point
from app import config

ELN = ProductSpec(product_type="ELN", tenor_months=12, coupon_pct=12, barrier_pct=70, notional=1_000_000)
C101 = CustomerProfile(id="C101", risk_appetite="conservative", loss_tolerance_pct=5, horizon_months=24,
                       portfolio_value=10_000_000, existing_exposures={"NIFTY 50": 45})


def v(p, f, m): return float(value_fraction(p, f, m))


def test_eln_hand_computed():
    assert v(ELN, 0.0, 0.0) == pytest.approx(1.12)           # coupon only
    assert v(ELN, -0.25, -0.25) == pytest.approx(1.12)       # above barrier
    assert v(ELN, -0.40, -0.40) == pytest.approx(0.72)       # breached: 0.60 + 0.12
    assert v(ELN, -0.20, -0.35) == pytest.approx(0.92)       # path breached, recovered to -20%
    assert v(ELN, 0.20, 0.0) == pytest.approx(1.12)          # upside capped at coupon


def test_dcd_and_cpn():
    dcd = ProductSpec(product_type="DCD", underlying="USDINR", tenor_months=12, coupon_pct=6, strike_pct=100)
    assert v(dcd, 0.03, 0) == pytest.approx(1.06)
    assert v(dcd, -0.02, -0.02) == pytest.approx(0.98 + 0.06)
    cpn = ProductSpec(product_type="CPN", tenor_months=12, protection_pct=100, participation_pct=80)
    assert v(cpn, 0.20, 0) == pytest.approx(1.16)
    assert v(cpn, -0.50, -0.50) == pytest.approx(1.00)


def test_eln_requires_barrier():
    with pytest.raises(Exception):
        ProductSpec(product_type="ELN")


def test_suitability_rules_and_breaking_point():
    rules = config.load_rules()
    res = evaluate(ELN, C101, 30.0, rules)
    st = {r["rule_id"]: r["status"] for r in res}
    assert st["R1_RISK_APPETITE"] == "MISMATCH"    # conservative vs high-risk (two levels)
    assert st["R2_LOSS_TOLERANCE"] == "MISMATCH"   # 5% vs 30%
    assert st["R3_HORIZON"] == "SUITABLE"
    assert st["R4_CONCENTRATION"] == "MISMATCH"    # 45 + 10 = 55 > 50
    assert overall(res) == "MISMATCH"
    bp = breaking_point(ELN, C101, rules)
    assert -31 <= bp["suitable_until_pct"] <= -29        # barrier at 70% => loss starts just below -30%
    assert loss_at_shock(ELN, -29) == 0.0 and loss_at_shock(ELN, -40) > 5
    assert bp["mismatch_from_pct"] is not None and bp["mismatch_from_pct"] < bp["suitable_until_pct"]
    assert "R4_CONCENTRATION" in bp["blocked_by_other_rules"]


def test_deterministic_pipeline_and_repair():
    from app.services.assessment import assess
    a1, a2 = assess(ELN, C101), assess(ELN, C101)
    assert a1["metrics"] == a2["metrics"] and a1["decision"] == a2["decision"]   # same input -> same output
    assert a1["decision"] != "SUITABLE"
    for r in a1["repairs"]:                       # every repair is re-verified as SUITABLE
        assert r["decision_after"] == "SUITABLE"
    assert a1["repairs"], "expected at least one verified repair"
    assert a1["scenarios"][0]["move_pct"] == 20
