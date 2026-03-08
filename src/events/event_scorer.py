"""
통합 이벤트 스코어러

뉴스 센티먼트 + SEC 공시 + (향후) 지수 리밸런싱 점수를 통합하여
종목별 이벤트 종합 점수를 산출한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.events.news_sentiment import compute_event_score as news_score
from src.events.sec_filings import compute_sec_score as sec_score


@dataclass
class EventSignal:
    """종목별 이벤트 종합 시그널."""
    symbol: str
    date: str
    news_score: int          # -10 ~ +10
    sec_score: int           # -5 ~ +5
    total_score: int         # 가중 합산
    action: str              # "BLOCK", "NEUTRAL", "BOOST"
    reason: str


def evaluate_events(
    symbol: str,
    date: str,
    news_lookback: int = 7,
    sec_lookback: int = 30,
) -> EventSignal:
    """
    종목의 이벤트 종합 시그널을 평가한다.

    통합 로직:
      - 뉴스 점수 (가중치 1.0) + SEC 점수 (가중치 1.5)
      - total < -2: BLOCK (진입 차단)
      - total >= +3: BOOST (R:R 기준 완화)
      - 그 외: NEUTRAL

    Args:
        symbol: 종목 심볼
        date: 기준일 (YYYY-MM-DD)
        news_lookback: 뉴스 조회 기간 (일)
        sec_lookback: SEC 공시 조회 기간 (일)
    """
    n_score = news_score(symbol, date, news_lookback)
    s_score = sec_score(symbol, date, sec_lookback)

    # 가중 합산: SEC 공시에 더 높은 가중치 (구조적 이벤트이므로)
    total = int(round(n_score * 1.0 + s_score * 1.5))

    if total <= -2:
        action = "BLOCK"
        reason = _build_reason(n_score, s_score, "부정 이벤트 감지 — 진입 차단")
    elif total >= 3:
        action = "BOOST"
        reason = _build_reason(n_score, s_score, "긍정 이벤트 — R:R 기준 완화")
    else:
        action = "NEUTRAL"
        reason = _build_reason(n_score, s_score, "이벤트 중립")

    return EventSignal(
        symbol=symbol,
        date=date,
        news_score=n_score,
        sec_score=s_score,
        total_score=total,
        action=action,
        reason=reason,
    )


def _build_reason(n_score: int, s_score: int, summary: str) -> str:
    parts = [summary]
    if n_score != 0:
        parts.append(f"뉴스={n_score:+d}")
    if s_score != 0:
        parts.append(f"SEC={s_score:+d}")
    return " | ".join(parts)
