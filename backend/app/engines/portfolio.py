"""Portfolio Impact and Rupee Impact engines.
Pure deterministic calculation — no LLM involved.
"""
from __future__ import annotations
from typing import Any

# Simplified sensitivity assumptions (shown explicitly in UI)
SENSITIVITY = {
    "NIFTY 50": 1.0,
    "USDINR": 0.5,
    "equity_other": 0.9,
    "debt": 0.0,
    "gold": 0.0,
    "cash": 0.0,
}

SENSITIVITY_NOTE = (
    "These sensitivities are simplified assumptions (not measured betas). "
    "NIFTY-linked=1.0, USDINR=0.5, other equity≈0.9, debt/gold/cash=0."
)


def portfolio_impact(
    customer: dict | Any,
    product: dict | Any,
    stress_shock_pct: float = -35.0,
) -> dict:
    """Compare portfolio loss BEFORE and AFTER adding the structured product at a stress shock."""
    c_dict = customer.model_dump() if hasattr(customer, "model_dump") else (dict(customer) if not isinstance(customer, dict) else customer)
    p_dict = product.model_dump() if hasattr(product, "model_dump") else (dict(product) if not isinstance(product, dict) else product)
    portfolio_value = float(c_dict.get("portfolio_value", 0))
    existing_exposures = c_dict.get("existing_exposures", {}) or {}
    notional = float(p_dict.get("notional", 1_000_000))
    underlying = p_dict.get("underlying", "NIFTY 50")

    # --- BEFORE ---
    before_loss_inr = 0.0
    before_exposures = {}
    for und, pct in existing_exposures.items():
        exp_inr = portfolio_value * pct / 100.0
        sens = SENSITIVITY.get(und, SENSITIVITY["equity_other"])
        loss = exp_inr * sens * abs(stress_shock_pct) / 100.0
        before_loss_inr += loss
        before_exposures[und] = {"pct": pct, "inr": round(exp_inr), "loss_inr": round(loss)}

    before_loss_pct = round(before_loss_inr / portfolio_value * 100, 2) if portfolio_value else 0

    # --- AFTER: add structured product notional ---
    new_pct = notional / portfolio_value * 100.0
    after_exposures = dict(existing_exposures)
    after_exposures[underlying] = after_exposures.get(underlying, 0) + new_pct

    after_loss_inr = before_loss_inr  # existing losses unchanged
    sens_new = SENSITIVITY.get(underlying, SENSITIVITY["equity_other"])
    product_loss_inr = notional * sens_new * abs(stress_shock_pct) / 100.0
    after_loss_inr += product_loss_inr

    after_loss_pct = round(after_loss_inr / portfolio_value * 100, 2) if portfolio_value else 0

    # Concentration
    total_underlying_pct = after_exposures.get(underlying, 0)
    concentration_limit = 50.0  # from rules
    concentration_flag = total_underlying_pct > concentration_limit

    return {
        "stress_shock_pct": stress_shock_pct,
        "portfolio_value": portfolio_value,
        "notional": notional,
        "underlying": underlying,
        "before": {
            "loss_pct": before_loss_pct,
            "loss_inr": round(before_loss_inr),
            "exposures": before_exposures,
        },
        "after": {
            "loss_pct": after_loss_pct,
            "loss_inr": round(after_loss_inr),
            "product_contribution_inr": round(product_loss_inr),
            "exposures": {
                und: {"pct": round(pct, 2)} for und, pct in after_exposures.items()
            },
        },
        "delta_loss_pct": round(after_loss_pct - before_loss_pct, 2),
        "delta_loss_inr": round(after_loss_inr - before_loss_inr),
        "concentration_pct": round(total_underlying_pct, 2),
        "concentration_limit_pct": concentration_limit,
        "concentration_flag": concentration_flag,
        "note": SENSITIVITY_NOTE,
    }


def rupee_impact(product: dict, tail_loss_pct: float, customer: dict | None = None) -> dict:
    """Convert % loss figures to INR amounts with Indian formatting context."""
    notional = product["notional"]
    loss_inr = round(notional * tail_loss_pct / 100.0)

    result = {
        "notional": notional,
        "notional_text": _inr(notional),
        "tail_loss_pct": tail_loss_pct,
        "loss_inr": loss_inr,
        "loss_inr_text": _inr(loss_inr),
    }

    if customer:
        annual_income = customer.get("annual_income_inr")
        if annual_income:
            monthly = annual_income / 12.0
            months_equiv = round(loss_inr / monthly, 1) if monthly else None
            result["annual_income"] = annual_income
            result["annual_income_text"] = _inr(annual_income)
            result["monthly_income"] = round(monthly)
            result["monthly_income_text"] = _inr(monthly)
            result["months_equivalent"] = months_equiv
            result["months_equivalent_text"] = (
                f"approximately {months_equiv} months of income" if months_equiv else None
            )

    return result


def _inr(x: float) -> str:
    """Indian numbering format: 10,00,000 etc."""
    s = f"{abs(round(x)):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if x < 0 else "") + "₹" + s
