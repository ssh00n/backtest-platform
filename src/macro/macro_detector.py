"""
매크로 스트레스 자동 감지 (API 키 불필요)

VIX + SPY 가격 데이터만으로 시장 스트레스 구간을 감지한다.
데이터: yfinance (무료, 키 불필요)

감지 규칙:
    HIGH   - VIX ≥ 30 OR SPY 5일 연속 -0.5% 이상 하락
    MEDIUM - VIX ≥ 20 OR SPY 3일 연속 하락 OR SPY 주간 -5% 이하
    LOW    - 정상
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)


class MacroRiskLevel(str, Enum):
    EXTREME = "EXTREME"  # Level 3: 모든 신규 진입 차단 (VIX 급등 속도 등)
    HIGH    = "HIGH"     # Level 2: 신규 진입 50% 축소 + R:R 상향
    MEDIUM  = "MEDIUM"   # Level 1: R:R 기준 상향 (4.5→5.5)
    LOW     = "LOW"      # Level 0: 정상 운용


class MacroEventType(str, Enum):
    TARIFF_SHOCK  = "TARIFF_SHOCK"   # 관세/무역 정책
    FED_DECISION  = "FED_DECISION"   # FOMC
    MARKET_STRESS = "MARKET_STRESS"  # VIX/SPY 기술적 스트레스
    MACRO_DATA    = "MACRO_DATA"     # 경제지표 서프라이즈
    GEOPOLITICAL  = "GEOPOLITICAL"   # 지정학적


@dataclass
class MacroEvent:
    """단일 매크로 이벤트."""
    event_date: pd.Timestamp
    event_type: MacroEventType
    risk_level: MacroRiskLevel
    description: str
    source: str = "AUTO"
    vix_level: Optional[float] = None
    spy_5d_return: Optional[float] = None
    duration_days: int = 5           # 이벤트 효력 지속 일수


@dataclass
class MarketStressResult:
    """시장 스트레스 감지 결과."""
    date: pd.Timestamp
    risk_level: MacroRiskLevel
    vix: Optional[float]
    spy_5d_return: Optional[float]
    spy_3d_consecutive_down: bool
    triggered_by: list[str] = field(default_factory=list)

    @property
    def is_high_risk(self) -> bool:
        return self.risk_level == MacroRiskLevel.HIGH

    @property
    def is_restricted(self) -> bool:
        return self.risk_level in (MacroRiskLevel.HIGH, MacroRiskLevel.MEDIUM)


def _fetch_price_data(
    symbol: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """yfinance로 가격 데이터 가져오기 (무료, 키 불필요)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))
        return df[["Close"]].rename(columns={"Close": symbol})
    except ImportError:
        log.warning("yfinance 미설치. 'uv add yfinance'로 설치하세요.")
        return pd.DataFrame()
    except Exception as e:
        log.debug("가격 데이터 조회 실패 [%s]: %s", symbol, e)
        return pd.DataFrame()


