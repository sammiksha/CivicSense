from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

UNDERLYINGS = {"NIFTY 50": "NIFTY50", "USDINR": "USDINR"}


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

    @model_validator(mode="after")
    def _check(self):
        if self.underlying not in UNDERLYINGS:
            raise ValueError(f"underlying must be one of {list(UNDERLYINGS)}")
        if self.product_type == "ELN" and self.barrier_pct is None:
            raise ValueError("ELN requires barrier_pct")
        return self


class CustomerProfile(BaseModel):
    id: str
    name: str = "Customer"
    risk_appetite: Literal["conservative", "moderate", "aggressive"]
    loss_tolerance_pct: float = Field(ge=0, le=100)
    horizon_months: int = Field(gt=0)
    portfolio_value: float = Field(gt=0)
    existing_exposures: dict[str, float] = Field(default_factory=dict, description="underlying -> % of portfolio")


class AssessmentRequest(BaseModel):
    product: ProductSpec
    customer_id: Optional[str] = None
    customer: Optional[CustomerProfile] = None
    mode: Literal["rm", "client"] = "rm"


class ScenarioRequest(BaseModel):
    product: ProductSpec
    moves: list[float] = [20, 0, -10, -25, -40]


class CopilotRequest(BaseModel):
    session_id: str = "default"
    message: str
    mode: Literal["rm", "client"] = "rm"
    product: Optional[ProductSpec] = None
    customer_id: Optional[str] = None


class TextRequest(BaseModel):
    text: str


class ExplainRequest(BaseModel):
    audit_id: int
    mode: Literal["rm", "client"] = "client"
