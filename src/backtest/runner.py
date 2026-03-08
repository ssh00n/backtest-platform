"""
백테스트 CLI 진입점

Usage:
    python -m src.backtest.runner --start 2023-01-01 --end 2025-12-31
    python -m src.backtest.runner --start 2024-01-01 --capital 200000 --max-positions 3
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.backtest.engine import run_backtest
from src.backtest.metrics import compute_metrics, format_report
from src.backtest.portfolio import BacktestConfig
from src.data.client import fetch_daily_bars
from src.data.universe import get_sp500_symbols
from src.utils.logger import get_logger, setup_logging

log = get_logger(__name__)

# Alpaca API에서 실패하는 심볼
_EXCLUDE_SYMBOLS = {"BRK/B", "BF/B"}

# 결과 저장 디렉토리
_RESULTS_DIR = Path(__file__).parent.parent.parent / "data" / "backtest_results"


def main() -> None:
    setup_logging()

    args = _parse_args()

    config = BacktestConfig(
        initial_capital=args.capital,
        max_positions=args.max_positions,
        position_size_pct=args.position_size_pct,
        trailing_stop_r=args.trailing_stop_r,
        confirm_breakout=args.confirm_breakout,
        min_rr_override=args.min_rr if args.min_rr else None,
        min_vol_ratio_override=args.min_vol_ratio if args.min_vol_ratio else None,
        use_events=args.use_events,
        use_macro_filter=args.macro_filter,
        macro_high_action=args.macro_high_action,
    )

    # ── 데이터 로드 ───────────────────────────────────
    log.info("Loading data...")

    symbols = [s for s in get_sp500_symbols() if s not in _EXCLUDE_SYMBOLS]
    all_symbols = list(set(symbols + ["SPY"]))

    # 시작일 이전 220거래일 (약 1년) 여유를 두고 데이터 수집
    lookback = timedelta(days=400)
    start_dt = datetime.strptime(args.start, "%Y-%m-%d") - lookback
    end_dt = datetime.strptime(args.end, "%Y-%m-%d") if args.end else None

    bars = fetch_daily_bars(all_symbols, start=start_dt, end=end_dt)
    if bars.empty:
        log.error("No data loaded. Check Alpaca API credentials and date range.")
        return

    log.info("Data loaded: %s rows, %d symbols",
             f"{bars.shape[0]:,}",
             bars.index.get_level_values("symbol").nunique())

    # SPY 추출
    try:
        spy_df = bars.xs("SPY", level="symbol").sort_index()
    except KeyError:
        log.error("SPY data not found")
        return

    # ── 백테스트 실행 ─────────────────────────────────
    log.info("Running backtest...")

    bear_overrides = None
    if args.bear_exit:
        bear_overrides = {int(k): True for k in args.bear_exit.split(",")}

    result = run_backtest(
        bars=bars,
        spy_df=spy_df,
        config=config,
        start_date=args.start,
        end_date=args.end,
        bear_exit_overrides=bear_overrides,
    )

    # ── 성과 지표 ─────────────────────────────────────
    metrics = compute_metrics(result.portfolio, result.regime_history)
    result.metrics = metrics

    # ── 리포트 출력 ───────────────────────────────────
    report = format_report(metrics)
    print(report)

    # ── 결과 저장 ─────────────────────────────────────
    if args.save:
        _save_results(result, metrics, args)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trading System Backtest Engine",
    )
    parser.add_argument(
        "--start", required=True,
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", default=None,
        help="Backtest end date (YYYY-MM-DD). Default: latest data",
    )
    parser.add_argument(
        "--capital", type=float, default=100_000.0,
        help="Initial capital (default: 100000)",
    )
    parser.add_argument(
        "--max-positions", type=int, default=5,
        help="Max concurrent positions (default: 5)",
    )
    parser.add_argument(
        "--position-size-pct", type=float, default=0.20,
        help="Position size as fraction of capital (default: 0.20)",
    )
    parser.add_argument(
        "--bear-exit", default=None,
        help="Bear exit condition overrides, comma-separated (e.g., '1,2')",
    )
    parser.add_argument(
        "--save", action="store_true", default=True,
        help="Save results to JSON (default: True)",
    )
    parser.add_argument(
        "--no-save", dest="save", action="store_false",
        help="Do not save results",
    )
    # ── 개선 파라미터 (v1) ──
    parser.add_argument(
        "--trailing-stop-r", type=float, default=1.0,
        help="Trailing stop R multiplier (default: 1.0 = -1R from high)",
    )
    parser.add_argument(
        "--confirm-breakout", action="store_true", default=False,
        help="Require breakout confirmation (next day close above box top)",
    )
    parser.add_argument(
        "--min-rr", type=float, default=None,
        help="Minimum R:R ratio for entry (default: 3.0)",
    )
    parser.add_argument(
        "--min-vol-ratio", type=float, default=None,
        help="Minimum volume ratio override for entry",
    )
    parser.add_argument(
        "--use-events", action="store_true", default=False,
        help="Enable event-based signal filtering (news + SEC)",
    )
    parser.add_argument(
        "--macro-filter", action="store_true", default=False,
        help="Enable macro risk filter (VIX/SPY based)",
    )
    parser.add_argument(
        "--macro-high-action", type=str, default="block",
        choices=["block", "reduce"],
        help="Action on HIGH macro risk: block or reduce position",
    )
    return parser.parse_args()


def _save_results(result, metrics: dict, args: argparse.Namespace) -> None:
    """결과를 JSON으로 저장한다."""
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backtest_{args.start}_{args.end or 'latest'}_{timestamp}.json"
    filepath = _RESULTS_DIR / filename

    # 거래 기록을 직렬화
    trades = []
    for t in result.portfolio.closed_trades:
        trades.append({
            "symbol": t.symbol,
            "entry_date": t.entry_date.isoformat() if t.entry_date else None,
            "entry_price": round(t.entry_price, 2),
            "exit_date": t.exit_date.isoformat() if t.exit_date else None,
            "exit_price": round(t.exit_price, 2) if t.exit_price else None,
            "exit_action": t.exit_action,
            "shares": round(t.shares, 2),
            "pnl": round(t.pnl, 2),
            "pnl_pct": round(t.pnl_pct * 100, 2),
            "pnl_r": round(t.pnl_r, 2),
            "regime_at_entry": t.regime_at_entry,
            "holding_days": t.holding_days,
            "partial": t.partial,
        })

    # Equity curve
    equity = [
        {"date": d.isoformat(), "equity": round(e, 2)}
        for d, e in result.portfolio.equity_curve
    ]

    # Regime history
    regimes = [
        {"date": d.isoformat(), "regime": r}
        for d, r in result.regime_history
    ]

    output = {
        "config": {
            "initial_capital": result.config.initial_capital,
            "max_positions": result.config.max_positions,
            "position_size_pct": result.config.position_size_pct,
            "slippage_pct": result.config.slippage_pct,
            "trailing_stop_r": result.config.trailing_stop_r,
            "confirm_breakout": result.config.confirm_breakout,
            "min_rr_override": result.config.min_rr_override,
            "min_vol_ratio_override": result.config.min_vol_ratio_override,
            "start_date": args.start,
            "end_date": args.end,
        },
        "metrics": metrics,
        "trades": trades,
        "equity_curve": equity,
        "regime_history": regimes,
    }

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)

    log.info("Results saved: %s", filepath)


if __name__ == "__main__":
    main()
