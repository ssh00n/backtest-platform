"""
포지션 관리 계층 (Position Manager)

protocol: docs/protocols/execution-protocol.md S1 익절, S2-2, S5

진입 후 포지션의 청산 조건을 관리한다:
  - Time Stop: 일정 기간 내 +1R 미달 시 청산
  - Trailing Stop: 진입 이후 최고가에서 -1R 하락 시 청산
  - 부분 익절: Sideways +20% / Bear +15% 도달 시 50% 익절
  - Target Exit: 전고점 -5% 도달 시 전량 청산
  - 다음 박스 손절 상향: 새 박스 형성 시 stop_loss를 새 Box Bottom으로 상향
"""

from dataclasses import dataclass

import pandas as pd

from src.screener.darvas_box import BoxBreakout, DarvasBox


@dataclass
class Position:
    """보유 중인 포지션을 표현한다."""

    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    stop_loss: float          # Box Top - Box Height x 0.25
    target_price: float       # 52w high x 0.95
    risk_r: float             # Entry - Stop Loss (1R 단위)
    regime_at_entry: str      # BULL / SIDEWAYS / BEAR
    time_stop_days: int       # regime별: 30 / 20 / 15
    partial_exit_pct: float | None  # regime별: None / 0.20 / 0.15
    breakout: BoxBreakout     # 원본 돌파 데이터 참조


@dataclass
class PositionCheck:
    """포지션 점검 결과를 표현한다."""

    symbol: str
    action: str               # HOLD / TIME_STOP / TRAILING_STOP / PARTIAL_EXIT / TARGET_EXIT / STOP_LOSS
    reason: str
    current_price: float
    days_held: int
    pnl_r: float              # 현재 손익을 R 단위로


def create_position_from_breakout(
    breakout: BoxBreakout,
    regime: str,
    regime_params: dict,
) -> Position:
    """BoxBreakout으로부터 Position을 생성한다."""
    return Position(
        symbol=breakout.symbol,
        entry_date=breakout.breakout_date,
        entry_price=breakout.breakout_price,
        stop_loss=breakout.stop_loss,
        target_price=breakout.target_price,
        risk_r=breakout.risk_r,
        regime_at_entry=regime,
        time_stop_days=regime_params.get("time_stop_days", 20),
        partial_exit_pct=regime_params.get("partial_exit_pct"),
        breakout=breakout,
    )


def check_stop_loss(
    position: Position,
    current_price: float,
    current_date: pd.Timestamp,
) -> PositionCheck | None:
    """기본 손절 확인: 현재가가 stop_loss 이하이면 STOP_LOSS 반환."""
    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    if current_price <= position.stop_loss:
        return PositionCheck(
            symbol=position.symbol,
            action="STOP_LOSS",
            reason=f"현재가 ${current_price:.2f} <= 손절선 ${position.stop_loss:.2f}",
            current_price=current_price,
            days_held=days_held,
            pnl_r=pnl_r,
        )
    return None


def check_time_stop(
    position: Position,
    current_price: float,
    current_date: pd.Timestamp,
) -> PositionCheck | None:
    """
    Time Stop: 진입 후 time_stop_days 이내에 +1R 수익 미달성 시 청산.

    프로토콜: "+1R 이상 수익이 발생하지 않으면 청산"
    Bull: 30일, Sideways: 20일, Bear: 15일
    """
    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    if days_held >= position.time_stop_days and pnl_r < 1.0:
        return PositionCheck(
            symbol=position.symbol,
            action="TIME_STOP",
            reason=(
                f"{days_held}일 경과 (한도 {position.time_stop_days}일), "
                f"수익 {pnl_r:+.2f}R < +1.0R"
            ),
            current_price=current_price,
            days_held=days_held,
            pnl_r=pnl_r,
        )
    return None


def check_trailing_stop(
    position: Position,
    high_since_entry: float,
    current_price: float,
    current_date: pd.Timestamp,
    trailing_r_mult: float = 1.0,
) -> PositionCheck | None:
    """
    Trailing Stop: 진입 이후 최고가에서 -(trailing_r_mult)R 하락 시 청산.

    Args:
        trailing_r_mult: R 배수 (기본 1.0 = -1R, 1.5 = -1.5R)
    high_since_entry는 호출자가 추적하여 전달한다.
    """
    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    trailing_stop_level = high_since_entry - position.risk_r * trailing_r_mult
    if current_price <= trailing_stop_level and high_since_entry > position.entry_price:
        return PositionCheck(
            symbol=position.symbol,
            action="TRAILING_STOP",
            reason=(
                f"고점 ${high_since_entry:.2f}에서 -1R(${position.risk_r:.2f}) 하락, "
                f"트레일링 스탑 ${trailing_stop_level:.2f} 이탈"
            ),
            current_price=current_price,
            days_held=days_held,
            pnl_r=pnl_r,
        )
    return None


