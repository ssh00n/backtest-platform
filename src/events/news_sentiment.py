"""
뉴스 센티먼트 분석 (Alpaca News API)

Alpaca의 News API에서 종목별 뉴스를 수집하고,
실적 관련 키워드 기반으로 이벤트 점수를 산출한다.

무료 플랜: 200 requests/min, 뉴스 콘텐츠 포함 가능
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()


@dataclass
class NewsEvent:
    """뉴스 이벤트 하나를 표현한다."""
    symbol: str
    headline: str
    source: str
    created_at: str
    event_type: str          # "earnings_beat", "earnings_miss", "buyback", "upgrade", "downgrade", etc.
    sentiment_score: int     # -2 ~ +2
    url: str = ""


# ── 키워드 기반 이벤트 분류 ──────────────────────────────

_POSITIVE_KEYWORDS = {
    "earnings_beat": [
        "beats", "beat estimates", "tops expectations", "exceeds",
        "surpasses", "better than expected", "strong quarter",
        "record revenue", "raises guidance", "guidance above",
    ],
    "upgrade": [
        "upgrade", "buy rating", "outperform", "price target raised",
        "overweight", "top pick",
    ],
    "buyback": [
        "buyback", "share repurchase", "stock repurchase",
        "repurchase program",
    ],
    "positive_catalyst": [
        "fda approval", "contract win", "partnership",
        "expansion", "acquisition",
    ],
}

_NEGATIVE_KEYWORDS = {
    "earnings_miss": [
        "misses", "missed estimates", "falls short", "below expectations",
        "disappointing", "weak quarter", "lowers guidance",
        "guidance below", "revenue decline",
    ],
    "downgrade": [
        "downgrade", "sell rating", "underperform",
        "price target cut", "underweight",
    ],
    "negative_catalyst": [
        "lawsuit", "sec investigation", "recall", "layoffs",
        "restructuring charge", "ceo resign", "cfo resign",
        "dilution", "secondary offering", "shelf registration",
    ],
}

# 점수 매핑
_SCORE_MAP = {
    "earnings_beat": +2,
    "upgrade": +1,
    "buyback": +1,
    "positive_catalyst": +1,
    "earnings_miss": -2,
    "downgrade": -1,
    "negative_catalyst": -1,
}


def fetch_news(
    symbol: str,
    start: str,
    end: str,
    limit: int = 50,
) -> list[dict]:
    """
    Alpaca News API에서 종목 뉴스를 가져온다.

    Args:
        symbol: 종목 심볼 (예: "AAPL")
        start: 시작일 (YYYY-MM-DD)
        end: 종료일 (YYYY-MM-DD)
        limit: 최대 뉴스 수

    Returns:
        뉴스 딕셔너리 리스트
    """
    key = os.getenv("ALPACA_API_KEY")
    secret = os.getenv("ALPACA_API_SECRET")

    if not key or not secret:
        return []

    r = requests.get(
        "https://data.alpaca.markets/v1beta1/news",
        params={
            "symbols": symbol,
            "start": start,
            "end": end,
            "limit": limit,
            "include_content": "false",
        },
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        },
        timeout=10,
    )

    if not r.ok:
        return []

    return r.json().get("news", [])


def classify_news(headline: str) -> tuple[str, int]:
    """
    헤드라인을 키워드 기반으로 분류하고 점수를 반환한다.

    Returns:
        (event_type, score) — 분류 불가 시 ("neutral", 0)
    """
    hl_lower = headline.lower()

    # 부정 키워드 먼저 (보수적 접근)
    for event_type, keywords in _NEGATIVE_KEYWORDS.items():
        for kw in keywords:
            if kw in hl_lower:
                return event_type, _SCORE_MAP[event_type]

    # 긍정 키워드
    for event_type, keywords in _POSITIVE_KEYWORDS.items():
        for kw in keywords:
            if kw in hl_lower:
                return event_type, _SCORE_MAP[event_type]

    return "neutral", 0


def get_news_events(
    symbol: str,
    date: str,
    lookback_days: int = 7,
) -> list[NewsEvent]:
    """
    특정 날짜 기준으로 lookback_days 이내의 뉴스 이벤트를 분석한다.

    Args:
        symbol: 종목 심볼
        date: 기준일 (YYYY-MM-DD)
        lookback_days: 과거 조회 일수

    Returns:
        NewsEvent 리스트 (중립 제외)
    """
    end_dt = datetime.strptime(date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)

    news_items = fetch_news(
        symbol,
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
    )

    events = []
    for item in news_items:
        event_type, score = classify_news(item.get("headline", ""))
        if score != 0:
            events.append(NewsEvent(
                symbol=symbol,
                headline=item.get("headline", ""),
                source=item.get("source", ""),
                created_at=item.get("created_at", ""),
                event_type=event_type,
                sentiment_score=score,
                url=item.get("url", ""),
            ))

    return events


def compute_event_score(
    symbol: str,
    date: str,
    lookback_days: int = 7,
) -> int:
    """
    종목의 이벤트 종합 점수를 반환한다.

    최근 뉴스 이벤트의 점수를 합산하되,
    시간 가중치를 적용한다 (최근일수록 가중치 높음).

    Returns:
        종합 점수 (-10 ~ +10 범위)
    """
    events = get_news_events(symbol, date, lookback_days)

    if not events:
        return 0

    total = 0
    end_dt = datetime.strptime(date, "%Y-%m-%d")

    for event in events:
        # 시간 가중치: 최근 이벤트에 더 높은 가중치
        event_dt = datetime.strptime(event.created_at[:10], "%Y-%m-%d")
        days_ago = (end_dt - event_dt).days
        weight = max(0.3, 1.0 - days_ago * 0.1)  # 7일 전 = 0.3, 당일 = 1.0

        total += event.sentiment_score * weight

    # 범위 제한
    return max(-10, min(10, int(round(total))))
