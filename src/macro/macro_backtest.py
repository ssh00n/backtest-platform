"""
매크로 필터 — 백테스트 전용 (사전 로드 데이터 사용)

yfinance HTTP 호출 없이, Alpaca에서 이미 로드된 SPY 데이터 +
VIX를 한 번만 로드하여 전체 기간 매크로 리스크 캘린더를 생성한다.

Usage:
    from src.macro.macro_backtest import build_macro_calendar_from_data
    calendar = build_macro_calendar_from_data(spy_df, start, end)
    # calendar[date] = MacroRiskLevel
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd

from src.macro.macro_detector import MacroRiskLevel

log = logging.getLogger(__name__)


def _load_vix_from_alpaca(start: datetime, end: datetime) -> pd.Series:
    """Alpaca에서 VIX 프록시 (VIXY ETF) 또는 yfinance에서 ^VIX를 한 번만 로드."""
    # 먼저 yfinance로 ^VIX 한 번만 로드 (캐시됨)
    try:
        import yfinance as yf
        vix = yf.download(
            "^VIX",
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=5)).strftime("%Y-%m-%d"),
            progress=False,
        )
        if not vix.empty:
            if isinstance(vix.columns, pd.MultiIndex):
                close = vix["Close"].iloc[:, 0] if "Close" in vix.columns.get_level_values(0) else vix.iloc[:, 0]
            else:
                close = vix["Close"]
            log.info("VIX 데이터 로드 완료: %d일", len(close))
            return close
    except ImportError:
        log.warning("yfinance 미설치 — VIX 데이터 없이 SPY만으로 매크로 필터 실행")
    except Exception as e:
        log.warning("VIX 로드 실패: %s", e)

    return pd.Series(dtype=float)


def detect_stress_from_data(
    date: pd.Timestamp,
    spy_series: pd.Series,
    vix_series: pd.Series,
    # EXTREME
    vix_extreme: float = 30.0,
    vix_spike_days: int = 2,
    vix_spike_pct: float = 0.50,
    spy_extreme_consec: int = 5,
    spy_extreme_daily: float = -0.01,
    # HIGH
    vix_high: float = 25.0,
    spy_high_consec: int = 3,
    spy_weekly_drop: float = -0.05,
    # MEDIUM
    vix_medium: float = 20.0,
    spy_medium_consec: int = 3,
    spy_medium_daily: float = -0.005,
) -> tuple[MacroRiskLevel, list[str]]:
    """
    사전 로드된 SPY/VIX 시리즈에서 특정 날짜의 스트레스 감지.
    yfinance 호출 없음.
    """
    risk = MacroRiskLevel.LOW
    reasons = []

    # tz-aware / naive 호환: date를 tz-naive로 통일
    date_naive = date.tz_localize(None) if date.tzinfo else date

    # VIX 평가
    if not vix_series.empty:
        vix_idx = vix_series.index.tz_localize(None) if vix_series.index.tz else vix_series.index
        _vix = vix_series.copy()
        _vix.index = vix_idx
        vix_up_to = _vix[_vix.index <= date_naive]
        if len(vix_up_to) > 0:
            vix_val = float(vix_up_to.iloc[-1])

            if vix_val >= vix_extreme:
                risk = MacroRiskLevel.EXTREME
                reasons.append(f"VIX {vix_val:.1f} ≥ {vix_extreme}")

            if len(vix_up_to) >= vix_spike_days + 1:
                prev_vix = float(vix_up_to.iloc[-(vix_spike_days + 1)])
                if prev_vix > 0:
                    spike = (vix_val - prev_vix) / prev_vix
                    if spike >= vix_spike_pct and risk != MacroRiskLevel.EXTREME:
                        risk = MacroRiskLevel.EXTREME
                        reasons.append(f"VIX spike {spike:.0%} in {vix_spike_days}d")

            if vix_val >= vix_high and risk == MacroRiskLevel.LOW:
                risk = MacroRiskLevel.HIGH
                reasons.append(f"VIX {vix_val:.1f} ≥ {vix_high}")

            if vix_val >= vix_medium and risk == MacroRiskLevel.LOW:
                risk = MacroRiskLevel.MEDIUM
                reasons.append(f"VIX {vix_val:.1f} ≥ {vix_medium}")

    # SPY 평가
    spy_idx = spy_series.index.tz_localize(None) if spy_series.index.tz else spy_series.index
    _spy = spy_series.copy()
    _spy.index = spy_idx
    spy_up_to = _spy[_spy.index <= date_naive]
    if len(spy_up_to) >= 5:
        spy_5d_ret = (spy_up_to.iloc[-1] / spy_up_to.iloc[-5]) - 1

        # EXTREME: 5일 연속 -1%
        if len(spy_up_to) >= spy_extreme_consec:
            daily_rets = spy_up_to.pct_change().iloc[-spy_extreme_consec:]
            if all(r <= spy_extreme_daily for r in daily_rets.dropna()):
                if risk.value < MacroRiskLevel.EXTREME.value or risk == MacroRiskLevel.LOW:
                    risk = MacroRiskLevel.EXTREME
                    reasons.append(f"SPY {spy_extreme_consec}d consecutive ≤{spy_extreme_daily:.1%}")

        # HIGH: 주간 -5%
        if spy_5d_ret <= spy_weekly_drop:
            if risk == MacroRiskLevel.LOW:
                risk = MacroRiskLevel.HIGH
                reasons.append(f"SPY 5d return {spy_5d_ret:.1%} ≤ {spy_weekly_drop:.0%}")

        # HIGH: 3일 연속 -1%
        if len(spy_up_to) >= spy_high_consec:
            daily_rets = spy_up_to.pct_change().iloc[-spy_high_consec:]
            if all(r <= -0.01 for r in daily_rets.dropna()):
                if risk == MacroRiskLevel.LOW:
                    risk = MacroRiskLevel.HIGH
                    reasons.append(f"SPY {spy_high_consec}d consecutive ≤-1%")

        # MEDIUM: 3일 연속 -0.5%
        if len(spy_up_to) >= spy_medium_consec:
            daily_rets = spy_up_to.pct_change().iloc[-spy_medium_consec:]
            if all(r <= spy_medium_daily for r in daily_rets.dropna()):
                if risk == MacroRiskLevel.LOW:
                    risk = MacroRiskLevel.MEDIUM
                    reasons.append(f"SPY {spy_medium_consec}d consecutive ≤{spy_medium_daily:.1%}")

    return risk, reasons


def build_macro_calendar_from_data(
    spy_df: pd.DataFrame,
    start: str | datetime,
    end: str | datetime,
) -> dict[str, MacroRiskLevel]:
    """
    백테스트 시작 전 전체 기간의 매크로 캘린더를 미리 생성.

    Args:
        spy_df: SPY 가격 DataFrame (index=datetime, 'close' column)
        start: 시작일
        end: 종료일

    Returns:
        dict[YYYY-MM-DD str, MacroRiskLevel]
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    # SPY close 시리즈 추출
    if "close" in spy_df.columns:
        spy_series = spy_df["close"]
    elif "Close" in spy_df.columns:
        spy_series = spy_df["Close"]
    else:
        spy_series = spy_df.iloc[:, 0]

    # VIX 한 번만 로드
    vix_series = _load_vix_from_alpaca(
        start_dt.to_pydatetime() - timedelta(days=30),
        end_dt.to_pydatetime(),
    )

    # 전 영업일 스캔
    dates = pd.date_range(start=start_dt, end=end_dt, freq="B")
    calendar = {}
    high_count = 0

    for date in dates:
        risk, reasons = detect_stress_from_data(date, spy_series, vix_series)
        calendar[date.strftime("%Y-%m-%d")] = risk
        if risk in (MacroRiskLevel.HIGH, MacroRiskLevel.EXTREME):
            high_count += 1

    log.info(
        "매크로 캘린더 생성 완료: %d 영업일, HIGH/EXTREME %d일 (%.1f%%)",
        len(dates), high_count, high_count / len(dates) * 100 if dates.size else 0,
    )
    return calendar
