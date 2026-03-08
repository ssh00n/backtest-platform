"""
매크로 이벤트 캘린더 (FRED + FMP)

FRED API: 연준 기준금리 변경, CPI 발표 등 공식 경제지표
FMP API:  경제 캘린더 (FOMC, NFP, CPI 일정)

환경변수:
    FRED_API_KEY  - FRED API (선택, 없으면 스킵)
    FMP_API_KEY   - FMP API (선택, 없으면 스킵)
"""
from __future__ import annotations

import logging
import os

# .env 자동 로드
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import requests

log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"
FMP_CALENDAR_URL = "https://financialmodelingprep.com/api/v3/economic_calendar"

# 주요 FRED 시리즈 ID
FRED_SERIES = {
    "FED_RATE":   "FEDFUNDS",     # 연방기금금리
    "CPI_YOY":    "CPIAUCSL",     # CPI (전년대비)
    "UNEMP":      "UNRATE",       # 실업률
    "VIX":        "VIXCLS",       # VIX (종가)
    "10Y_YIELD":  "DGS10",        # 10년 국채 수익률
}

# 고충격 경제 이벤트 키워드
HIGH_IMPACT_KEYWORDS = [
    "Federal Funds", "FOMC", "Interest Rate",  # 연준
    "CPI", "Consumer Price",                    # 물가
    "Tariff", "Trade", "Import Duty",           # 관세/무역
    "Non Farm", "NFP", "Employment",            # 고용
]


@dataclass
class EconomicEvent:
    """경제 캘린더 이벤트."""
    event_date: pd.Timestamp
    event_name: str
    country: str = "US"
    impact: str = "Low"          # "High" | "Medium" | "Low"
    actual: float | None = None
    estimate: float | None = None
    previous: float | None = None
    surprise_pct: float | None = None   # (actual - estimate) / |estimate|
    source: str = "FMP"


