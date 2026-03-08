"""
백테스트 시뮬레이션 엔진

기존 screener 모듈을 재사용하여 날짜별로 진입/청산을 시뮬레이션한다.
핵심 제약: Look-ahead bias 방지 — 모든 데이터를 df[:current_date]로 슬라이싱.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.backtest.portfolio import BacktestConfig, OpenPosition, Portfolio
from src.screener.darvas_box import analyze_symbol, find_darvas_boxes
from src.screener.market_regime import (
    MarketRegime,
    classify_regime,
    compute_breadth,
    get_regime_params,
)
from src.screener.position_manager import (
    evaluate_position,
    update_stop_on_new_box,
)
from src.screener.price_screener import compute_price_signals
from src.screener.volume_protocol import classify_volume_regime, compute_volume_signals
from src.utils.logger import get_logger

# 이벤트 시스템 (lazy import — use_events=False일 때 불필요)
_event_scorer = None

def _get_event_signal(symbol: str, date_str: str):
    """이벤트 스코어 조회 (lazy import)."""
    global _event_scorer
    if _event_scorer is None:
        from src.events.event_scorer import evaluate_events
        _event_scorer = evaluate_events
    return _event_scorer(symbol, date_str)

log = get_logger(__name__)

# 최소 데이터 길이 (SMA 200 + 여유)
_MIN_DATA_LEN = 220

# Regime 재계산 주기 (거래일)
_REGIME_RECHECK_INTERVAL = 5


@dataclass
class BacktestResult:
    config: BacktestConfig
    portfolio: Portfolio
    regime_history: list[tuple[pd.Timestamp, str]] = field(default_factory=list)
    daily_regimes: pd.Series = field(default_factory=lambda: pd.Series(dtype=str))
    metrics: dict = field(default_factory=dict)


def run_backtest(
    bars: pd.DataFrame,
    spy_df: pd.DataFrame,
    config: BacktestConfig | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    bear_exit_overrides: dict[int, bool] | None = None,
) -> BacktestResult:
    """
    메인 백테스트 루프.

    Args:
        bars: MultiIndex(symbol, timestamp) 전체 OHLCV 데이터
        spy_df: SPY 단일 심볼 OHLCV (DatetimeIndex)
        config: 백테스트 설정
        start_date: 시뮬레이션 시작일 (없으면 데이터 시작 + 220일)
        end_date: 시뮬레이션 종료일 (없으면 데이터 끝)
        bear_exit_overrides: Bear 탈출 조건 수동 충족
    """
    config = config or BacktestConfig()
    portfolio = Portfolio(config)

    # 거래일 범위 결정
    spy_dates = spy_df.index.sort_values()
    tz = spy_dates.tz  # Alpaca 데이터는 UTC timezone-aware

    if start_date:
        ts = pd.Timestamp(start_date, tz=tz)
        spy_dates = spy_dates[spy_dates >= ts]
    else:
        # SMA200 계산에 최소 220일 필요
        spy_dates = spy_dates[_MIN_DATA_LEN:]
    if end_date:
        ts = pd.Timestamp(end_date, tz=tz)
        spy_dates = spy_dates[spy_dates <= ts]

    trading_days = spy_dates.tolist()
    if not trading_days:
        log.warning("No trading days in range")
        return BacktestResult(config=config, portfolio=portfolio)

    log.info("Backtest: %s ~ %s (%d trading days)",
             trading_days[0].strftime("%Y-%m-%d"),
             trading_days[-1].strftime("%Y-%m-%d"),
             len(trading_days))

    # 심볼 목록 (SPY 제외)
    all_symbols = [s for s in bars.index.get_level_values("symbol").unique() if s != "SPY"]

    # 심볼별 데이터 미리 추출 (반복 xs 비용 절약)
    symbol_dfs: dict[str, pd.DataFrame] = {}
    for sym in all_symbols:
        try:
            df = bars.xs(sym, level="symbol")
            if len(df) >= 60:
                symbol_dfs[sym] = df.sort_index()
        except KeyError:
            continue

    log.info("Universe: %d symbols with sufficient data", len(symbol_dfs))

    # ── 매크로 캘린더 사전 생성 (v3) ──────────────────
    macro_calendar: dict[str, "MacroRiskLevel"] = {}
    if config.use_macro_filter:
        from src.macro.macro_backtest import build_macro_calendar_from_data
        from src.macro.macro_detector import MacroRiskLevel
        _start = start_date or trading_days[0].strftime("%Y-%m-%d")
        _end = end_date or trading_days[-1].strftime("%Y-%m-%d")
        macro_calendar = build_macro_calendar_from_data(spy_df, _start, _end)

    # Regime 캐시
    current_regime: MarketRegime | None = None
    regime_history: list[tuple[pd.Timestamp, str]] = []
    daily_regime_records: list[tuple[pd.Timestamp, str]] = []
    last_regime_check = 0

    for day_idx, today in enumerate(trading_days):
        # ── 1) Regime 판단 (주기적 갱신) ──────────────
        if current_regime is None or (day_idx - last_regime_check) >= _REGIME_RECHECK_INTERVAL:
            spy_slice = spy_df.loc[:today]
            if len(spy_slice) >= _MIN_DATA_LEN:
                try:
                    new_regime = classify_regime(
                        spy_slice,
                        bear_exit_overrides=bear_exit_overrides,
                    )
                    if current_regime is None or new_regime.regime != current_regime.regime:
                        log.info("[%s] Regime: %s", today.strftime("%Y-%m-%d"), new_regime.regime)
                        regime_history.append((today, new_regime.regime))
                    current_regime = new_regime
                except (ValueError, Exception) as e:
                    log.debug("Regime check failed on %s: %s", today.strftime("%Y-%m-%d"), e)
                    if current_regime is None:
                        # 첫 날에 실패하면 SIDEWAYS로 기본값
                        current_regime = MarketRegime(
                            regime="SIDEWAYS", spy_price=0, sma_200=0,
                            sma_200_slope=0, vix=None, breadth_pct=None,
                            bear_exit_conditions_met=0,
                            params=get_regime_params("SIDEWAYS"),
                        )
                        regime_history.append((today, "SIDEWAYS"))
            last_regime_check = day_idx

        daily_regime_records.append((today, current_regime.regime))
        params = current_regime.params

        # 당일 종가 수집 (equity 및 포지션 평가용)
        today_prices: dict[str, float] = {}
        for sym, sdf in symbol_dfs.items():
            if today in sdf.index:
                today_prices[sym] = float(sdf.loc[today, "close"])

        # ── 2) 기존 포지션 관리 ───────────────────────
        _manage_positions(portfolio, symbol_dfs, today, today_prices, params, config)

        # ── 3) 신규 진입 (Bear + Macro 게이트 통과 시) ────────
        bear_blocked = (
            current_regime.regime == "BEAR"
            and current_regime.bear_exit_conditions_met < 2
        )

        # 매크로 필터 체크
        macro_blocked = False
        if config.use_macro_filter and macro_calendar:
            from src.macro.macro_detector import MacroRiskLevel
            day_key = today.strftime("%Y-%m-%d")
            macro_risk = macro_calendar.get(day_key, MacroRiskLevel.LOW)
            if macro_risk == MacroRiskLevel.EXTREME:
                macro_blocked = True
            elif macro_risk == MacroRiskLevel.HIGH:
                macro_blocked = (config.macro_high_action == "block")
            # MEDIUM은 진입은 허용, _scan_entries에서 R:R 상향 가능 (향후)

        if not bear_blocked and not macro_blocked and portfolio.can_open_position():
            _scan_entries(
                portfolio, symbol_dfs, spy_df, today, current_regime, params, config,
            )

        # ── 4) Equity curve 갱신 ──────────────────────
        portfolio.update_equity(today, today_prices)

        # 진행 상황 로그 (50일마다)
        if (day_idx + 1) % 50 == 0:
            equity = portfolio.equity_curve[-1][1] if portfolio.equity_curve else config.initial_capital
            log.info("[%s] Day %d/%d | Equity: $%.0f | Open: %d | Trades: %d",
                     today.strftime("%Y-%m-%d"), day_idx + 1, len(trading_days),
                     equity, len(portfolio.open_positions), len(portfolio.closed_trades))

    # ── 최종: 미청산 포지션 시장가 청산 ───────────────
    if portfolio.open_positions:
        last_day = trading_days[-1]
        last_prices = {}
        for sym, sdf in symbol_dfs.items():
            if last_day in sdf.index:
                last_prices[sym] = float(sdf.loc[last_day, "close"])

        for symbol in list(portfolio.open_positions.keys()):
            price = last_prices.get(symbol)
            if price:
                portfolio.close_position(symbol, last_day, price, "END_OF_BACKTEST")

    # 결과 구성
    daily_regimes = pd.Series(
        [r for _, r in daily_regime_records],
        index=pd.DatetimeIndex([d for d, _ in daily_regime_records]),
        name="regime",
    )

    log.info("Backtest complete: %d trades, final equity $%.0f",
             len(portfolio.closed_trades),
             portfolio.equity_curve[-1][1] if portfolio.equity_curve else config.initial_capital)

    return BacktestResult(
        config=config,
        portfolio=portfolio,
        regime_history=regime_history,
        daily_regimes=daily_regimes,
    )


# ── 포지션 관리 ──────────────────────────────────────────────


def _manage_positions(
    portfolio: Portfolio,
    symbol_dfs: dict[str, pd.DataFrame],
    today: pd.Timestamp,
    today_prices: dict[str, float],
    params: dict,
    config: BacktestConfig | None = None,
) -> None:
    """기존 포지션을 점검하고 청산 조건 충족 시 청산한다."""
    for symbol in list(portfolio.open_positions.keys()):
        op = portfolio.open_positions[symbol]
        price = today_prices.get(symbol)
        if price is None:
            continue

        # a) high_since_entry 갱신
        sdf = symbol_dfs.get(symbol)
        if sdf is not None and today in sdf.index:
            today_high = float(sdf.loc[today, "high"])
            op.high_since_entry = max(op.high_since_entry, today_high)

        # b) 새 박스 형성 확인 → 손절 상향
        if sdf is not None:
            sliced = sdf.loc[:today]
            if len(sliced) >= params.get("box_min_days", 10):
                boxes = find_darvas_boxes(
                    sliced,
                    min_days=params.get("box_min_days", 10),
                    max_width_pct=params.get("box_max_width_pct", 0.15),
                )
                if boxes:
                    latest_box = boxes[-1]
                    # 진입 이후 형성된 박스만 고려
                    if pd.Timestamp(latest_box.box_end).date() >= pd.Timestamp(op.position.entry_date).date():
                        op.position = update_stop_on_new_box(op.position, latest_box)

        # c) evaluate_position → 청산 조건 확인
        trailing_r = config.trailing_stop_r if config else 1.0
        check = evaluate_position(
            op.position, price, today, op.high_since_entry,
            trailing_r_mult=trailing_r,
        )

        if check.action == "PARTIAL_EXIT":
            if not op.partial_exited:
                portfolio.partial_close(symbol, today, price, fraction=0.5)
        elif check.action != "HOLD":
            portfolio.close_position(symbol, today, price, check.action)


# ── 신규 진입 스캔 ───────────────────────────────────────────


def _scan_entries(
    portfolio: Portfolio,
    symbol_dfs: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame,
    today: pd.Timestamp,
    regime: MarketRegime,
    params: dict,
    config: BacktestConfig | None = None,
) -> None:
    """Fail-Fast Pipeline으로 당일 돌파 종목을 찾아 진입한다."""
    config = config or BacktestConfig()
    candidates = []

    # 최소 R:R 기준 (config override 또는 기본 3.0)
    min_rr = config.min_rr_override if config.min_rr_override is not None else 3.0

    # 거래량 비율 override
    vol_ratio_override = config.min_vol_ratio_override

    for symbol, sdf in symbol_dfs.items():
        if symbol in portfolio.open_positions:
            continue

        # Look-ahead bias 방지: 당일까지만 슬라이싱
        sliced = sdf.loc[:today]
        if len(sliced) < _MIN_DATA_LEN:
            continue

        # Step 1: Deep Discount
        price_df = compute_price_signals(
            sliced,
            deep_discount_threshold=params["deep_discount_threshold"],
        )
        latest = price_df.iloc[-1]
        if not latest.get("sig_deep_discount", False):
            continue

        # Step 2: Volume Signal
        vol_df = compute_volume_signals(sliced, regime=regime.regime)
        vol_latest = vol_df.iloc[-1]
        vol_regime = classify_volume_regime(vol_latest)

        # 거래량 비율 추가 필터 (override가 있으면 적용)
        if vol_ratio_override is not None:
            if vol_latest.get("vol_ratio", 0) < vol_ratio_override:
                continue

        if regime.regime == "BEAR":
            if vol_regime != "CONFIRMATION":
                continue
        else:
            if vol_regime not in ("ACCUMULATION", "CONFIRMATION"):
                continue

        # Step 3: Darvas Box + Breakout
        result = analyze_symbol(
            sliced,
            symbol=symbol,
            min_days=params["box_min_days"],
            max_width_pct=params["box_max_width_pct"],
            breakout_vol_ratio=params["breakout_vol_ratio"],
            min_rr=min_rr,
        )

        # 당일 돌파만 진입 (과거 돌파 재진입 금지)
        for breakout in result["actionable"]:
            bd = pd.Timestamp(breakout.breakout_date)
            # tz-aware 비교를 위해 날짜만 추출
            if bd.date() == today.date():
                if config.confirm_breakout:
                    # Breakout confirmation: 돌파일은 후보로 저장만
                    # pending_breakouts에 추가 (다음 날 확인)
                    _add_pending_breakout(portfolio, breakout, today)
                else:
                    candidates.append(breakout)

    # Confirmation 모드: 전날 pending된 돌파 중 오늘도 Box Top 위인 것만 진입
    if config.confirm_breakout:
        confirmed = _check_pending_breakouts(portfolio, symbol_dfs, today)
        candidates.extend(confirmed)

    # ── 이벤트 필터 (v3 — miss_block/earnings_block 등 이벤트 차단) ──
    # ACC와 독립 실행: ACC는 사이징만, 이벤트 필터는 차단만 담당
    if config.use_events and config.event_filter_mode != "none" and candidates:
        from src.events.event_filter import check_event_filter
        filtered = []
        for breakout in candidates:
            result = check_event_filter(breakout.symbol, today, config)
            if not result.allow:
                log.debug("[%s] EVENT BLOCK %s: %s (quality=%s)",
                          today.strftime("%Y-%m-%d"), breakout.symbol,
                          result.reason, result.quality)
                continue
            filtered.append(breakout)
        candidates = filtered

    # ── Accumulation Quality Score (등급제 사이징) ──
    size_map: dict[str, float] = {}  # symbol → size_multiplier
    if config.use_accumulation_score and candidates:
        from src.screener.accumulation_score import compute_accumulation_score

        scored = []
        for breakout in candidates:
            sym = breakout.symbol
            price_df = symbol_dfs.get(sym)
            # event_type 조회 (이벤트 필터 결과 활용)
            ev_type = "NONE"
            if config.use_events:
                from src.events.event_filter import check_event_filter
                ev_result = check_event_filter(sym, today, config)
                ev_type = ev_result.quality or "NONE"
            acc = compute_accumulation_score(
                breakout=breakout,
                price_df=price_df,
                event_type=ev_type,
            )
            if acc.score < config.accumulation_min_score:
                log.debug("[%s] ACC BLOCK %s: score=%.0f grade=%s — %s",
                          today.strftime("%Y-%m-%d"), sym, acc.score,
                          acc.grade.value, "; ".join(acc.warnings or acc.reasons[:2]))
                continue
            # 등급별 사이즈 배수 (v2: C/B 상향)
            if acc.score >= 80:
                mult = 1.0      # A+/A: 풀 사이즈
            elif acc.score >= 65:
                mult = 0.85     # B: 85%
            else:
                mult = 0.7      # C: 70%
            size_map[sym] = mult
            scored.append(breakout)
            log.info("[%s] ACC %s: score=%.0f grade=%s size=%.1fx",
                     today.strftime("%Y-%m-%d"), sym, acc.score,
                     acc.grade.value, mult)
        candidates = scored

    # R:R 높은 순서로 정렬
    candidates.sort(key=lambda b: b.rr_ratio, reverse=True)

    for breakout in candidates:
        if not portfolio.can_open_position():
            break
        mult = size_map.get(breakout.symbol, 1.0)
        portfolio.open_position(breakout, regime.regime, params, today,
                                size_multiplier=mult)


# ── Breakout Confirmation 헬퍼 ────────────────────────────


# pending_breakouts 저장소 (Portfolio 객체에 동적으로 추가)
def _add_pending_breakout(
    portfolio: Portfolio,
    breakout: "BoxBreakout",
    date: pd.Timestamp,
) -> None:
    """돌파 후보를 다음 날 확인용으로 저장."""
    if not hasattr(portfolio, "_pending_breakouts"):
        portfolio._pending_breakouts = []
    portfolio._pending_breakouts.append((breakout, date))


def _check_pending_breakouts(
    portfolio: Portfolio,
    symbol_dfs: dict[str, pd.DataFrame],
    today: pd.Timestamp,
) -> list:
    """전날 pending된 돌파 중 오늘 종가가 여전히 Box Top 위인 것만 반환."""
    if not hasattr(portfolio, "_pending_breakouts"):
        return []

    confirmed = []
    remaining = []

    for breakout, pending_date in portfolio._pending_breakouts:
        # 전날(또는 이전) pending만 확인 (당일 pending은 내일 확인)
        if pending_date.date() >= today.date():
            remaining.append((breakout, pending_date))
            continue

        # 2거래일 이상 지난 pending은 만료
        days_since = (today - pending_date).days
        if days_since > 5:
            continue

        symbol = breakout.symbol
        if symbol in portfolio.open_positions:
            continue

        sdf = symbol_dfs.get(symbol)
        if sdf is None or today not in sdf.index:
            remaining.append((breakout, pending_date))
            continue

        today_close = float(sdf.loc[today, "close"])
        if today_close > breakout.box.box_top:
            # 확인 완료: 오늘 종가가 여전히 Box Top 위
            # 진입가를 오늘 종가로 업데이트
            from src.screener.darvas_box import BoxBreakout
            confirmed_breakout = BoxBreakout(
                symbol=breakout.symbol,
                box=breakout.box,
                breakout_date=today,
                breakout_price=today_close,
                breakout_vol_ratio=breakout.breakout_vol_ratio,
                stop_loss=breakout.stop_loss,
                risk_r=today_close - breakout.stop_loss,
                target_price=breakout.target_price,
                reward=breakout.target_price - today_close,
                rr_ratio=(breakout.target_price - today_close) / (today_close - breakout.stop_loss) if (today_close - breakout.stop_loss) > 0 else 0,
                rr_pass=True,
            )
            confirmed.append(confirmed_breakout)
        # else: 종가가 Box Top 아래 → 가짜 돌파, 버림

    portfolio._pending_breakouts = remaining
    return confirmed