def detect_market_stress_from_cache(
    date: pd.Timestamp,
    spy_cache: pd.DataFrame,
    vix_cache: pd.DataFrame,
    vix_extreme_threshold: float = 30.0,
    vix_spike_days: int = 2,
    vix_spike_pct: float = 0.50,
    spy_extreme_consecutive: int = 5,
    spy_extreme_daily: float = -0.01,
    vix_high_threshold: float = 25.0,
    spy_high_consecutive: int = 3,
    spy_weekly_drop: float = -0.05,
    vix_medium_threshold: float = 20.0,
    spy_consecutive_days: int = 3,
    spy_daily_drop: float = -0.005,
) -> MarketStressResult:
    """
    사전 로드된 SPY/VIX DataFrame에서 특정 날짜의 스트레스 계산.

    백테스트용 — API 호출 없이 메모리에서 조회 (고속).

    Args:
        date: 조회 날짜
        spy_cache: 전체 기간 SPY 데이터 (index=datetime, columns=['SPY' 또는 'close'])
        vix_cache: 전체 기간 VIX 데이터 (index=datetime, columns=['^VIX' 또는 'close'])
    """
    vix_level = None
    spy_5d_return = None
    spy_3d_down = False
    triggered_by = []
    risk_level = MacroRiskLevel.LOW

    # tz-aware 비교를 위한 날짜 정규화
    date_naive = _ts_to_naive(date)

    # VIX 슬라이스 (해당 날짜까지 최근 10일)
    if not vix_cache.empty:
        col = "^VIX" if "^VIX" in vix_cache.columns else vix_cache.columns[0]
        idx = _to_naive(vix_cache.index)
        recent_vix = vix_cache[idx <= date_naive][col].tail(10)

        if not recent_vix.empty:
            vix_level = float(recent_vix.iloc[-1])

            if vix_level >= vix_extreme_threshold:
                risk_level = MacroRiskLevel.EXTREME
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_extreme_threshold} (EXTREME)")

            if len(recent_vix) >= vix_spike_days + 1:
                prev_vix = float(recent_vix.iloc[-(vix_spike_days + 1)])
                if prev_vix > 0 and (vix_level - prev_vix) / prev_vix >= vix_spike_pct:
                    if risk_level != MacroRiskLevel.EXTREME:
                        risk_level = MacroRiskLevel.EXTREME
                    triggered_by.append(f"VIX 급등 {(vix_level-prev_vix)/prev_vix:.0%} ({prev_vix:.1f}→{vix_level:.1f})")

            if vix_level >= vix_high_threshold and risk_level == MacroRiskLevel.LOW:
                risk_level = MacroRiskLevel.HIGH
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_high_threshold}")
            elif vix_level >= vix_medium_threshold and risk_level == MacroRiskLevel.LOW:
                risk_level = MacroRiskLevel.MEDIUM
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_medium_threshold}")

    # SPY 슬라이스
    if not spy_cache.empty:
        col = "SPY" if "SPY" in spy_cache.columns else spy_cache.columns[0]
        idx = _to_naive(spy_cache.index)
        recent_spy = spy_cache[idx <= date_naive][col].tail(10)

        if len(recent_spy) >= 5:
            spy_5d_return = float((recent_spy.iloc[-1] / recent_spy.iloc[-5]) - 1)
            if spy_5d_return <= spy_weekly_drop:
                if risk_level in (MacroRiskLevel.LOW, MacroRiskLevel.MEDIUM):
                    risk_level = MacroRiskLevel.HIGH
                triggered_by.append(f"SPY 5d {spy_5d_return:.1%} ≤ {spy_weekly_drop:.1%}")

        if len(recent_spy) >= 3:
            daily_ret = recent_spy.pct_change().dropna()
            if len(daily_ret) >= spy_extreme_consecutive:
                if all(r <= spy_extreme_daily for r in daily_ret.tail(spy_extreme_consecutive)):
                    risk_level = MacroRiskLevel.EXTREME
                    spy_3d_down = True
                    triggered_by.append(f"SPY {spy_extreme_consecutive}일 연속 {spy_extreme_daily:.1%}")
            elif len(daily_ret) >= spy_high_consecutive:
                if all(r <= spy_extreme_daily for r in daily_ret.tail(spy_high_consecutive)):
                    if risk_level == MacroRiskLevel.LOW:
                        risk_level = MacroRiskLevel.HIGH
                    spy_3d_down = True
                    triggered_by.append(f"SPY {spy_high_consecutive}일 연속 {spy_extreme_daily:.1%}")
            elif len(daily_ret) >= spy_consecutive_days:
                if all(r <= spy_daily_drop for r in daily_ret.tail(spy_consecutive_days)):
                    spy_3d_down = True
                    if risk_level == MacroRiskLevel.LOW:
                        risk_level = MacroRiskLevel.MEDIUM
                    triggered_by.append(f"SPY {spy_consecutive_days}일 연속 {spy_daily_drop:.1%}")

    return MarketStressResult(
        date=date,
        risk_level=risk_level,
        vix=vix_level,
        spy_5d_return=spy_5d_return,
        spy_3d_consecutive_down=spy_3d_down,
        triggered_by=triggered_by,
    )