def fetch_fred_series(
    series_id: str,
    start: datetime,
    end: datetime,
    api_key: str | None = None,
) -> pd.Series:
    """FRED에서 경제 데이터 시리즈 조회."""
    key = api_key or os.getenv("FRED_API_KEY", "")
    if not key:
        log.debug("FRED_API_KEY 없음, 스킵")
        return pd.Series(dtype=float, name=series_id)

    try:
        resp = requests.get(
            f"{FRED_BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": start.strftime("%Y-%m-%d"),
                "observation_end": end.strftime("%Y-%m-%d"),
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return pd.Series(dtype=float, name=series_id)

        obs = resp.json().get("observations", [])
        data = {
            pd.Timestamp(o["date"]): float(o["value"])
            for o in obs
            if o["value"] != "."
        }
        return pd.Series(data, name=series_id)

    except Exception as e:
        log.debug("FRED 조회 실패 [%s]: %s", series_id, e)
        return pd.Series(dtype=float, name=series_id)


def fetch_fmp_economic_calendar(
    start: datetime,
    end: datetime,
    api_key: str | None = None,
) -> list[EconomicEvent]:
    """FMP 경제 캘린더에서 고충격 이벤트 조회."""
    key = api_key or os.getenv("FMP_API_KEY", "")
    if not key:
        log.debug("FMP_API_KEY 없음, 스킵")
        return []

    try:
        resp = requests.get(
            FMP_CALENDAR_URL,
            params={
                "apikey": key,
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        events = []
        for item in resp.json():
            impact = item.get("impact", "Low")
            if impact not in ("High", "Medium"):
                continue  # 저충격 이벤트 스킵

            actual = item.get("actual")
            estimate = item.get("estimate")
            surprise = None
            if actual is not None and estimate is not None:
                try:
                    denom = abs(float(estimate)) or 1.0
                    surprise = (float(actual) - float(estimate)) / denom
                except (TypeError, ValueError):
                    pass

            try:
                event_date = pd.Timestamp(item["date"])
            except Exception:
                continue

            events.append(EconomicEvent(
                event_date=event_date,
                event_name=item.get("event", ""),
                country=item.get("country", "US"),
                impact=impact,
                actual=float(actual) if actual is not None else None,
                estimate=float(estimate) if estimate is not None else None,
                surprise_pct=surprise,
                source="FMP",
            ))

        return events

    except Exception as e:
        log.debug("FMP 경제 캘린더 실패: %s", e)
        return []


def fetch_fred_release_calendar(
    start: datetime,
    end: datetime,
    api_key: str | None = None,
) -> list[EconomicEvent]:
    """
    FRED 발표 캘린더에서 고충격 경제 이벤트 조회.

    FMP economic_calendar 대체 (무료, API KEY 있으면 전부 조회).
    NFP, CPI, GDP, FOMC 발표일 포함.

    주요 Release ID:
        10  = Employment Situation (NFP)
        21  = Consumer Price Index (CPI)
        53  = Gross Domestic Product (GDP)
        175 = FOMC Press Release
        18  = Industrial Production
    """
    key = api_key or os.getenv("FRED_API_KEY", "")
    if not key:
        log.debug("FRED_API_KEY 없음, 경제 캘린더 스킵")
        return []

    # 고충격 FRED 발표 (release_id → 이름, 충격도)
    HIGH_IMPACT_RELEASES = {
        "10":  ("Employment Situation (NFP)", "High"),
        "21":  ("Consumer Price Index (CPI)", "High"),
        "53":  ("Gross Domestic Product (GDP)", "High"),
        "175": ("FOMC Press Release", "High"),
        "82":  ("Producer Price Index (PPI)", "Medium"),
        "18":  ("Industrial Production", "Medium"),
        "22":  ("Retail Sales", "Medium"),
    }

    events: list[EconomicEvent] = []
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    for release_id, (name, impact) in HIGH_IMPACT_RELEASES.items():
        try:
            resp = requests.get(
                f"{FRED_BASE}/release/dates",
                params={
                    "release_id": release_id,
                    "api_key": key,
                    "file_type": "json",
                    "realtime_start": start_str,
                    "realtime_end": end_str,
                    "include_release_dates_with_no_data": "true",
                },
                timeout=10,
            )
            if not resp.ok:
                continue

            for item in resp.json().get("release_dates", []):
                date_str = item.get("date", "")
                if not date_str or not (start_str <= date_str <= end_str):
                    continue
                events.append(EconomicEvent(
                    event_date=pd.Timestamp(date_str),
                    event_name=name,
                    country="US",
                    impact=impact,
                    source="FRED",
                ))
        except Exception as e:
            log.debug("FRED release dates 실패 [%s]: %s", release_id, e)

    log.debug("FRED 경제 캘린더: %d 이벤트 (%s~%s)", len(events), start_str, end_str)
    return events


def get_macro_risk_for_date(
    date: pd.Timestamp,
    window_before: int = 3,
    window_after: int = 1,
    fmp_api_key: str | None = None,
    fred_api_key: str | None = None,
) -> tuple[str, list[str]]:
    """
    특정 날짜의 매크로 위험도를 반환한다.

    Args:
        date: 조회 날짜
        window_before: 이벤트 영향 이전 일수
        window_after:  이벤트 영향 이후 일수

    Returns:
        (risk_level, reasons): "HIGH" | "MEDIUM" | "LOW", 이유 목록
    """
    from datetime import timedelta
    start = (date - pd.Timedelta(days=window_before)).to_pydatetime()
    end = (date + pd.Timedelta(days=window_after)).to_pydatetime()

    # FMP 경제 캘린더 + FRED 발표 캘린더 병합
    events = fetch_fmp_economic_calendar(start, end, fmp_api_key)
    events += fetch_fred_release_calendar(start, end, fred_api_key)
    reasons = []
    risk = "LOW"

    for ev in events:
        if ev.impact == "High":
            risk = "HIGH"
            surprise_str = f" (서프라이즈 {ev.surprise_pct:+.1%})" if ev.surprise_pct else ""
            reasons.append(f"{ev.event_date:%m/%d} {ev.event_name}{surprise_str}")
        elif ev.impact == "Medium" and risk == "LOW":
            risk = "MEDIUM"
            reasons.append(f"{ev.event_date:%m/%d} {ev.event_name}")

    return risk, reasons
