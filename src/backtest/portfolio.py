"""
백테스트 포트폴리오 상태 관리

포지션 진입/청산, 현금 추적, equity curve 기록을 담당한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.screener.darvas_box import BoxBreakout
from src.screener.position_manager import Position, create_position_from_breakout
from src.utils.logger import get_logger

log = get_logger(__name__)


# ── 설정 ──────────────────────────────────────────────────


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    max_positions: int = 5
    position_size_pct: float = 0.20   # 포지션당 자본의 20%
    commission_pct: float = 0.0       # Alpaca 수수료 무료
    slippage_pct: float = 0.001       # 0.1% 슬리피지

    # ── 개선 파라미터 (v1) ──
    trailing_stop_r: float = 1.0      # Trailing stop: 고점 대비 -NR (기본 1.0R)
    confirm_breakout: bool = False    # True: 돌파 다음날 종가 확인 후 진입
    min_rr_override: float | None = None  # None이면 기본 3.0 사용
    min_vol_ratio_override: float | None = None  # None이면 regime 기본값

    # ── 이벤트 필터 (v3 — 승훈 전략 방향) ──────────────────────
    #
    # 핵심 인사이트: 이벤트 반응 예측은 불확실성 ↑ → NO_EVENT가 압도적으로 유리
    # NO_EVENT WR 66~75%, PF 3.5~4.1 vs EARNINGS_BEAT WR 36~40%, PF 1.1
    #
    use_events: bool = True           # True: 이벤트 필터 활성화
    event_filter_mode: str = "earnings_block"
    # 모드:
    #   "no_event_only"   ← 권장: 순수 기술적 돌파만 (이벤트 없는 종목만 진입)
    #   "miss_block"      : EARNINGS_MISS만 차단, 나머지 허용
    #   "earnings_block"  : 어닝 근처 모두 차단 (8-K CATALYST는 허용)
    #   "none"            : 필터 없음 (구 동작)
    event_window_before: int = 7          # 이벤트 탐색 범위 — 돌파 이전 N일
    event_window_after: int = 3           # 이벤트 탐색 범위 — 돌파 이후 N일

    # ── Accumulation Quality Score (등급제 사이징) ──────────
    use_accumulation_score: bool = False  # True: 등급제 포지션 사이징 활성화
    accumulation_min_score: float = 50.0  # D등급 (<50) 진입 차단
    # 등급별 사이즈 배수: A+/A=1.0, B=0.7, C=0.5, D=차단
    event_fail_open: bool = True          # API 실패 시 True=통과 / False=차단
    # ── 구버전 호환 (deprecated) ──
    event_block_threshold: int = -2
    event_boost_threshold: int = 3
    event_boost_rr_discount: float = 1.0

    # ── L2: 박스 품질 필터 (기관 축적 패턴) ──────────────────────────────────
    #
    # 기관이 조용히 포지션을 쌓는 패턴 포착: 타이트 박스 + 충분한 기간 + 거래량 축적
    # NO_EVENT보다 robust: 데이터 증가해도 안정적으로 작동하는 양성 기준
    #
    use_box_quality_filter: bool = False   # True: 박스 품질 필터 활성화
    box_quality_min_score: float = 50.0    # 최소 점수 (0~100; 권장 B급=55+, 경계=35+)
    # 점수 구성: 타이트함(40점) + 기간(30점) + 거래량 추세(30점)

    # ── L4: 매크로 필터 (v3) ──
    use_macro_filter: bool = False    # True: 매크로 리스크 기반 진입 필터
    macro_extreme_action: str = "block"      # "block" = 차단
    macro_high_action: str = "block"         # "block" or "reduce"
    macro_medium_action: str = "reduce"      # "reduce" = 포지션 50% + R:R +0.5


# ── 거래 기록 ─────────────────────────────────────────────


@dataclass
class TradeRecord:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp | None
    exit_price: float | None
    exit_action: str | None
    shares: float
    pnl: float
    pnl_pct: float
    pnl_r: float
    regime_at_entry: str
    holding_days: int
    partial: bool = False


# ── 보유 포지션 ───────────────────────────────────────────


@dataclass
class OpenPosition:
    """백테스트 내 개별 보유 포지션."""

    position: Position
    shares: float
    high_since_entry: float
    partial_exited: bool = False


# ── 포트폴리오 ───────────────────────────────────────────


class Portfolio:
    """포트폴리오 전체 상태를 관리한다."""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.cash: float = self.config.initial_capital
        self.open_positions: dict[str, OpenPosition] = {}
        self.closed_trades: list[TradeRecord] = []
        self.equity_curve: list[tuple[pd.Timestamp, float]] = []

    # ── 조회 ──────────────────────────────────────────

    def can_open_position(self) -> bool:
        """최대 동시 보유 한도 + 현금 확인."""
        if len(self.open_positions) >= self.config.max_positions:
            return False
        required = self.config.initial_capital * self.config.position_size_pct
        return self.cash >= required

    def get_total_equity(self, prices: dict[str, float]) -> float:
        """현금 + 보유 포지션 시가총액."""
        equity = self.cash
        for symbol, op in self.open_positions.items():
            price = prices.get(symbol, op.position.entry_price)
            equity += op.shares * price
        return equity

    # ── 진입 ──────────────────────────────────────────

    def open_position(
        self,
        breakout: BoxBreakout,
        regime: str,
        regime_params: dict,
        date: pd.Timestamp,
        size_multiplier: float = 1.0,
    ) -> bool:
        """포지션 진입. size_multiplier로 등급별 사이징 (0.5~1.0). 성공 시 True."""
        symbol = breakout.symbol

        if symbol in self.open_positions:
            return False
        if not self.can_open_position():
            return False

        position = create_position_from_breakout(breakout, regime, regime_params)

        # 슬리피지 적용: 진입가를 breakout 가격보다 약간 높게
        entry_price = breakout.breakout_price * (1 + self.config.slippage_pct)

        # 포지션 규모 산정 (등급별 사이즈 조절)
        alloc = self.config.initial_capital * self.config.position_size_pct * size_multiplier
        shares = alloc / entry_price

        cost = shares * entry_price
        if cost > self.cash:
            return False

        self.cash -= cost

        # Position의 entry_price를 슬리피지 반영 가격으로 조정
        position = Position(
            symbol=position.symbol,
            entry_date=date,
            entry_price=entry_price,
            stop_loss=position.stop_loss,
            target_price=position.target_price,
            risk_r=entry_price - position.stop_loss,
            regime_at_entry=position.regime_at_entry,
            time_stop_days=position.time_stop_days,
            partial_exit_pct=position.partial_exit_pct,
            breakout=position.breakout,
        )

        self.open_positions[symbol] = OpenPosition(
            position=position,
            shares=shares,
            high_since_entry=entry_price,
        )
        log.debug("[%s] ENTRY %s @ $%.2f, %d shares, cash=$%.0f",
                  date.strftime("%Y-%m-%d"), symbol, entry_price, int(shares), self.cash)
        return True

    # ── 전량 청산 ─────────────────────────────────────

    def close_position(
        self,
        symbol: str,
        date: pd.Timestamp,
        price: float,
        action: str,
    ) -> TradeRecord | None:
        """전량 청산하고 TradeRecord를 반환한다."""
        op = self.open_positions.get(symbol)
        if op is None:
            return None

        # 슬리피지 적용: 청산가를 약간 낮게
        exit_price = price * (1 - self.config.slippage_pct)
        proceeds = op.shares * exit_price
        self.cash += proceeds

        pos = op.position
        pnl = (exit_price - pos.entry_price) * op.shares
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        pnl_r = (exit_price - pos.entry_price) / pos.risk_r if pos.risk_r > 0 else 0.0
        days_held = len(pd.bdate_range(pos.entry_date, date)) - 1

        record = TradeRecord(
            symbol=symbol,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date,
            exit_price=exit_price,
            exit_action=action,
            shares=op.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            pnl_r=pnl_r,
            regime_at_entry=pos.regime_at_entry,
            holding_days=days_held,
            partial=False,
        )

        del self.open_positions[symbol]
        self.closed_trades.append(record)
        log.debug("[%s] EXIT  %s @ $%.2f (%s), pnl=%.2fR, cash=$%.0f",
                  date.strftime("%Y-%m-%d"), symbol, exit_price, action, pnl_r, self.cash)
        return record

    # ── 부분 청산 ─────────────────────────────────────

    def partial_close(
        self,
        symbol: str,
        date: pd.Timestamp,
        price: float,
        fraction: float = 0.5,
    ) -> TradeRecord | None:
        """포지션의 fraction 비율을 익절한다."""
        op = self.open_positions.get(symbol)
        if op is None or op.partial_exited:
            return None

        exit_price = price * (1 - self.config.slippage_pct)
        exit_shares = op.shares * fraction
        proceeds = exit_shares * exit_price
        self.cash += proceeds

        pos = op.position
        pnl = (exit_price - pos.entry_price) * exit_shares
        pnl_pct = (exit_price - pos.entry_price) / pos.entry_price
        pnl_r = (exit_price - pos.entry_price) / pos.risk_r if pos.risk_r > 0 else 0.0
        days_held = len(pd.bdate_range(pos.entry_date, date)) - 1

        record = TradeRecord(
            symbol=symbol,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=date,
            exit_price=exit_price,
            exit_action="PARTIAL_EXIT",
            shares=exit_shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            pnl_r=pnl_r,
            regime_at_entry=pos.regime_at_entry,
            holding_days=days_held,
            partial=True,
        )

        # 잔여 포지션 갱신
        op.shares -= exit_shares
        op.partial_exited = True
        self.closed_trades.append(record)
        log.debug("[%s] PARTIAL %s %.0f%% @ $%.2f, pnl=%.2fR, remain=%d shares",
                  date.strftime("%Y-%m-%d"), symbol, fraction * 100,
                  exit_price, pnl_r, int(op.shares))
        return record

    # ── Equity 갱신 ───────────────────────────────────

    def update_equity(self, date: pd.Timestamp, prices: dict[str, float]) -> None:
        """일일 equity를 기록한다."""
        equity = self.get_total_equity(prices)
        self.equity_curve.append((date, equity))
