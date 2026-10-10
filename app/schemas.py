from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

class HistoryItem(BaseModel):
    due: int = Field(..., ge=0, le=10000000000)
    paid: int = Field(..., ge=0, le=10000000000)
    days_late: int = Field(..., ge=0, le=365)

class ScoreRequest(BaseModel):
    lang: str = Field(default="en", pattern="^(en|ru|uz)$")
    business_type: str = Field(...)
    loan_amount: int = Field(..., ge=0, le=10000000000)
    annual_rate: float = Field(..., ge=0, le=1.0)
    term_months: int = Field(..., ge=1, le=120)
    months_elapsed: int = Field(..., ge=0, le=120)
    outstanding: int = Field(..., ge=0, le=10000000000)
    history: List[HistoryItem] = Field(..., min_length=6, max_length=12)
    turnover: Optional[List[int]] = None

    @model_validator(mode='after')
    def check_turnover_and_months(self):
        if self.turnover is not None and len(self.turnover) != len(self.history):
            raise ValueError("turnover length must match history length")
        if self.months_elapsed > self.term_months:
            raise ValueError("months_elapsed cannot be greater than term_months")
        return self

class DecisionRequest(BaseModel):
    borrower_id: str
    action_code: str
    officer: str = Field(..., max_length=60)
    comment: str = Field(..., max_length=500)