"""Strict server-side validation: the browser is never trusted."""
from typing import List, Literal, Optional

from pydantic import BaseModel as _Base
from pydantic import ConfigDict, Field, model_validator

MAX_MONEY = 10_000_000_000


class BaseModel(_Base):
    # Unknown fields are rejected (422): no "mass assignment" of e.g. {"status": "approved"}.
    model_config = ConfigDict(extra="forbid")
Lang = Literal["en", "ru", "uz"]
Business = Literal["tailoring", "greenhouse", "livestock", "retail_shop", "bakery", "wedding_services", "other"]
Segment = Literal["household", "micro_business", "sme"]


class HistoryItem(BaseModel):
    due: int = Field(..., ge=0, le=MAX_MONEY)
    paid: int = Field(..., ge=0, le=MAX_MONEY)
    days_late: int = Field(..., ge=0, le=365)


class ScoreRequest(BaseModel):
    lang: Lang = "en"
    name: str = Field("Jury borrower", max_length=40)
    business_type: Business = "other"
    segment: Segment = "micro_business"
    annual_rate: float = Field(..., ge=0, le=1.0)
    term_months: int = Field(..., ge=1, le=120)
    months_elapsed: int = Field(..., ge=0, le=120)
    outstanding: int = Field(..., ge=0, le=MAX_MONEY)
    installment: Optional[int] = Field(None, ge=0, le=MAX_MONEY)
    history: List[HistoryItem] = Field(..., min_length=6, max_length=12)
    turnover: Optional[List[int]] = Field(None, max_length=12)
    has_app: bool = False
    has_guarantor: bool = False
    prior_loans_repaid: int = Field(0, ge=0, le=20)

    @model_validator(mode="after")
    def check(self):
        if self.months_elapsed >= self.term_months:
            raise ValueError("months_elapsed must be smaller than term_months")
        if self.turnover is not None:
            if len(self.turnover) != len(self.history):
                raise ValueError("turnover must have the same number of months as history")
            if any(t < 0 or t > MAX_MONEY for t in self.turnover):
                raise ValueError("turnover values must be between 0 and 10,000,000,000")
        return self


class DecisionRequest(BaseModel):
    borrower_id: str = Field(..., max_length=20)
    action_code: str = Field(..., max_length=40)
    officer: str = Field(..., min_length=1, max_length=60)
    comment: str = Field("", max_length=500)


class OutcomeRequest(BaseModel):
    borrower_id: str = Field(..., max_length=20)
    action_code: str = Field(..., max_length=40)
    resolved: bool
