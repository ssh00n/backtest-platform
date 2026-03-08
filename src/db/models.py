"""
SQLAlchemy ORM 모델.

protocol: docs/protocols/decision-protocol.md

Tables:
    buy_logs   — 매수 의사결정 기록 (BuyLog)
    trades     — 실제 체결 기록 (매수/매도)
    positions  — 현재 보유 포지션
    sell_logs  — 매도 의사결정 기록
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.database import Base


# ── Enums ─────────────────────────────────────────────────


class MarketRegimeEnum(str):
    BULL = "BULL"
    SIDEWAYS = "SIDEWAYS"
    BEAR = "BEAR"


class SellTriggerEnum(str):
    KILL_CONDITION = "KILL_CONDITION"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    STRUCTURAL_CHANGE = "STRUCTURAL_CHANGE"
    PROFIT_TARGET = "PROFIT_TARGET"
    TRAILING_STOP = "TRAILING_STOP"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    OPPORTUNITY_COST = "OPPORTUNITY_COST"


class TradeActionEnum(str):
    BUY = "BUY"
    SELL = "SELL"


# ── Buy Log ───────────────────────────────────────────────


class BuyLog(Base):
    """매수 의사결정 기록 — decision-protocol.md BuyLog 구현."""

    __tablename__ = "buy_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 기본 정보
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    position_size: Mapped[float] = mapped_column(Float, nullable=False)

    # 필수 3요소
    thesis: Mapped[str] = mapped_column(Text, nullable=False)
    kill_condition: Mapped[str] = mapped_column(Text, nullable=False)
    risk_factors: Mapped[str] = mapped_column(Text, nullable=False)

    # 실행 엔진 (execution-protocol)
    box_top: Mapped[float] = mapped_column(Float, nullable=False)
    box_bottom: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target_price: Mapped[float] = mapped_column(Float, nullable=False)
    risk_r: Mapped[float] = mapped_column(Float, nullable=False)
    reward: Mapped[float] = mapped_column(Float, nullable=False)
    rr_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    time_stop_days: Mapped[int] = mapped_column(Integer, nullable=False)
    partial_exit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 스크리닝 기록
    screening_step: Mapped[int] = mapped_column(Integer, nullable=False)
    volume_regime: Mapped[str] = mapped_column(String(20), nullable=False)
    market_regime: Mapped[str] = mapped_column(String(10), nullable=False)

    # 예외
    exception_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_rule: Mapped[str] = mapped_column(Text, default="")
    exception_reason: Mapped[str] = mapped_column(Text, default="")
    exception_risk: Mapped[str] = mapped_column(Text, default="")

    notes: Mapped[str] = mapped_column(Text, default="")

    # Relationships
    trades: Mapped[list["Trade"]] = relationship(back_populates="buy_log")
    sell_log: Mapped["SellLog | None"] = relationship(back_populates="buy_log", uselist=False)
    position: Mapped["Position | None"] = relationship(back_populates="buy_log", uselist=False)


# ── Trade ─────────────────────────────────────────────────


class Trade(Base):
    """실제 체결 기록."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    buy_log_id: Mapped[int] = mapped_column(ForeignKey("buy_logs.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY / SELL
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)

    notes: Mapped[str] = mapped_column(Text, default="")

    buy_log: Mapped["BuyLog"] = relationship(back_populates="trades")


# ── Position ──────────────────────────────────────────────


class Position(Base):
    """현재 보유 포지션."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    buy_log_id: Mapped[int] = mapped_column(ForeignKey("buy_logs.id"), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_quantity: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    highest_price: Mapped[float] = mapped_column(Float, nullable=False)  # 트레일링 스탑 추적용

    # Time Stop 추적
    entry_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    time_stop_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    is_open: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    buy_log: Mapped["BuyLog"] = relationship(back_populates="position")


# ── Sell Log ──────────────────────────────────────────────


class SellLog(Base):
    """매도 의사결정 기록."""

    __tablename__ = "sell_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    buy_log_id: Mapped[int] = mapped_column(ForeignKey("buy_logs.id"), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)

    # 매도 트리거 (decision-protocol 매도 판단)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_detail: Mapped[str] = mapped_column(Text, nullable=False)

    # 결과
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_amount: Mapped[float] = mapped_column(Float, nullable=False)  # 절대 손익
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)  # 수익률 (%)
    pnl_r: Mapped[float] = mapped_column(Float, nullable=False)  # R 배수

    # 보유 기간
    holding_days: Mapped[int] = mapped_column(Integer, nullable=False)

    # 회고
    was_thesis_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retrospective: Mapped[str] = mapped_column(Text, default="")

    buy_log: Mapped["BuyLog"] = relationship(back_populates="sell_log")