def detect_market_stress(
    date: pd.Timestamp,
    lookback_days: int = 10,
    # Level 3 (EXTREME) 트리거
    vix_extreme_threshold: float = 30.0,    # VIX ≥ 30
    vix_spike_days: int = 2,                # N일 내 VIX 50%+ 급등
    vix_spike_pct: float = 0.50,            # VIX 급등 기준 (50%)
    spy_extreme_consecutive: int = 5,       # SPY N일 연속 -1% → EXTREME
    spy_extreme_daily: float = -0.01,       # 연속 하락 기준 (-1%/일)
    # Level 2 (HIGH) 트리거
    vix_high_threshold: float = 25.0,       # VIX ≥ 25
    spy_high_consecutive: int = 3,          # SPY 3일 연속 -1%
    spy_weekly_drop: float = -0.05,         # SPY 주간 -5%
    # Level 1 (MEDIUM) 트리거
    vix_medium_threshold: float = 20.0,     # VIX ≥ 20
    spy_consecutive_days: int = 3,          # SPY 3일 연속 하락 (-0.5%)
    spy_daily_drop: float = -0.005,
) -> MarketStressResult:
    """
    특정 날짜의 시장 스트레스 수준을 감지한다.

    Args:
        date: 감지 날짜
        lookback_days: 조회 기간 (영업일)
        vix_high_threshold: HIGH 리스크 VIX 기준 (기본 30)
        vix_medium_threshold: MEDIUM 리스크 VIX 기준 (기본 20)
        spy_weekly_drop: 주간 낙폭 MEDIUM 기준 (기본 -5%)
        spy_consecutive_days: 연속 하락 일수 기준 (기본 3)
        spy_daily_drop: 연속 하락 기준 일별 수익률 (기본 -0.5%)

    Returns:
        MarketStressResult
    """
    start = date.to_pydatetime() - timedelta(days=lookback_days + 5)
    end = date.to_pydatetime() + timedelta(days=1)

    # VIX 데이터
    vix_df = _fetch_price_data("^VIX", start, end)
    # SPY 데이터
    spy_df = _fetch_price_data("SPY", start, end)

    vix_level = None
    spy_5d_return = None
    spy_3d_down = False
    triggered_by = []
    risk_level = MacroRiskLevel.LOW

    # ── VIX 평가 ──────────────────────────────────────────
    if not vix_df.empty:
        recent_vix = vix_df[vix_df.index.date <= date.date()].tail(10)
        if not recent_vix.empty:
            vix_level = float(recent_vix["^VIX"].iloc[-1])

            # Level 3 (EXTREME): VIX ≥ 30
            if vix_level >= vix_extreme_threshold:
                risk_level = MacroRiskLevel.EXTREME
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_extreme_threshold} (EXTREME)")

            # Level 3 (EXTREME): VIX 급등 속도 — N일 내 50%+ 급등
            if len(recent_vix) >= vix_spike_days + 1:
                prev_vix = float(recent_vix["^VIX"].iloc[-(vix_spike_days + 1)])
                if prev_vix > 0:
                    vix_change = (vix_level - prev_vix) / prev_vix
                    if vix_change >= vix_spike_pct and risk_level != MacroRiskLevel.EXTREME:
                        risk_level = MacroRiskLevel.EXTREME
                        triggered_by.append(
                            f"VIX 급등 {vix_change:.0%} ({prev_vix:.1f}→{vix_level:.1f}, {vix_spike_days}일)"
                        )

            # Level 2 (HIGH): VIX ≥ 25
            if vix_level >= vix_high_threshold and risk_level == MacroRiskLevel.LOW:
                risk_level = MacroRiskLevel.HIGH
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_high_threshold}")

            # Level 1 (MEDIUM): VIX ≥ 20
            elif vix_level >= vix_medium_threshold and risk_level == MacroRiskLevel.LOW:
                risk_level = MacroRiskLevel.MEDIUM
                triggered_by.append(f"VIX {vix_level:.1f} ≥ {vix_medium_threshold}")

    # ── SPY 평가 ──────────────────────────────────────────
    if not spy_df.empty:
        recent_spy = spy_df[spy_df.index.date <= date.date()].tail(10)

        if len(recent_spy) >= 5:
            spy_5d_return = float(
                (recent_spy["SPY"].iloc[-1] / recent_spy["SPY"].iloc[-5]) - 1
            )
            # Level 2 (HIGH): 주간 -5%
            if spy_5d_return <= spy_weekly_drop:
                if risk_level in (MacroRiskLevel.LOW, MacroRiskLevel.MEDIUM):
                    risk_level = MacroRiskLevel.HIGH
                triggered_by.append(f"SPY 5d return {spy_5d_return:.1%} ≤ {spy_weekly_drop:.1%}")

        if len(recent_spy) >= 3:
            daily_returns = recent_spy["SPY"].pct_change().dropna()

            # Level 3 (EXTREME): 5일 연속 -1% 이상
            if len(daily_returns) >= spy_extreme_consecutive:
                last_5 = daily_returns.tail(spy_extreme_consecutive)
                if all(r <= spy_extreme_daily for r in last_5):
                    risk_level = MacroRiskLevel.EXTREME
                    spy_3d_down = True
                    triggered_by.append(
                        f"SPY {spy_extreme_consecutive}일 연속 {spy_extreme_daily:.1%} 이하"
                    )

            # Level 2 (HIGH): 3일 연속 -1% 이상
            elif len(daily_returns) >= spy_high_consecutive:
                last_3 = daily_returns.tail(spy_high_consecutive)
                if all(r <= spy_extreme_daily for r in last_3):
                    if risk_level == MacroRiskLevel.LOW:
                        risk_level = MacroRiskLevel.HIGH
                    spy_3d_down = True
                    triggered_by.append(
                        f"SPY {spy_high_consecutive}일 연속 {spy_extreme_daily:.1%} 이하"
                    )

            # Level 1 (MEDIUM): 3일 연속 -0.5% 이상
            elif len(daily_returns) >= spy_consecutive_days:
                last_n = daily_returns.tail(spy_consecutive_days)
                if all(r <= spy_daily_drop for r in last_n):
                    spy_3d_down = True
                    triggered_by.append(f"SPY {spy_consecutive_days}일 연속 하락 ({spy_daily_drop:.1%}/일)")
                    if risk_level == MacroRiskLevel.LOW:
                        risk_level = MacroRiskLevel.MEDIUM

    return MarketStressResult(
        date=date,
        risk_level=risk_level,
        vix=vix_level,
        spy_5d_return=spy_5d_return,
        spy_3d_consecutive_down=spy_3d_down,
        triggered_by=triggered_by,
    )


