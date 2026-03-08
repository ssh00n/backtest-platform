"""
의사결정 로거 — Buy/Sell/Position CRUD.

protocol: docs/protocols/decision-protocol.md

모든 매수/매도 의사결정을 PostgreSQL에 기록하고,
방어적 실행 프로토콜(강제 대기 조건)을 검증한다.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.database import SessionLocal, init_db
from src.db.models import BuyLog, Position, SellLog, Trade
from src.db.schemas import BuyLogCreate, BuyLogResponse, SellLogCreate, SellLogResponse, TradeCreate
from src.utils.logger import get_logger

log = get_logger(__name__)


# ── Buy Log ───────────────────────────────────────────────


def create_buy_log(session: Session, data: BuyLogCreate) -> BuyLog:
    """매수 의사결정을 기록한다. 방어적 실행 조건을 사전 검증."""

    # 방어적 실행: 강제 대기 조건 체크
    violations = check_defensive_constraints(session, data.market_regime)
    if violations:
        for v in violations:
            log.warning("Defensive constraint violated: %s", v)
        raise ValueError(f"Defensive constraints violated: {'; '.join(violations)}")

    buy_log = BuyLog(
        symbol=data.symbol,
        entry_price=data.entry_price,
        position_size=data.position_size,
        thesis=data.thesis,
        kill_condition=data.kill_condition,
        risk_factors=data.risk_factors,
        box_top=data.box_top,
        box_bottom=data.box_bottom,
        stop_loss=data.stop_loss,
        target_price=data.target_price,
        risk_r=data.risk_r,
        reward=data.reward,
        rr_ratio=data.rr_ratio,
        time_stop_days=data.time_stop_days,
        partial_exit_pct=data.partial_exit_pct,
        screening_step=data.screening_step,
        volume_regime=data.volume_regime,
        market_regime=data.market_regime,
        exception_applied=data.exception_applied,
        exception_rule=data.exception_rule,
        exception_reason=data.exception_reason,
        exception_risk=data.exception_risk,
        notes=data.notes,
    )

    session.add(buy_log)
    session.commit()
    session.refresh(buy_log)

    log.info("BuyLog created: #%d %s @ $%.2f (R:R=%.1f, %s)",
             buy_log.id, buy_log.symbol, buy_log.entry_price,
             buy_log.rr_ratio, buy_log.market_regime)

    # 포지션 자동 생성
    entry_date = datetime.now()
    position = Position(
        buy_log_id=buy_log.id,
        symbol=buy_log.symbol,
        entry_price=buy_log.entry_price,
        current_quantity=buy_log.position_size,
        stop_loss=buy_log.stop_loss,
        highest_price=buy_log.entry_price,
        entry_date=entry_date,
        time_stop_deadline=entry_date + timedelta(days=int(buy_log.time_stop_days * 1.4)),
        is_open=True,
    )
    session.add(position)

    # 매수 체결 기록
    trade = Trade(
        buy_log_id=buy_log.id,
        symbol=buy_log.symbol,
        action="BUY",
        price=buy_log.entry_price,
        quantity=buy_log.position_size,
        total_value=buy_log.entry_price * buy_log.position_size,
    )
    session.add(trade)

    session.commit()
    log.info("Position & Trade created for BuyLog #%d", buy_log.id)

    return buy_log


def get_buy_log(session: Session, buy_log_id: int) -> BuyLog | None:
    return session.get(BuyLog, buy_log_id)


def get_buy_logs_by_symbol(session: Session, symbol: str) -> list[BuyLog]:
    stmt = select(BuyLog).where(BuyLog.symbol == symbol).order_by(BuyLog.created_at.desc())
    return list(session.scalars(stmt).all())


def get_all_buy_logs(session: Session, limit: int = 50) -> list[BuyLog]:
    stmt = select(BuyLog).order_by(BuyLog.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


# ── Sell Log ──────────────────────────────────────────────


def create_sell_log(session: Session, data: SellLogCreate) -> SellLog:
    """매도 의사결정을 기록한다. PnL을 자동 계산."""

    buy_log = session.get(BuyLog, data.buy_log_id)
    if buy_log is None:
        raise ValueError(f"BuyLog #{data.buy_log_id} not found")

    # PnL 계산
    pnl_amount = (data.exit_price - buy_log.entry_price) * buy_log.position_size
    pnl_pct = (data.exit_price - buy_log.entry_price) / buy_log.entry_price * 100
    pnl_r = (data.exit_price - buy_log.entry_price) / buy_log.risk_r if buy_log.risk_r > 0 else 0

    sell_log = SellLog(
        buy_log_id=data.buy_log_id,
        symbol=data.symbol,
        trigger=data.trigger,
        trigger_detail=data.trigger_detail,
        exit_price=data.exit_price,
        pnl_amount=round(pnl_amount, 2),
        pnl_pct=round(pnl_pct, 2),
        pnl_r=round(pnl_r, 2),
        holding_days=data.holding_days,
        was_thesis_correct=data.was_thesis_correct,
        retrospective=data.retrospective,
    )

    session.add(sell_log)

    # 매도 체결 기록
    position = session.execute(
        select(Position).where(Position.buy_log_id == data.buy_log_id, Position.is_open)
    ).scalar_one_or_none()

    sell_qty = position.current_quantity if position else buy_log.position_size

    trade = Trade(
        buy_log_id=data.buy_log_id,
        symbol=data.symbol,
        action="SELL",
        price=data.exit_price,
        quantity=sell_qty,
        total_value=data.exit_price * sell_qty,
    )
    session.add(trade)

    # 포지션 종료
    if position:
        position.is_open = False

    session.commit()
    session.refresh(sell_log)

    log.info("SellLog created: #%d %s @ $%.2f (PnL: $%.2f / %.1f%% / %.1fR) trigger=%s",
             sell_log.id, sell_log.symbol, sell_log.exit_price,
             sell_log.pnl_amount, sell_log.pnl_pct, sell_log.pnl_r, sell_log.trigger)

    return sell_log


def create_partial_exit(session: Session, buy_log_id: int, exit_price: float, exit_ratio: float = 0.5) -> Trade:
    """부분 익절을 실행한다."""

    position = session.execute(
        select(Position).where(Position.buy_log_id == buy_log_id, Position.is_open)
    ).scalar_one_or_none()

    if position is None:
        raise ValueError(f"No open position for BuyLog #{buy_log_id}")

    sell_qty = position.current_quantity * exit_ratio
    position.current_quantity -= sell_qty

    trade = Trade(
        buy_log_id=buy_log_id,
        symbol=position.symbol,
        action="SELL",
        price=exit_price,
        quantity=sell_qty,
        total_value=exit_price * sell_qty,
        notes=f"Partial exit ({exit_ratio*100:.0f}%)",
    )
    session.add(trade)
    session.commit()
    session.refresh(trade)

    log.info("Partial exit: %s %.0f shares @ $%.2f (%.0f%% of position)",
             position.symbol, sell_qty, exit_price, exit_ratio * 100)

    return trade


# ── Position ──────────────────────────────────────────────


def get_open_positions(session: Session) -> list[Position]:
    stmt = select(Position).where(Position.is_open).order_by(Position.entry_date)
    return list(session.scalars(stmt).all())


def update_highest_price(session: Session, position_id: int, price: float) -> None:
    """트레일링 스탑 추적을 위해 최고가를 갱신한다."""
    position = session.get(Position, position_id)
    if position and price > position.highest_price:
        position.highest_price = price
        session.commit()


# ── 방어적 실행 (Defensive Execution) ──────────────────────


def check_defensive_constraints(session: Session, market_regime: str) -> list[str]:
    """
    방어적 실행 프로토콜의 강제 대기 조건을 검증한다.

    Returns:
        위반 목록 (빈 리스트면 진입 허용)
    """
    violations = []

    # 1) 최근 2건 연속 손절 → 1주일 냉각기
    recent_sells = session.execute(
        select(SellLog)
        .where(SellLog.trigger == "STOP_LOSS")
        .order_by(SellLog.created_at.desc())
        .limit(2)
    ).scalars().all()

    if len(recent_sells) >= 2:
        last_sell_date = recent_sells[0].created_at
        cooldown_end = last_sell_date + timedelta(days=7)
        if datetime.now() < cooldown_end:
            violations.append(
                f"2 consecutive stop-losses detected. "
                f"Cooldown until {cooldown_end:%Y-%m-%d}"
            )

    return violations


# ── 통계 / 리포트 ─────────────────────────────────────────


def get_trade_stats(session: Session) -> dict:
    """전체 매매 통계를 반환한다."""

    sell_logs = session.execute(select(SellLog)).scalars().all()

    if not sell_logs:
        return {"total_trades": 0}

    wins = [s for s in sell_logs if s.pnl_amount > 0]
    losses = [s for s in sell_logs if s.pnl_amount <= 0]

    total_pnl = sum(s.pnl_amount for s in sell_logs)
    avg_win = sum(s.pnl_pct for s in wins) / len(wins) if wins else 0
    avg_loss = sum(s.pnl_pct for s in losses) / len(losses) if losses else 0
    avg_r = sum(s.pnl_r for s in sell_logs) / len(sell_logs)

    return {
        "total_trades": len(sell_logs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(sell_logs) * 100 if sell_logs else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "avg_r_multiple": round(avg_r, 2),
    }
