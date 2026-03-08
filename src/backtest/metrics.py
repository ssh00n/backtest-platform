"""
백테스트 성과 지표 계산

기본 지표, R-multiple 분석, Exit 분석, 국면별 분석을 산출한다.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from src.backtest.portfolio import Portfolio, TradeRecord


def compute_metrics(
    portfolio: Portfolio,
    regime_history: list[tuple[pd.Timestamp, str]] | None = None,
) -> dict:
    """모든 성과 지표를 계산하여 dict로 반환한다."""
    trades = portfolio.closed_trades
    equity_curve = portfolio.equity_curve

    metrics: dict = {}
    metrics["basic"] = _compute_basic(portfolio, equity_curve)
    metrics["r_multiple"] = _compute_r_multiple(trades)
    metrics["exit_analysis"] = _compute_exit_analysis(trades)
    metrics["regime_analysis"] = _compute_regime_analysis(trades)
    metrics["trade_count"] = len(trades)

    return metrics


# ── 기본 지표 ─────────────────────────────────────────────


def _compute_basic(
    portfolio: Portfolio,
    equity_curve: list[tuple[pd.Timestamp, float]],
) -> dict:
    if not equity_curve:
        return {}

    initial = portfolio.config.initial_capital
    final = equity_curve[-1][1]
    total_return = (final - initial) / initial

    # 연율화 수익률
    dates = [d for d, _ in equity_curve]
    n_days = (dates[-1] - dates[0]).days
    n_years = n_days / 365.25 if n_days > 0 else 1.0
    ann_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0.0

    # 일별 수익률 → Sharpe, Max Drawdown
    equities = pd.Series(
        [e for _, e in equity_curve],
        index=pd.DatetimeIndex(dates),
    )
    daily_returns = equities.pct_change().dropna()

    sharpe = 0.0
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe = float(daily_returns.mean() / daily_returns.std() * np.sqrt(252))

    # Max Drawdown
    peak = equities.cummax()
    drawdown = (equities - peak) / peak
    max_dd = float(drawdown.min())

    # Max Drawdown Duration (일)
    dd_duration = 0
    if max_dd < 0:
        is_dd = drawdown < 0
        groups = (~is_dd).cumsum()
        dd_periods = is_dd.groupby(groups).sum()
        dd_duration = int(dd_periods.max()) if not dd_periods.empty else 0

    # Win/Loss
    trades = portfolio.closed_trades
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) if trades else 0.0

    avg_win = np.mean([t.pnl for t in wins]) if wins else 0.0
    avg_loss = abs(np.mean([t.pnl for t in losses])) if losses else 0.0

    total_profit = sum(t.pnl for t in wins) if wins else 0.0
    total_loss = abs(sum(t.pnl for t in losses)) if losses else 0.0
    profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

    return {
        "initial_capital": initial,
        "final_equity": round(final, 2),
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(ann_return * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "max_drawdown_duration_days": dd_duration,
        "sharpe_ratio": round(sharpe, 2),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "profit_factor": round(profit_factor, 2),
        "total_trades": len(trades),
        "n_years": round(n_years, 1),
    }


# ── R-multiple 분석 ──────────────────────────────────────


def _compute_r_multiple(trades: list[TradeRecord]) -> dict:
    if not trades:
        return {}

    r_values = [t.pnl_r for t in trades]
    wins_r = [r for r in r_values if r > 0]
    losses_r = [r for r in r_values if r <= 0]

    avg_r = float(np.mean(r_values))
    avg_win_r = float(np.mean(wins_r)) if wins_r else 0.0
    avg_loss_r = float(np.mean(losses_r)) if losses_r else 0.0
    above_1r = sum(1 for r in r_values if r >= 1.0)
    above_1r_pct = above_1r / len(r_values) * 100

    # R 분포 (히스토그램 데이터)
    bins = [-5, -3, -2, -1, 0, 1, 2, 3, 5, 10]
    hist, _ = np.histogram(r_values, bins=bins)
    r_distribution = {
        f"{bins[i]:.0f} to {bins[i+1]:.0f}R": int(hist[i])
        for i in range(len(hist))
    }

    return {
        "avg_r": round(avg_r, 2),
        "avg_win_r": round(avg_win_r, 2),
        "avg_loss_r": round(avg_loss_r, 2),
        "above_1r_count": above_1r,
        "above_1r_pct": round(above_1r_pct, 1),
        "r_distribution": r_distribution,
    }


# ── Exit 분석 ────────────────────────────────────────────


def _compute_exit_analysis(trades: list[TradeRecord]) -> dict:
    if not trades:
        return {}

    # Exit trigger별 분류
    counter = Counter(t.exit_action for t in trades)
    total = len(trades)

    triggers = {}
    for action, count in counter.items():
        subset = [t for t in trades if t.exit_action == action]
        avg_r = float(np.mean([t.pnl_r for t in subset]))
        avg_days = float(np.mean([t.holding_days for t in subset]))
        triggers[action] = {
            "count": count,
            "pct": round(count / total * 100, 1),
            "avg_r": round(avg_r, 2),
            "avg_holding_days": round(avg_days, 1),
        }

    avg_holding = float(np.mean([t.holding_days for t in trades]))

    return {
        "by_trigger": triggers,
        "avg_holding_days": round(avg_holding, 1),
    }


# ── 국면별 분석 ──────────────────────────────────────────


def _compute_regime_analysis(trades: list[TradeRecord]) -> dict:
    if not trades:
        return {}

    regimes = {}
    for regime_name in ("BULL", "SIDEWAYS", "BEAR"):
        subset = [t for t in trades if t.regime_at_entry == regime_name]
        if not subset:
            continue
        wins = [t for t in subset if t.pnl > 0]
        r_values = [t.pnl_r for t in subset]
        regimes[regime_name] = {
            "entries": len(subset),
            "win_rate_pct": round(len(wins) / len(subset) * 100, 1),
            "avg_r": round(float(np.mean(r_values)), 2),
            "total_pnl": round(sum(t.pnl for t in subset), 2),
        }

    return regimes


# ── 리포트 포맷 ──────────────────────────────────────────


def format_report(metrics: dict) -> str:
    """성과 지표를 텍스트 리포트로 포맷한다."""
    lines = []
    lines.append("=" * 60)
    lines.append("  BACKTEST RESULTS")
    lines.append("=" * 60)

    basic = metrics.get("basic", {})
    if basic:
        lines.append("")
        lines.append("  PERFORMANCE SUMMARY")
        lines.append(f"  Period: {basic.get('n_years', 0)} years | Trades: {basic.get('total_trades', 0)}")
        lines.append(f"  Initial Capital: ${basic.get('initial_capital', 0):,.0f}")
        lines.append(f"  Final Equity:    ${basic.get('final_equity', 0):,.0f}")
        lines.append(f"  Total Return:    {basic.get('total_return_pct', 0):+.2f}%")
        lines.append(f"  Annualized:      {basic.get('annualized_return_pct', 0):+.2f}%")
        lines.append(f"  Max Drawdown:    {basic.get('max_drawdown_pct', 0):.2f}%")
        lines.append(f"  DD Duration:     {basic.get('max_drawdown_duration_days', 0)} days")
        lines.append(f"  Sharpe Ratio:    {basic.get('sharpe_ratio', 0):.2f}")
        lines.append(f"  Win Rate:        {basic.get('win_rate_pct', 0):.1f}%")
        lines.append(f"  Profit Factor:   {basic.get('profit_factor', 0):.2f}")
        lines.append(f"  Avg Win:  ${basic.get('avg_win', 0):,.2f} | Avg Loss: ${basic.get('avg_loss', 0):,.2f}")

    r = metrics.get("r_multiple", {})
    if r:
        lines.append("")
        lines.append("-" * 60)
        lines.append("  R-MULTIPLE ANALYSIS")
        lines.append(f"  Average R:     {r.get('avg_r', 0):+.2f}")
        lines.append(f"  Avg Win R:     {r.get('avg_win_r', 0):+.2f}")
        lines.append(f"  Avg Loss R:    {r.get('avg_loss_r', 0):+.2f}")
        lines.append(f"  >= 1R trades:  {r.get('above_1r_count', 0)} ({r.get('above_1r_pct', 0):.1f}%)")

        dist = r.get("r_distribution", {})
        if dist:
            lines.append("  R Distribution:")
            for bucket, count in dist.items():
                bar = "#" * count
                lines.append(f"    {bucket:>12s}: {count:3d} {bar}")

    exit_a = metrics.get("exit_analysis", {})
    if exit_a:
        lines.append("")
        lines.append("-" * 60)
        lines.append("  EXIT ANALYSIS")
        lines.append(f"  Avg Holding: {exit_a.get('avg_holding_days', 0):.1f} days")
        for trigger, info in exit_a.get("by_trigger", {}).items():
            lines.append(
                f"    {trigger:<16s}: {info['count']:3d} ({info['pct']:5.1f}%) | "
                f"avg R={info['avg_r']:+.2f} | avg {info['avg_holding_days']:.0f}d"
            )

    regime_a = metrics.get("regime_analysis", {})
    if regime_a:
        lines.append("")
        lines.append("-" * 60)
        lines.append("  REGIME ANALYSIS")
        for regime_name, info in regime_a.items():
            lines.append(
                f"    {regime_name:<10s}: {info['entries']:3d} entries | "
                f"WR={info['win_rate_pct']:.1f}% | "
                f"avg R={info['avg_r']:+.2f} | "
                f"PnL=${info['total_pnl']:,.0f}"
            )

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
