"""
일일 스크리너 — Phase A (Fail-Fast Pipeline)

protocol: docs/protocols/screening-pipeline.md

TA 지양 원칙: 거래량만을 기술적 분석 데이터로 사용한다.

[Macro 게이트] -> [S&P 500] -> Step 1: Deep Discount -> Step 2: Volume Signal
    -> Step 3: Darvas Box + R:R >= 3 -> [후보]
"""

from datetime import datetime, timedelta

import pandas as pd

from src.data.client import fetch_daily_bars
from src.data.universe import fetch_sp500_constituents, get_sp500_symbols
from src.data.universe_extended import get_extended_universe
from src.screener.darvas_box import (
    BoxBreakout,
    analyze_symbol,
    format_breakout_report,
)
from src.screener.market_regime import (
    MarketRegime,
    classify_regime,
    compute_breadth,
    format_regime_report,
    get_regime_params,
)
from src.screener.price_screener import compute_price_signals
from src.screener.volume_protocol import classify_volume_regime, compute_volume_signals
from src.utils.logger import get_logger, setup_logging

log = get_logger(__name__)

# Alpaca API에서 실패하는 심볼 (slash 포함 클래스 주식)
_EXCLUDE_SYMBOLS = {"BRK/B", "BF/B"}


def run_daily_screen(
    lookback_days: int = 400,
    bear_exit_overrides: dict[int, bool] | None = None,
    use_extended_universe: bool = True,
) -> dict:
    """
    Phase A 일일 스크리닝 파이프라인 (Fail-Fast 구조).

    TA 지양 원칙: 골든크로스, RSI 등 기술적 지표를 사용하지 않는다.
    회복 증거는 오직 거래량(Accumulation/Confirmation)으로 확인한다.

    Pipeline:
        Phase 0: Macro 게이트 (SPY vs SMA200, VIX, Breadth)
        Step 1:  Deep Discount 필터 (52주 고점 대비 하락률)
        Step 2:  Volume Signal 필터 (매집/확인 = 회복의 거래량 증거)
        Step 3:  Darvas Box + R:R >= 3 필터

    각 단계에서 탈락 종목 수를 로그에 기록한다.

    Args:
        lookback_days: 데이터 조회 기간
        bear_exit_overrides: Bear 탈출 조건 수동 충족 (Phase 1-3 반자동)

    Returns:
        {
            "regime": MarketRegime,
            "pipeline_stats": dict,
            "deep_discount": pd.DataFrame,
            "volume_signals": pd.DataFrame,
            "boxes_found": pd.DataFrame,
            "breakouts": pd.DataFrame,
            "actionable": pd.DataFrame,
        }
    """
    log.info("Daily Screener — Phase A Fail-Fast Pipeline started")

    # ── 1) Universe 로드 ──────────────────────────────
    if use_extended_universe:
        raw_symbols = get_extended_universe()  # S&P 500 + S&P 400 Mid-Cap
        symbols = [s for s in raw_symbols if s not in _EXCLUDE_SYMBOLS]
        log.info("[1/5] Universe: %d S&P 500+400 symbols (+SPY)", len(symbols))
    else:
        sp500 = fetch_sp500_constituents()
        symbols = [s for s in sp500["symbol"].tolist() if s not in _EXCLUDE_SYMBOLS]
        log.info("[1/5] Universe: %d S&P 500 symbols (+SPY)", len(symbols))

    # SPY는 Macro 게이트에 필요
    all_symbols = list(set(symbols + ["SPY"]))

    # ── 2) 가격 데이터 수집 ───────────────────────────
    end = datetime.now() - timedelta(days=1)
    start = end - timedelta(days=lookback_days)
    log.info("[2/5] Fetching price data: %s ~ %s", f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}")

    bars = fetch_daily_bars(all_symbols, start=start, end=end)
    if bars.empty:
        log.error("No data returned from Alpaca")
        return {}

    log.info("  Data fetched: %s rows", f"{bars.shape[0]:,}")

    # ── Phase 0: Macro 게이트 ─────────────────────────
    log.info("[3/5] Phase 0: Macro Gate")

    spy_df = _extract_symbol(bars, "SPY")
    if spy_df is None or len(spy_df) < 220:
        log.warning("SPY data insufficient (%d rows) — defaulting to SIDEWAYS",
                     len(spy_df) if spy_df is not None else 0)
        regime = MarketRegime(
            regime="SIDEWAYS",
            spy_price=0,
            sma_200=0,
            sma_200_slope=0,
            vix=None,
            breadth_pct=None,
            bear_exit_conditions_met=0,
            params=get_regime_params("SIDEWAYS"),
        )
    else:
        breadth = compute_breadth(bars, window=50)
        regime = classify_regime(
            spy_df,
            vix_df=None,
            breadth_pct=breadth,
            bear_exit_overrides=bear_exit_overrides,
        )

    log.info("\n%s", format_regime_report(regime))
    params = regime.params

    # Bear 게이트: 명시적 중단 + 상세 로그
    if regime.regime == "BEAR" and regime.bear_exit_conditions_met < 2:
        log.warning(
            "BEAR regime: 파이프라인 중단 (exit conditions %d/3, 최소 2 필요)",
            regime.bear_exit_conditions_met,
        )
        return {"regime": regime}

    if regime.regime == "BEAR":
        log.info(
            "BEAR regime: 파이프라인 실행 (exit conditions %d/3 충족, Bear 파라미터 적용)",
            regime.bear_exit_conditions_met,
        )

    # ── Fail-Fast 파이프라인 ──────────────────────────
    log.info("[4/5] Fail-Fast Pipeline with %s parameters (discount=%s%%, vol=%sx, box=%sd)",
             regime.regime,
             f"{params['deep_discount_threshold']*100:.0f}",
             params["breakout_vol_ratio"],
             params["box_min_days"])

    sector_map = dict(zip(sp500["symbol"], sp500["sector"]))
    grouped = bars.groupby(level="symbol")
    total_symbols = len(grouped)

    # Pipeline stats
    stats = {
        "total_symbols": total_symbols,
        "step1_deep_discount": 0,
        "step2_volume": 0,
        "step3_boxes": 0,
        "step3_breakouts": 0,
        "step3_actionable": 0,
    }

    # Step 1: Deep Discount 필터
    deep_discounts = []
    step1_passed = {}  # symbol -> (group_df, sector)

    for idx, (symbol, group_df) in enumerate(grouped):
        if (idx + 1) % 100 == 0:
            log.debug("Step 1 Processing %d/%d...", idx + 1, total_symbols)

        group_df = group_df.droplevel("symbol")
        if len(group_df) < 60:
            continue

        sector = sector_map.get(symbol, "Unknown")

        price_df = compute_price_signals(
            group_df,
            deep_discount_threshold=params["deep_discount_threshold"],
        )
        latest = price_df.iloc[-1]

        drawdown = latest.get("drawdown_from_high")
        if drawdown is not None and drawdown <= params["deep_discount_threshold"]:
            deep_discounts.append({
                "symbol": symbol,
                "close": round(float(latest["close"]), 2),
                "high_52w": round(float(latest["high_52w"]), 2),
                "drawdown_pct": round(drawdown * 100, 1),
                "sector": sector,
            })
            step1_passed[symbol] = (group_df, sector)

    stats["step1_deep_discount"] = len(step1_passed)
    log.info("  Step 1 Deep Discount: %d/%d passed", len(step1_passed), total_symbols)

    # Step 2: Volume Signal 필터 (거래량 = 회복의 유일한 증거)
    # Accumulation(매집) 또는 Confirmation(확인) 시그널이 있는 종목만 통과
    # Bear: Confirmation(확인) 필수 (3단계 거래량 시퀀스)
    step2_passed = {}
    volume_alerts = []

    for symbol, (group_df, sector) in step1_passed.items():
        vol_df = compute_volume_signals(group_df, regime=regime.regime)
        vol_latest = vol_df.iloc[-1]
        vol_regime = classify_volume_regime(vol_latest)

        has_accumulation = vol_regime == "ACCUMULATION"
        has_confirmation = vol_regime == "CONFIRMATION"

        if vol_regime != "NEUTRAL":
            volume_alerts.append({
                "symbol": symbol,
                "regime": vol_regime,
                "vol_ratio": round(float(vol_latest["vol_ratio"]), 2) if pd.notna(vol_latest.get("vol_ratio")) else None,
                "close": round(float(vol_latest["close"]), 2),
                "price_change_pct": round(float(vol_latest["price_change_pct"]) * 100, 2) if pd.notna(vol_latest.get("price_change_pct")) else None,
                "sector": sector,
            })

        if regime.regime == "BEAR":
            # Bear: Confirmation(확인) 필수 — 거래량 3단계 시퀀스의 최종 확인
            if has_confirmation:
                step2_passed[symbol] = (group_df, sector)
        else:
            # Bull/Sideways: Accumulation 또는 Confirmation
            if has_accumulation or has_confirmation:
                step2_passed[symbol] = (group_df, sector)

    stats["step2_volume"] = len(step2_passed)
    log.info("  Step 2 Volume: %d/%d passed", len(step2_passed), len(step1_passed))

    # Step 3: Darvas Box + R:R >= 3 필터
    all_boxes = []
    all_breakouts: list[BoxBreakout] = []
    all_actionable: list[BoxBreakout] = []

    for symbol, (group_df, sector) in step2_passed.items():
        result = analyze_symbol(
            group_df,
            symbol=symbol,
            min_days=params["box_min_days"],
            max_width_pct=params["box_max_width_pct"],
            breakout_vol_ratio=params["breakout_vol_ratio"],
        )

        for box in result["boxes"]:
            all_boxes.append({
                "symbol": symbol,
                "box_top": round(box.box_top, 2),
                "box_bottom": round(box.box_bottom, 2),
                "box_height": round(box.box_height, 2),
                "duration": box.duration_days,
                "start": box.box_start,
                "end": box.box_end,
                "sector": sector,
            })

        all_breakouts.extend(result["breakouts"])
        all_actionable.extend(result["actionable"])

    stats["step3_boxes"] = len(all_boxes)
    stats["step3_breakouts"] = len(all_breakouts)
    stats["step3_actionable"] = len(all_actionable)
    log.info("  Step 3 Boxes: %d found, %d breakouts, %d actionable",
             len(all_boxes), len(all_breakouts), len(all_actionable))

    # ── 5) 결과 정리 ─────────────────────────────────
    log.info("[5/5] Building results...")

    deep_discount_df = (
        pd.DataFrame(deep_discounts).sort_values("drawdown_pct")
        if deep_discounts else pd.DataFrame()
    )
    volume_df = (
        pd.DataFrame(volume_alerts).sort_values("regime")
        if volume_alerts else pd.DataFrame()
    )
    boxes_df = (
        pd.DataFrame(all_boxes).sort_values("end", ascending=False)
        if all_boxes else pd.DataFrame()
    )

    breakouts_data = [_breakout_to_dict(b) for b in all_breakouts]
    breakout_df = (
        pd.DataFrame(breakouts_data).sort_values("rr_ratio", ascending=False)
        if breakouts_data else pd.DataFrame()
    )

    actionable_data = [_breakout_to_dict(b) for b in all_actionable]
    actionable_df = (
        pd.DataFrame(actionable_data).sort_values("rr_ratio", ascending=False)
        if actionable_data else pd.DataFrame()
    )

    # ── 요약 ──────────────────────────────────────────
    log.info("  Pipeline: %d -> Step1(DD:%d) -> Step2(Vol:%d) -> Boxes(%d) -> Breakouts(%d) -> Actionable(%d)",
             stats["total_symbols"],
             stats["step1_deep_discount"],
             stats["step2_volume"],
             stats["step3_boxes"],
             stats["step3_breakouts"],
             stats["step3_actionable"])

    # Sideways 경고
    if regime.regime == "SIDEWAYS":
        log.warning(
            "Sideways regime: 이벤트 매칭 미적용 (Phase A 한계). "
            "수동 이벤트 확인 필요."
        )

    return {
        "regime": regime,
        "pipeline_stats": stats,
        "deep_discount": deep_discount_df,
        "volume_signals": volume_df,
        "boxes_found": boxes_df,
        "breakouts": breakout_df,
        "actionable": actionable_df,
    }