def build_stress_calendar(
    start: pd.Timestamp,
    end: pd.Timestamp,
    freq: str = "W",  # 주별 체크 (일별로 하면 API 느림)
) -> list[MarketStressResult]:
    """
    기간 전체의 시장 스트레스 캘린더를 생성한다.

    백테스트에서 "어느 날이 고위험 구간이었나"를 미리 캐시한다.
    """
    dates = pd.date_range(start=start, end=end, freq=freq)
    results = []

    for date in dates:
        result = detect_market_stress(date)
        if result.risk_level != MacroRiskLevel.LOW:
            results.append(result)
            log.info(
                "[매크로 스트레스] %s → %s | %s",
                date.strftime("%Y-%m-%d"),
                result.risk_level,
                ", ".join(result.triggered_by),
            )

    return results


def _to_naive(idx: "pd.DatetimeIndex") -> "pd.DatetimeIndex":
    """DatetimeIndex를 tz-naive 날짜(00:00)로 통일.
    Alpaca(America/New_York), yfinance(UTC or naive) 모두 처리."""
    if idx.tz is not None:
        # tz-aware → UTC 변환 → tz 제거 → 날짜만 남김(normalize)
        return idx.tz_localize(None).normalize()
    return idx.normalize()

def _ts_to_naive(ts: "pd.Timestamp") -> "pd.Timestamp":
    """Timestamp를 tz-naive 날짜(00:00)로 통일."""
    if ts.tzinfo is not None:
        return ts.tz_localize(None).normalize()
    return ts.normalize()
