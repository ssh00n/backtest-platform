"""
뉴스 크롤러 (News Crawler)

섹터 & 기간 기반 이벤트 수집.

데이터 소스:
  1. Alpaca News API — 종목/섹터 뉴스
  2. FRED API — 금리, CPI, 고용 등 매크로 이벤트

목적:
  돌파 시점의 섹터 모멘텀과 매크로 환경을 분석하여
  "구조적 이벤트 기반 돌파"인지 판별한다.
"""

import os

# .env 자동 로드
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd
import requests

from src.utils.logger import get_logger

log = get_logger(__name__)

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"

# 섹터 → 대표 ETF 매핑 (섹터 모멘텀 뉴스 대리)
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
    "Consumer Staples": "XLP",
}

# 주요 매크로 이벤트 FRED 시리즈
MACRO_SERIES = {
    "CPI": "CPIAUCSL",          # 소비자물가지수
    "FED_RATE": "FEDFUNDS",     # 연방기금금리
    "UNEMPLOYMENT": "UNRATE",   # 실업률
}


@dataclass
class NewsItem:
    """단일 뉴스 항목."""
    headline: str
    published_at: pd.Timestamp
    symbols: list[str] = field(default_factory=list)
    sentiment: str = "NEUTRAL"   # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    relevance_score: float = 0.0


@dataclass
class SectorEventSummary:
    """섹터 이벤트 요약."""
    symbol: str
    sector: str
    breakout_date: pd.Timestamp
    company_news: list[NewsItem] = field(default_factory=list)
    sector_news: list[NewsItem] = field(default_factory=list)
    macro_context: dict = field(default_factory=dict)

    # 최종 판정
    event_quality: str = "NO_EVENT"   # "STRONG_CATALYST" | "CATALYST" | "SECTOR_DRIVEN" | "NO_EVENT"
    event_summary: str = ""


# ── 긍/부정 키워드 ─────────────────────────────────────────

POSITIVE_KEYWORDS = [
    "beat", "exceed", "surpass", "record", "growth", "upgrade",
    "guidance raised", "strong", "robust", "outperform", "buy",
    "acquisition", "partnership", "contract", "approval", "wins",
]

NEGATIVE_KEYWORDS = [
    "miss", "below", "disappoint", "cut", "lower", "downgrade",
    "guidance cut", "weak", "loss", "decline", "sell", "investigation",
    "recall", "lawsuit", "concern",
]


def _classify_sentiment(headline: str) -> str:
    """헤드라인 감성 분류 (간단한 키워드 기반)."""
    headline_lower = headline.lower()
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in headline_lower)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in headline_lower)
    if pos > neg:
        return "POSITIVE"
    if neg > pos:
        return "NEGATIVE"
    return "NEUTRAL"


