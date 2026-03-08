"""
Pydantic 스키마 — 입력 검증 + API 응답 직렬화.

protocol: docs/protocols/decision-protocol.md
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enums ─────────────────────────────────────────────────


class MarketRegimeType(str, Enum):
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"


class SellTriggerType(str, Enum):
    KILL_CONDITION = "KILL_CONDITION"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"
    PROFIT_TARGET = "PROFIT_TARGET"
    TRAILING_STOP = "TRAILING_STOP"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    OPPORTUNITY_COST = "OPPORTUNITY_COST"


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# ── Buy Log ───────────────────────────────────────────────


class BuyLogCreate(BaseModel):
    """매수 의사결정 생성 스키마."""

    symbol: str = Field(..., max_length=10)
    entry_price: float = Field(..., gt=0)
    position_size: float = Field(..., gt=0)

    # 필수 3요소 (빈 문자열 금지)
    thesis: str = Field(..., min_length=1)
    kill_condition: str = Field(..., min_length=1)
    risk_factors: str = Field(..., min_length=1)

    # 실행 엔진
    box_top: float = Field(..., gt=0)
    box_bottom: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    target_price: float = Field(..., gt=0)
    risk_r: float = Field(..., gt=0)
    reward: float
    rr_ratio: float = Field(..., gt=0, description="R:R >= 3.0 필수 (예외 시 >= 2.0)")
    time_stop_days: int = Field(..., gt=0)
    partial_exit_pct: float | None = Field(None, ge=0, le=1)

    # 스크리닝 기록
    screening_step: int = Field(..., ge=1, le=4)
    volume_regime: str
    market_regime: MarketRegimeType

    # 예외
    exception_applied: bool = False
    exception_rule: str = ""
    exception_reason: str = ""
    exception_risk: str = ""

    notes: str = ""

    @model_validator(mode="after")
    def rr_must_be_at_least_3(self):
        # 예외 적용 시 R:R < 3 허용 (단 >= 2.0)
        if self.exception_applied and self.rr_ratio >= 2.0:
            return self
        if self.rr_ratio < 3.0:
            raise ValueError(
                f"R:R must be >= 3.0 (got {self.rr_ratio}). "
                f"Use exception_applied=True if R:R >= 2.0."
            )
        return self

    @field_validator("box_bottom")
    @classmethod
    def box_bottom_less_than_top(cls, v: float, info) -> float:
        top = info.data.get("box_top")
        if top is not None and v >= top:
            raise ValueError(f"box_bottom ({v}) must be < box_top ({top})")
        return v

    @field_validator("stop_loss")
    @classmethod
    def stop_loss_below_entry(cls, v: float, info) -> float:
        entry = info.data.get("entry_price")
        if entry is not None and v >= entry:
            raise ValueError(f"stop_loss ({v}) must be < entry_price ({entry})")
        return v


class BuyLogResponse(BaseModel):
    """매수 의사결정 응답 스키마."""

    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
    symbol: str
    entry_price: float
    position_size: float
    thesis: str
    kill_condition: str
    risk_factors: str
    box_top: float
    box_bottom: float
    stop_loss: float
    target_price: float
    risk_r: float
    reward: float
    rr_ratio: float
    time_stop_days: int
    partial_exit_pct: float | None
    screening_step: int
    volume_regime: str
    market_regime: str
    exception_applied: bool
    exception_rule: str
    exception_reason: str
    exception_risk: str
    notes: str


# ── Trade ─────────────────────────────────────────────────


class TradeCreate(BaseModel):
    """체결 기록 생성 스키마."""

    buy_log_id: int
    symbol: str = Field(..., max_length=10)
    action: TradeAction
    price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    notes: str = ""


class TradeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
    buy_log_id: int
    symbol: str
    action: str
    price: float
    quantity: float
    total_value: float
    notes: str


# ── Sell Log ──────────────────────────────────────────────


class SellLogCreate(BaseModel):
    """매도 의사결정 생성 스키마."""

    buy_log_id: int
    symbol: str = Field(..., max_length=10)
    trigger: SellTriggerType
    trigger_detail: str = Field(..., min_length=1)
    exit_price: float = Field(..., gt=0)
    holding_days: int = Field(..., ge=0)

    # 회고 (선택)
    was_thesis_correct: bool | None = None
    retrospective: str = ""


class SellLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
    buy_log_id: int
    symbol: str
    trigger: str
    trigger_detail: str
    exit_price: float
    pnl_amount: float
    pnl_pct: float
    pnl_r: float
    holding_days: int
    was_thesis_correct: bool | None
    retrospective: str


# ── Position ──────────────────────────────────────────────


class PositionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    buy_log_id: int
    symbol: str
    entry_price: float
    current_quantity: float
    stop_loss: float
    highest_price: float
    entry_date: datetime
    time_stop_deadline: datetime
    is_open: bool