# ── 리포트 출력 ───────────────────────────────────────────


def log_report(results: dict) -> None:
    """스크리닝 결과를 로그에 기록한다."""
    if not results:
        log.warning("No results to report")
        return

    regime: MarketRegime | None = results.get("regime")

    log.info("=" * 70)
    log.info("  MARKET REGIME")
    if regime:
        log.info("\n%s", format_regime_report(regime))

    # Pipeline stats
    stats = results.get("pipeline_stats")
    if stats:
        log.info("=" * 70)
        log.info("  PIPELINE FUNNEL")
        log.info("  Total -> Step1(Deep Discount) -> Step2(Volume) -> Boxes -> Breakouts -> Actionable")
        log.info("  %d -> %d -> %d -> %d -> %d -> %d",
                 stats.get("total_symbols", 0),
                 stats.get("step1_deep_discount", 0),
                 stats.get("step2_volume", 0),
                 stats.get("step3_boxes", 0),
                 stats.get("step3_breakouts", 0),
                 stats.get("step3_actionable", 0))

    _log_section("DEEP DISCOUNT STOCKS", results.get("deep_discount"))
    _log_section("VOLUME SIGNALS", results.get("volume_signals"), group_by="regime")
    _log_section("DARVAS BOXES (recent 20)", results.get("boxes_found"), head=20)
    _log_section("BOX BREAKOUTS", results.get("breakouts"))

    log.info("=" * 70)
    log.info("  ACTIONABLE CANDIDATES (R:R >= 3.0)")
    actionable = results.get("actionable")
    if actionable is not None and not actionable.empty:
        log.info("\n%s", actionable.to_string(index=False))
        if regime:
            p = regime.params
            if p.get("partial_exit_pct"):
                log.info("  Note: %s regime — partial exit at +%s%% (50%% position)",
                         regime.regime, f"{p['partial_exit_pct']*100:.0f}")
            log.info("  Time Stop: %d trading days", p["time_stop_days"])
    else:
        log.info("  None — no breakouts with R:R >= 3.0")

    # Sideways 경고 (리포트에도 표시)
    if regime and regime.regime == "SIDEWAYS":
        log.warning(
            "  Sideways regime: 이벤트 매칭 미적용 (Phase A 한계). "
            "수동 이벤트 확인 필요."
        )