def check_partial_exit(
    position: Position,
    current_price: float,
    current_date: pd.Timestamp,
) -> PositionCheck | None:
    """
    부분 익절 확인.

    Sideways: +20% 도달 시 50% 익절
    Bear: +15% 도달 시 50% 익절
    Bull: 적용 안 함 (partial_exit_pct is None)
    """
    if position.partial_exit_pct is None:
        return None

    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    pct_gain = (current_price - position.entry_price) / position.entry_price
    if pct_gain >= position.partial_exit_pct:
        return PositionCheck(
            symbol=position.symbol,
            action="PARTIAL_EXIT",
            reason=(
                f"+{pct_gain*100:.1f}% 도달 (기준 +{position.partial_exit_pct*100:.0f}%), "
                f"50% 포지션 익절 권고"
            ),
            current_price=current_price,
            days_held=days_held,
            pnl_r=pnl_r,
        )
    return None


def check_target_exit(
    position: Position,
    current_price: float,
    current_date: pd.Timestamp,
) -> PositionCheck | None:
    """전고점 -5% 도달 시 전량 청산."""
    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    if current_price >= position.target_price:
        return PositionCheck(
            symbol=position.symbol,
            action="TARGET_EXIT",
            reason=(
                f"목표가 ${position.target_price:.2f} (전고점 -5%) 도달, "
                f"전량 청산 권고"
            ),
            current_price=current_price,
            days_held=days_held,
            pnl_r=pnl_r,
        )
    return None


def evaluate_position(
    position: Position,
    current_price: float,
    current_date: pd.Timestamp,
    high_since_entry: float,
    trailing_r_mult: float = 1.0,
) -> PositionCheck:
    """
    통합 평가: 모든 청산 조건을 우선순위에 따라 확인한다.

    우선순위:
      1. Stop Loss hit (기본 손절)
      2. Time Stop (기간 내 +1R 미달)
      3. Trailing Stop (고점 대비 -1R)
      4. Partial Exit (부분 익절)
      5. Target Exit (전고점 -5%)
      6. HOLD (유지)
    """
    days_held = _business_days(position.entry_date, current_date)
    pnl_r = _compute_pnl_r(position, current_price)

    # 1. Stop Loss
    result = check_stop_loss(position, current_price, current_date)
    if result is not None:
        return result

    # 2. Time Stop
    result = check_time_stop(position, current_price, current_date)
    if result is not None:
        return result

    # 3. Trailing Stop
    result = check_trailing_stop(position, high_since_entry, current_price, current_date, trailing_r_mult)
    if result is not None:
        return result

    # 4. Partial Exit
    result = check_partial_exit(position, current_price, current_date)
    if result is not None:
        return result

    # 5. Target Exit
    result = check_target_exit(position, current_price, current_date)
    if result is not None:
        return result

    # 6. HOLD
    return PositionCheck(
        symbol=position.symbol,
        action="HOLD",
        reason=f"청산 조건 미충족, 보유 유지 ({pnl_r:+.2f}R, {days_held}일)",
        current_price=current_price,
        days_held=days_held,
        pnl_r=pnl_r,
    )


def update_stop_on_new_box(position: Position, new_box: DarvasBox) -> Position:
    """
    새 박스 형성 시 stop_loss를 new_box.box_bottom으로 상향.

    프로토콜: "새로운 박스가 형성되면 손절선을 새 Box Bottom으로 상향"
    손절선은 상향만 가능 (하향 불가).
    """
    new_stop = new_box.box_bottom
    if new_stop > position.stop_loss:
        return Position(
            symbol=position.symbol,
            entry_date=position.entry_date,
            entry_price=position.entry_price,
            stop_loss=new_stop,
            target_price=position.target_price,
            risk_r=position.entry_price - new_stop,
            regime_at_entry=position.regime_at_entry,
            time_stop_days=position.time_stop_days,
            partial_exit_pct=position.partial_exit_pct,
            breakout=position.breakout,
        )
    return position


# ── 내부 헬퍼 ────────────────────────────────────────────


def _business_days(start: pd.Timestamp, end: pd.Timestamp) -> int:
    """두 날짜 사이의 거래일 수를 계산한다."""
    if not isinstance(start, pd.Timestamp):
        start = pd.Timestamp(start)
    if not isinstance(end, pd.Timestamp):
        end = pd.Timestamp(end)
    return len(pd.bdate_range(start, end)) - 1  # 당일 제외


def _compute_pnl_r(position: Position, current_price: float) -> float:
    """현재 손익을 R 단위로 계산한다."""
    if position.risk_r <= 0:
        return 0.0
    return (current_price - position.entry_price) / position.risk_r