def fetch_company_news(
    symbol: str,
    start_date: datetime,
    end_date: datetime,
    api_key: str | None = None,
    api_secret: str | None = None,
    limit: int = 30,
) -> list[NewsItem]:
    """
    종목별 뉴스를 Alpaca에서 가져온다.
    """
    key = api_key or os.getenv("ALPACA_API_KEY", "")
    secret = api_secret or os.getenv("ALPACA_API_SECRET", "")

    if not key or not secret:
        return []

    try:
        resp = requests.get(
            ALPACA_NEWS_URL,
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
            },
            params={
                "symbols": symbol,
                "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
                "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
                "limit": limit,
                "sort": "desc",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []

        items = []
        for n in resp.json().get("news", []):
            headline = n.get("headline", "")
            try:
                ts = pd.Timestamp(n["created_at"]).normalize()
            except Exception:
                continue
            items.append(NewsItem(
                headline=headline,
                published_at=ts,
                symbols=n.get("symbols", [symbol]),
                sentiment=_classify_sentiment(headline),
            ))
        return items

    except Exception as e:
        log.debug("Company news fetch failed for %s: %s", symbol, e)
        return []


def fetch_sector_news(
    sector: str,
    start_date: datetime,
    end_date: datetime,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> list[NewsItem]:
    """
    섹터 ETF 기반 섹터 뉴스를 가져온다.
    """
    etf = SECTOR_ETF_MAP.get(sector)
    if not etf:
        log.debug("No ETF mapping for sector: %s", sector)
        return []

    return fetch_company_news(etf, start_date, end_date, api_key, api_secret, limit=20)


def fetch_macro_context(
    target_date: datetime,
    lookback_months: int = 1,
) -> dict:
    """
    FRED에서 돌파일 기준 최신 매크로 지표를 가져온다.
    무료 API (no key required for public series).

    Returns:
        {"CPI": float, "FED_RATE": float, "UNEMPLOYMENT": float}
    """
    fred_key = os.getenv("FRED_API_KEY", "")
    if not fred_key:
        log.debug("FRED_API_KEY not set, skipping macro context")
        return {}

    start = target_date - timedelta(days=lookback_months * 31)
    context = {}

    for name, series_id in MACRO_SERIES.items():
        try:
            resp = requests.get(
                FRED_API_URL,
                params={
                    "series_id": series_id,
                    "observation_start": start.strftime("%Y-%m-%d"),
                    "observation_end": target_date.strftime("%Y-%m-%d"),
                    "api_key": fred_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 2,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                obs = resp.json().get("observations", [])
                if obs:
                    try:
                        context[name] = float(obs[0]["value"])
                    except (ValueError, KeyError):
                        pass
        except Exception as e:
            log.debug("FRED fetch failed for %s: %s", series_id, e)

    return context


def build_sector_event_summary(
    symbol: str,
    sector: str,
    breakout_date: pd.Timestamp,
    window_before: int = 7,
    window_after: int = 2,
) -> SectorEventSummary:
    """
    종목의 돌파 시점 전후 이벤트를 수집하고 요약한다.

    Args:
        symbol: 종목 심볼
        sector: 섹터명
        breakout_date: 돌파일
        window_before: 이전 탐색 일수
        window_after: 이후 탐색 일수

    Returns:
        SectorEventSummary
    """
    start = (breakout_date - timedelta(days=window_before)).to_pydatetime()
    end = (breakout_date + timedelta(days=window_after)).to_pydatetime()

    summary = SectorEventSummary(
        symbol=symbol,
        sector=sector,
        breakout_date=breakout_date,
    )

    # 1. 종목 뉴스 (Alpaca 제거 → 빈 리스트, 향후 FMP 뉴스 API로 대체 가능)
    summary.company_news = []

    # 2. 섹터 뉴스 (Alpaca 제거 → 빈 리스트)
    summary.sector_news = []

    # 3. 매크로 컨텍스트
    summary.macro_context = fetch_macro_context(breakout_date.to_pydatetime())

    # 4. 이벤트 품질 판정
    positive_company = [n for n in summary.company_news if n.sentiment == "POSITIVE"]
    negative_company = [n for n in summary.company_news if n.sentiment == "NEGATIVE"]
    positive_sector = [n for n in summary.sector_news if n.sentiment == "POSITIVE"]

    if len(positive_company) >= 2:
        summary.event_quality = "STRONG_CATALYST"
        summary.event_summary = f"종목 긍정 뉴스 {len(positive_company)}건 (강한 촉매)"
    elif len(positive_company) >= 1:
        summary.event_quality = "CATALYST"
        summary.event_summary = f"종목 긍정 뉴스 {len(positive_company)}건"
    elif len(positive_sector) >= 2:
        summary.event_quality = "SECTOR_DRIVEN"
        summary.event_summary = f"섹터 모멘텀 {len(positive_sector)}건 (개별 촉매 없음)"
    elif len(negative_company) >= 1:
        summary.event_quality = "NO_EVENT"
        summary.event_summary = f"부정적 뉴스 {len(negative_company)}건 → 기술적 돌파만"
    else:
        summary.event_quality = "NO_EVENT"
        summary.event_summary = "이벤트 없음 → 순수 기술적 돌파"

    return summary


def format_event_summary(summary: SectorEventSummary) -> str:
    """SectorEventSummary를 사람이 읽기 쉬운 포맷으로 출력."""
    lines = [
        f"[{summary.symbol}] {summary.breakout_date:%Y-%m-%d} 돌파 이벤트 분석",
        f"  섹터: {summary.sector}",
        f"  판정: {summary.event_quality} — {summary.event_summary}",
    ]

    if summary.company_news:
        lines.append(f"  종목 뉴스 ({len(summary.company_news)}건):")
        for n in summary.company_news[:3]:
            lines.append(f"    [{n.sentiment}] {n.published_at:%Y-%m-%d} {n.headline[:60]}")

    if summary.sector_news:
        lines.append(f"  섹터 뉴스 ({len(summary.sector_news)}건):")
        for n in summary.sector_news[:2]:
            lines.append(f"    [{n.sentiment}] {n.headline[:60]}")

    if summary.macro_context:
        ctx = summary.macro_context
        lines.append("  매크로:")
        if "FED_RATE" in ctx:
            lines.append(f"    금리: {ctx['FED_RATE']:.2f}%")
        if "CPI" in ctx:
            lines.append(f"    CPI: {ctx['CPI']:.1f}")

    return "\n".join(lines)
