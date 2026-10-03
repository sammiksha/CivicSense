from __future__ import annotations
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, model_validator

UNDERLYINGS = {
    "NIFTY 50": "NIFTY50",
    "USDINR": "USDINR",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD"
}


class ProductSpec(BaseModel):
    product_type: Literal["ELN", "DCD", "CPN"]
    underlying: str = "NIFTY 50"
    tenor_months: int = Field(12, ge=1, le=120)
    coupon_pct: float = Field(0, ge=0, le=100, description="annual coupon / interest, %")
    barrier_pct: Optional[float] = Field(None, gt=0, le=100, description="ELN knock-in barrier, % of initial")
    strike_pct: float = Field(100, gt=0, le=200, description="strike / DCD conversion level, % of initial")
    protection_pct: float = Field(100, ge=0, le=100, description="CPN protected %")
    participation_pct: float = Field(100, ge=0, le=500, description="CPN participation %")
    notional: float = Field(1_000_000, gt=0)
    currency: str = "INR"
    observation_type: str = "at_maturity"

    @model_validator(mode="after")
    def _check(self):
        # Normalize underlying if needed
        if self.product_type == "ELN" and self.barrier_pct is None:
            raise ValueError("ELN requires barrier_pct")
        if self.product_type == "ELN" and self.barrier_pct is not None:
            if self.barrier_pct > self.strike_pct:
                raise ValueError("barrier_pct cannot exceed strike_pct")
        return self


class CustomerProfile(BaseModel):
    id: str
    name: str = "Customer"
    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    loss_tolerance_pct: float = Field(ge=0, le=100)
    horizon_months: int = Field(gt=0)
    portfolio_value: float = Field(gt=0)
    existing_exposures: dict[str, float] = Field(default_factory=dict, description="underlying -> % of portfolio")
    annual_income_inr: Optional[float] = None
    liquidity_need: str = "medium"
    rm_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    pan: Optional[str] = None
    kyc_status: str = "verified"
    segment: str = "HNI"
    holdings: list[dict] = Field(default_factory=list)


class AssessmentRequest(BaseModel):
    product: ProductSpec
    customer_id: Optional[str] = None
    customer: Optional[CustomerProfile] = None
    mode: Literal["rm", "client"] = "rm"


class ScenarioRequest(BaseModel):
    product: ProductSpec
    moves: list[float] = [20, 10, 0, -10, -20, -25, -30, -35, -40, -50]


class CopilotRequest(BaseModel):
    session_id: str = "default"
    message: str
    mode: Literal["rm", "client"] = "client"
    product: Optional[ProductSpec] = None
    customer_id: Optional[str] = None
    page_context: Optional[str] = None
    history: Optional[list[dict]] = None


class TextRequest(BaseModel):
    text: str


class ExplainRequest(BaseModel):
    audit_id: int
    mode: Literal["rm", "client"] = "client"


class LoginRequest(BaseModel):
    email: str
    password: str


class PortfolioImpactRequest(BaseModel):
    product: ProductSpec
    customer_id: str
    stress_shock_pct: float = -35.0


class RMNoteRequest(BaseModel):
    audit_id: int
    rm_decision: Optional[str] = None  # "Proceed" | "Modify" | "Decline"
    rm_comments: Optional[str] = None