# ── 헬퍼 ─────────────────────────────────────────────────


def _extract_symbol(bars: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """MultiIndex bars에서 특정 심볼의 DataFrame을 추출한다."""
    try:
        df = bars.xs(symbol, level="symbol")
        return df if not df.empty else None
    except KeyError:
        return None


def _breakout_to_dict(b: BoxBreakout) -> dict:
    return {
        "symbol": b.symbol,
        "date": b.breakout_date,
        "entry": b.breakout_price,
        "stop_loss": b.stop_loss,
        "target": b.target_price,
        "risk_r": b.risk_r,
        "reward": b.reward,
        "rr_ratio": b.rr_ratio,
        "rr_pass": b.rr_pass,
        "vol_ratio": b.breakout_vol_ratio,
        "box_top": b.box.box_top,
        "box_bottom": b.box.box_bottom,
        "box_days": b.box.duration_days,
    }


def _log_section(
    title: str,
    df: pd.DataFrame | None,
    group_by: str | None = None,
    head: int | None = None,
) -> None:
    log.info("=" * 70)
    log.info("  %s", title)
    if df is None or df.empty:
        log.info("  None")
        return

    display_df = df.head(head) if head else df

    if group_by and group_by in df.columns:
        for group_val in df[group_by].unique():
            subset = df[df[group_by] == group_val]
            log.info("\n  [%s] (%d)\n%s", group_val, len(subset), subset.to_string(index=False))
    else:
        log.info("\n%s", display_df.to_string(index=False))


if __name__ == "__main__":
    setup_logging()
    results = run_daily_screen()
    log_report(results)
