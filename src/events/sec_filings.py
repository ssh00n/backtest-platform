"""
SEC EDGAR 공시 크롤러

SEC EDGAR EFTS (Full-Text Search) API를 사용하여
8-K 공시에서 주요 이벤트를 탐지한다.

API: https://efts.sec.gov/LATEST/search-index
무료, 키 불필요, Rate limit: 10 requests/sec
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests


# SEC EDGAR API 설정
_EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
_USER_AGENT = "HoonTradingSystem research@example.com"
_RATE_LIMIT_DELAY = 0.15  # 10 req/sec 준수


@dataclass
class SECEvent:
    """SEC 공시 이벤트."""
    symbol: str
    filing_date: str
    form_type: str
    event_type: str        # "buyback", "dilution", "ceo_change", "ma", etc.
    description: str
    sentiment_score: int   # -2 ~ +2
    filing_url: str = ""


# ── 8-K 이벤트 유형별 검색 쿼리 ──────────────────────────

_EVENT_QUERIES = {
    "buyback": {
        "query": '"stock repurchase" OR "share repurchase" OR "buyback program"',
        "score": +1,
        "description": "자사주 매입 프로그램",
    },
    "dilution": {
        "query": '"secondary offering" OR "shelf registration" OR "convertible notes"',
        "score": -2,
        "description": "지분 희석 리스크",
    },
    "ceo_change": {
        "query": '"chief executive officer" AND ("appointed" OR "resigned" OR "terminated")',
        "score": -1,
        "description": "CEO 변경",
    },
    "ma": {
        "query": '"acquisition" AND ("definitive agreement" OR "merger agreement")',
        "score": +1,
        "description": "M&A 관련",
    },
    "restructuring": {
        "query": '"restructuring" AND ("workforce reduction" OR "cost reduction")',
        "score": -1,
        "description": "구조조정",
    },
}


def search_sec_filings(
    query: str,
    ticker: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    form_type: str = "8-K",
    limit: int = 10,
) -> list[dict]:
    """
    SEC EDGAR EFTS에서 공시를 검색한다.

    Args:
        query: 검색 쿼리 (full-text)
        ticker: 종목 티커 (optional)
        start_date: 시작일 (YYYY-MM-DD)
        end_date: 종료일 (YYYY-MM-DD)
        form_type: 공시 유형 (기본: 8-K)
        limit: 최대 결과 수

    Returns:
        검색 결과 리스트
    """
    params = {
        "q": query,
        "forms": form_type,
        "from": 0,
        "size": limit,
    }

    if start_date and end_date:
        params["dateRange"] = "custom"
        params["startdt"] = start_date
        params["enddt"] = end_date

    if ticker:
        params["q"] = f'"{ticker}" AND ({query})'

    time.sleep(_RATE_LIMIT_DELAY)

    try:
        r = requests.get(
            _EDGAR_BASE,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=10,
        )
        if not r.ok:
            return []

        data = r.json()
        return data.get("hits", {}).get("hits", [])

    except (requests.RequestException, ValueError):
        return []


def get_sec_events(
    symbol: str,
    date: str,
    lookback_days: int = 30,
) -> list[SECEvent]:
    """
    특정 종목의 SEC 공시 이벤트를 검색한다.

    Args:
        symbol: 종목 심볼
        date: 기준일 (YYYY-MM-DD)
        lookback_days: 과거 조회 일수 (기본 30일)

    Returns:
        SECEvent 리스트
    """
    end_dt = datetime.strptime(date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)

    events = []

    for event_type, config in _EVENT_QUERIES.items():
        hits = search_sec_filings(
            query=config["query"],
            ticker=symbol,
            start_date=start_dt.strftime("%Y-%m-%d"),
            end_date=end_dt.strftime("%Y-%m-%d"),
            limit=5,
        )

        for hit in hits:
            src = hit.get("_source", {})
            # 종목 확인 (ticker가 display_names에 포함되는지)
            display_names = src.get("display_names", [])
            ticker_match = any(
                f"({symbol})" in name or f" {symbol} " in name
                for name in display_names
            )
            if not ticker_match and display_names:
                continue

            events.append(SECEvent(
                symbol=symbol,
                filing_date=src.get("file_date", ""),
                form_type=src.get("form_type", "8-K"),
                event_type=event_type,
                description=config["description"],
                sentiment_score=config["score"],
                filing_url=src.get("file_url", ""),
            ))

    return events


def compute_sec_score(
    symbol: str,
    date: str,
    lookback_days: int = 30,
) -> int:
    """
    SEC 공시 기반 종합 점수.

    Returns:
        -5 ~ +5 범위 점수
    """
    events = get_sec_events(symbol, date, lookback_days)

    if not events:
        return 0

    total = sum(e.sentiment_score for e in events)
    return max(-5, min(5, total))
