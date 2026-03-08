"""
매크로 심층 시그널 — 크레딧 스프레드 + 수익률 곡선

선택 기준: 노이즈 대비 신호 비율이 높은 지표만.
  - 복잡한 뉴스 파싱 X (노이즈 많음)
  - 단순하지만 검증된 선행 지표 2개만

시그널 1: 크레딧 스프레드 (HY OAS)
  출처: FRED BAMLH0A0HYM2 (ICE BofA US High Yield OAS)
  의미: 하이일드 채권과 국채 간 스프레드 → 기업 부도 리스크 시장 평가
  임계값: 4% 이하 = 정상, 5%+ = 주의, 7%+ = 위험, 10%+ = 위기 (2020 코로나: 11%)

시그널 2: 수익률 곡선 (2Y-10Y 스프레드)
  출처: FRED DGS2, DGS10
  의미: 역전(음수) = 6~18개월 후 경기침체 선행 신호
  임계값: +0.5% 이상 = 정상, 0~0.5% = 평탄, 역전(-) = 주의, -0.5% 이하 = 경고

L4 매크로 레이어 통합:
  VIX/SPY (기존) + 크레딧 스프레드 + 수익률 곡선
  → 복합 위험 점수로 진입 차단 여부 결정
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum

import pandas as pd
import requests

log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"


class SignalLevel(IntEnum):
    NORMAL   = 0
    ELEVATED = 1   # 주의 (진입 허용, 리스크 인식)
    HIGH     = 2   # 경고 (포지션 축소 고려)
    EXTREME  = 3   # 위험 (진입 차단)


@dataclass
class CreditSpreadSignal:
    """하이일드 크레딧 스프레드 시그널."""
    date: pd.Timestamp
    hy_oas: float          # HY OAS (%)
    level: SignalLevel
    reason: str


@dataclass
class YieldCurveSignal:
    """수익률 곡선 시그널."""
    date: pd.Timestamp
    spread_2y10y: float    # 10Y - 2Y (%)
    level: SignalLevel
    reason: str


@dataclass
class MacroSignalSummary:
    """복합 매크로 시그널 요약."""
    date: pd.Timestamp
    credit: CreditSpreadSignal | None
    yield_curve: YieldCurveSignal | None
    combined_level: SignalLevel     # 두 시그널 중 더 심각한 쪽
    block_entry: bool               # True = 진입 차단
    reasons: list[str]


# ── 크레딧 스프레드 ──────────────────────────────────────────────────────────

# HY OAS 임계값 (%) — 2020-2025 역사적 데이터 기반 조정
# 75th: 4.49%, 90th: 5.17%, 95th: 6.03%, 2020 코로나: 10.87%
# 2025 관세 충격 최고 4.61% → ELEVATED 수준으로 인식
_HY_THRESHOLDS = [
    ( 8.5, SignalLevel.EXTREME,  "HY OAS {v:.1f}% (위기, 2008 수준)"),
    ( 6.0, SignalLevel.HIGH,     "HY OAS {v:.1f}% (위험, 95th 백분위, 진입 차단)"),
    ( 4.5, SignalLevel.ELEVATED, "HY OAS {v:.1f}% (주의, 75th 백분위, 리스크 인식)"),
    ( 0.0, SignalLevel.NORMAL,   "HY OAS {v:.1f}% (정상)"),
]


def _fetch_fred_series_latest(
    series_id: str,
    lookback_days: int = 30,
    api_key: str | None = None,
) -> pd.Series:
    """FRED에서 최근 N일 데이터 조회."""
    key = api_key or os.getenv("FRED_API_KEY", "")
    if not key:
        return pd.Series(dtype=float, name=series_id)

    start = (datetime.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    try:
        resp = requests.get(
            f"{FRED_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": start,
                "sort_order": "desc",
            },
            timeout=10,
        )
        if not resp.ok:
            return pd.Series(dtype=float, name=series_id)

        obs = [
            (pd.Timestamp(o["date"]), float(o["value"]))
            for o in resp.json().get("observations", [])
            if o["value"] != "."
        ]
        if not obs:
            return pd.Series(dtype=float, name=series_id)
        dates, vals = zip(*obs)
        return pd.Series(dict(zip(dates, vals)), name=series_id).sort_index()

    except Exception as e:
        log.debug("FRED 조회 실패 [%s]: %s", series_id, e)
        return pd.Series(dtype=float, name=series_id)


def get_credit_spread_signal(
    date: pd.Timestamp | None = None,
    api_key: str | None = None,
) -> CreditSpreadSignal | None:
    """
    하이일드 크레딧 스프레드 시그널 조회.

    Args:
        date: 기준 날짜 (None이면 최신)
        api_key: FRED API key

    Returns:
        CreditSpreadSignal | None (API 실패 시)
    """
    series = _fetch_fred_series_latest("BAMLH0A0HYM2", lookback_days=30, api_key=api_key)
    if series.empty:
        return None

    # 기준 날짜 이전 가장 최근 값
    if date is not None:
        series = series[series.index <= date]
    if series.empty:
        return None

    latest_date = series.index[-1]
    oas = series.iloc[-1]

    for threshold, level, msg_tmpl in _HY_THRESHOLDS:
        if oas >= threshold:
            return CreditSpreadSignal(
                date=latest_date,
                hy_oas=oas,
                level=level,
                reason=msg_tmpl.format(v=oas),
            )

    return CreditSpreadSignal(
        date=latest_date, hy_oas=oas,
        level=SignalLevel.NORMAL, reason=f"HY OAS {oas:.1f}% (정상)"
    )


# ── 수익률 곡선 ──────────────────────────────────────────────────────────────

# 2Y-10Y 스프레드 임계값 (10Y - 2Y, %)
_YC_THRESHOLDS = [
    (-0.75, SignalLevel.EXTREME,  "수익률 곡선 역전 {v:+.2f}% (심각한 역전, 경기침체 강한 신호)"),
    (-0.25, SignalLevel.HIGH,     "수익률 곡선 역전 {v:+.2f}% (역전, 경기침체 선행)"),
    ( 0.25, SignalLevel.ELEVATED, "수익률 곡선 평탄 {v:+.2f}% (평탄화, 주의)"),
    (-99.9, SignalLevel.NORMAL,   "수익률 곡선 정상 {v:+.2f}%"),
]


def get_yield_curve_signal(
    date: pd.Timestamp | None = None,
    api_key: str | None = None,
) -> YieldCurveSignal | None:
    """
    2Y-10Y 수익률 곡선 시그널 조회.

    Returns:
        YieldCurveSignal | None (API 실패 시)
    """
    s2y  = _fetch_fred_series_latest("DGS2",  lookback_days=30, api_key=api_key)
    s10y = _fetch_fred_series_latest("DGS10", lookback_days=30, api_key=api_key)

    if s2y.empty or s10y.empty:
        return None

    # 날짜 기준 필터
    if date is not None:
        s2y  = s2y[s2y.index <= date]
        s10y = s10y[s10y.index <= date]

    if s2y.empty or s10y.empty:
        return None

    # 공통 날짜에서 최신값
    common = s2y.index.intersection(s10y.index)
    if common.empty:
        latest_date = min(s2y.index[-1], s10y.index[-1])
        y2  = float(s2y.reindex(s2y.index).iloc[-1])
        y10 = float(s10y.reindex(s10y.index).iloc[-1])
    else:
        latest_date = common[-1]
        y2  = float(s2y[latest_date])
        y10 = float(s10y[latest_date])

    spread = y10 - y2  # 양수 = 정상, 음수 = 역전

    # 역전 기준 (역방향 체크)
    if spread <= -0.75:
        level, reason = SignalLevel.EXTREME, f"수익률 곡선 역전 {spread:+.2f}% (심각)"
    elif spread <= -0.25:
        level, reason = SignalLevel.HIGH,    f"수익률 곡선 역전 {spread:+.2f}% (경기침체 선행)"
    elif spread <= 0.25:
        level, reason = SignalLevel.ELEVATED, f"수익률 곡선 평탄 {spread:+.2f}% (주의)"
    else:
        level, reason = SignalLevel.NORMAL,  f"수익률 곡선 정상 {spread:+.2f}%"

    return YieldCurveSignal(
        date=latest_date, spread_2y10y=spread,
        level=level, reason=reason,
    )


# ── 복합 시그널 ──────────────────────────────────────────────────────────────

def get_macro_signal_summary(
    date: pd.Timestamp | None = None,
    api_key: str | None = None,
    block_on_high: bool = True,
    block_on_extreme: bool = True,
) -> MacroSignalSummary:
    """
    크레딧 스프레드 + 수익률 곡선 복합 시그널.

    Args:
        date: 기준 날짜 (None = 오늘)
        block_on_high: HIGH 수준 시 진입 차단
        block_on_extreme: EXTREME 수준 시 진입 차단

    Returns:
        MacroSignalSummary
    """
    ref_date = date or pd.Timestamp.today().normalize()
    api_key  = api_key or os.getenv("FRED_API_KEY", "")

    credit = get_credit_spread_signal(ref_date, api_key)
    yc     = get_yield_curve_signal(ref_date, api_key)

    levels = []
    reasons = []

    if credit:
        levels.append(credit.level)
        if credit.level >= SignalLevel.ELEVATED:
            reasons.append(credit.reason)

    if yc:
        levels.append(yc.level)
        if yc.level >= SignalLevel.ELEVATED:
            reasons.append(yc.reason)

    combined = max(levels) if levels else SignalLevel.NORMAL

    block = (
        (combined >= SignalLevel.HIGH and block_on_high) or
        (combined >= SignalLevel.EXTREME and block_on_extreme)
    )

    return MacroSignalSummary(
        date=ref_date,
        credit=credit,
        yield_curve=yc,
        combined_level=combined,
        block_entry=block,
        reasons=reasons,
    )


# ── 히스토리컬 조회 (백테스트용) ────────────────────────────────────────────

def build_macro_signal_history(
    start: datetime,
    end: datetime,
    api_key: str | None = None,
) -> pd.DataFrame:
    """
    백테스트용 — 날짜별 매크로 시그널 사전 계산.

    Returns:
        DataFrame: date, hy_oas, spread_2y10y, credit_level, yc_level, combined_level, block_entry
    """
    key = api_key or os.getenv("FRED_API_KEY", "")
    start_str = start.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    def _fetch_range(series_id: str) -> pd.Series:
        try:
            resp = requests.get(
                f"{FRED_BASE}/series/observations",
                params={"series_id": series_id, "api_key": key, "file_type": "json",
                        "observation_start": start_str, "observation_end": end_str},
                timeout=15,
            )
            if not resp.ok:
                return pd.Series(dtype=float, name=series_id)
            obs = [(pd.Timestamp(o["date"]), float(o["value"]))
                   for o in resp.json().get("observations", []) if o["value"] != "."]
            dates, vals = zip(*obs) if obs else ([], [])
            return pd.Series(dict(zip(dates, vals)), name=series_id)
        except Exception as e:
            log.debug("FRED 히스토리 실패 [%s]: %s", series_id, e)
            return pd.Series(dtype=float, name=series_id)

    hy_oas = _fetch_range("BAMLH0A0HYM2").ffill()
    dgs2   = _fetch_range("DGS2").ffill()
    dgs10  = _fetch_range("DGS10").ffill()

    # 공통 날짜 인덱스
    idx = hy_oas.index.union(dgs2.index).union(dgs10.index)
    hy_oas = hy_oas.reindex(idx).ffill()
    dgs2   = dgs2.reindex(idx).ffill()
    dgs10  = dgs10.reindex(idx).ffill()
    spread = dgs10 - dgs2

    # 레벨 계산
    def _credit_level(v: float) -> int:
        if v >= 8.5: return int(SignalLevel.EXTREME)
        if v >= 6.0: return int(SignalLevel.HIGH)
        if v >= 4.5: return int(SignalLevel.ELEVATED)   # 2025 관세 충격 수준
        return int(SignalLevel.NORMAL)

    def _yc_level(v: float) -> int:
        if v <= -0.75: return int(SignalLevel.EXTREME)
        if v <= -0.25: return int(SignalLevel.HIGH)
        if v <=  0.25: return int(SignalLevel.ELEVATED)
        return int(SignalLevel.NORMAL)

    df = pd.DataFrame({
        "hy_oas":        hy_oas,
        "spread_2y10y":  spread,
        "credit_level":  hy_oas.apply(_credit_level),
        "yc_level":      spread.apply(_yc_level),
    }, index=idx)

    df["combined_level"] = df[["credit_level", "yc_level"]].max(axis=1)
    df["block_entry"]    = df["combined_level"] >= int(SignalLevel.HIGH)

    return df.dropna(subset=["hy_oas"])


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)

    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    summary = get_macro_signal_summary()
    print(f"=== 매크로 시그널 ({summary.date.date()}) ===")
    if summary.credit:
        print(f"크레딧 스프레드: {summary.credit.reason}")
    if summary.yield_curve:
        print(f"수익률 곡선:     {summary.yield_curve.reason}")
    print(f"복합 레벨:       {summary.combined_level.name}")
    print(f"진입 차단:       {'⛔ YES' if summary.block_entry else '✅ NO'}")
    if summary.reasons:
        print(f"경고 사유:       {', '.join(summary.reasons)}")
