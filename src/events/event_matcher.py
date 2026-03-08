"""
이벤트 매처 (Event Matcher)

Darvas Box 돌파 신호에 이벤트 컨텍스트를 결합한다.

핵심 철학 (hoon-strategy.md):
  "Macro가 형성한 상승장 안에서, 망하지 않을 이유(생존 필터)를 확인하고,
   강제 수급 주체가 자금을 움직인 증거(거래량)를 포착하여,
   시간의 압축 지점(이벤트)에서만 집행한다."

이벤트 매처는 위 원칙의 마지막 조건인 '시간의 압축 지점' 검증을 담당한다.
"""

from dataclasses import dataclass, field
import os

# .env 자동 로드
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    load_dotenv(_Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

import pandas as pd

from src.screener.darvas_box import BoxBreakout
from src.events.earnings_calendar import (
    EarningsEvent,
    find_events_near_breakout,
    classify_event_quality,
)
from src.events.news_crawler import (
    SectorEventSummary,
    build_sector_event_summary,
    format_event_summary,
)
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class EnrichedBreakout:
    """이벤트 컨텍스트가 붙은 돌파 신호."""
    breakout: BoxBreakout
    sector: str

    # 이벤트 분석 결과
    earnings_events: list[EarningsEvent] = field(default_factory=list)
    earnings_quality: str = "NO_EVENT"   # "CATALYST" | "FILING" | "NO_EVENT"
    sector_summary: SectorEventSummary | None = None

    # 최종 진입 점수 (0~100)
    event_score: int = 0

    # 진입 권고
    recommendation: str = "HOLD"   # "STRONG_BUY" | "BUY" | "WATCH" | "HOLD"
    reason: str = ""


# ── 이벤트 스코어 계산 ─────────────────────────────────────

def compute_event_score(
    earnings_quality: str,
    sector_quality: str,
    rr_ratio: float,
    vol_ratio: float,
) -> int:
    """
    이벤트 + 기술적 지표를 결합한 진입 점수를 계산한다. (0~100)

    구성:
      - 이벤트 품질 (0~50점)
      - R:R 비율 (0~25점)
      - 거래량 비율 (0~25점)
    """
    score = 0

    # 이벤트 품질 (최대 50점)
    earnings_scores = {
        "EARNINGS_BEAT":     50,  # FMP 실적 Beat — 최강 촉매
        "CATALYST_EARNINGS": 45,  # SEC 8-K Item 2.02/7.01 (실적/가이던스 공시)
        "CATALYST":          30,  # SEC 8-K 기타 (M&A, 중대 공시)
        "EARNINGS":          25,  # 실적 발표 (Beat/Miss 불명확)
        "EARNINGS_MISS":      0,  # 실적 Miss — 부정적
        "NO_EVENT":           0,
    }
    sector_scores = {
        "STRONG_CATALYST": 30,
        "CATALYST": 20,
        "SECTOR_DRIVEN": 10,
        "NO_EVENT": 0,
    }
    score += earnings_scores.get(earnings_quality, 0)
    # 섹터 이벤트는 개별 이벤트 없을 때만 가점
    if earnings_quality == "NO_EVENT":
        score += sector_scores.get(sector_quality, 0)

    # R:R 비율 (최대 25점)
    if rr_ratio >= 6.0:
        score += 25
    elif rr_ratio >= 5.0:
        score += 20
    elif rr_ratio >= 4.0:
        score += 15
    elif rr_ratio >= 3.0:
        score += 10

    # 거래량 비율 (최대 25점)
    if vol_ratio >= 3.0:
        score += 25
    elif vol_ratio >= 2.5:
        score += 20
    elif vol_ratio >= 2.0:
        score += 15
    elif vol_ratio >= 1.5:
        score += 10

    return min(score, 100)


def score_to_recommendation(score: int) -> str:
    """점수를 진입 권고로 변환."""
    if score >= 70:
        return "STRONG_BUY"
    if score >= 50:
        return "BUY"
    if score >= 30:
        return "WATCH"
    return "HOLD"


# ── 메인 통합 함수 ────────────────────────────────────────

def enrich_breakout(
    breakout: BoxBreakout,
    sector: str,
    fmp_api_key: str | None = None,
    window_before: int = 5,
    window_after: int = 2,
    # 하위 호환성 유지 (deprecated)
    api_key: str | None = None,
    api_secret: str | None = None,
) -> EnrichedBreakout:
    """
    Darvas Box 돌파에 이벤트 컨텍스트를 결합한다.

    Args:
        breakout: BoxBreakout 신호
        sector: 종목 섹터
        fmp_api_key: FMP API Key (없으면 환경변수 FMP_API_KEY 사용)
        window_before: 돌파 이전 탐색 일수
        window_after: 돌파 이후 탐색 일수

    Returns:
        EnrichedBreakout
    """
    enriched = EnrichedBreakout(breakout=breakout, sector=sector)

    # 1. 실적 이벤트 조회 (FMP + SEC EDGAR 8-K)
    fmp_key = fmp_api_key or os.getenv("FMP_API_KEY")
    enriched.earnings_events = find_events_near_breakout(
        symbol=breakout.symbol,
        breakout_date=breakout.breakout_date,
        window_before=window_before,
        window_after=window_after,
        fmp_api_key=fmp_key,
    )
    enriched.earnings_quality = classify_event_quality(enriched.earnings_events)

    # 2. 섹터 + 매크로 뉴스 수집 (Alpaca 의존성 제거, SEC/FRED만 사용)
    enriched.sector_summary = build_sector_event_summary(
        symbol=breakout.symbol,
        sector=sector,
        breakout_date=breakout.breakout_date,
        window_before=window_before,
        window_after=window_after,
    )
    sector_quality = enriched.sector_summary.event_quality if enriched.sector_summary else "NO_EVENT"

    # 3. 점수 계산
    enriched.event_score = compute_event_score(
        earnings_quality=enriched.earnings_quality,
        sector_quality=sector_quality,
        rr_ratio=breakout.rr_ratio,
        vol_ratio=breakout.breakout_vol_ratio,
    )

    # 4. 진입 권고
    enriched.recommendation = score_to_recommendation(enriched.event_score)

    # 5. 근거 요약
    parts = []
    if enriched.earnings_quality == "CATALYST":
        parts.append("실적/이벤트 촉매 확인")
    elif enriched.earnings_quality == "NO_EVENT":
        parts.append("이벤트 없음 (순수 기술적)")
    if enriched.sector_summary:
        parts.append(enriched.sector_summary.event_summary)
    parts.append(f"R:R={breakout.rr_ratio:.1f}, Vol={breakout.breakout_vol_ratio:.1f}x")
    enriched.reason = " | ".join(parts)

    return enriched


def enrich_breakout_list(
    breakouts: list[BoxBreakout],
    sector_map: dict[str, str],
    fmp_api_key: str | None = None,
) -> list[EnrichedBreakout]:
    """
    여러 돌파 신호를 일괄 처리한다.

    Args:
        breakouts: BoxBreakout 리스트
        sector_map: {symbol: sector} 매핑
        fmp_api_key: FMP API Key (없으면 환경변수 FMP_API_KEY 사용)

    Returns:
        EnrichedBreakout 리스트 (점수 내림차순)
    """
    results = []
    for b in breakouts:
        sector = sector_map.get(b.symbol, "Unknown")
        enriched = enrich_breakout(b, sector, fmp_api_key=fmp_api_key)
        results.append(enriched)
        log.info(
            "[%s] event_score=%d recommendation=%s | %s",
            b.symbol, enriched.event_score,
            enriched.recommendation, enriched.reason,
        )

    return sorted(results, key=lambda e: e.event_score, reverse=True)


def format_enriched_report(enriched: EnrichedBreakout) -> str:
    """EnrichedBreakout 리포트 포맷."""
    b = enriched.breakout
    lines = [
        f"{'='*60}",
        f"[{b.symbol}] {b.breakout_date:%Y-%m-%d} | {enriched.recommendation} (score={enriched.event_score})",
        f"  Entry: ${b.breakout_price:.2f} | Stop: ${b.stop_loss:.2f} | Target: ${b.target_price:.2f}",
        f"  R:R={b.rr_ratio:.1f} | Vol={b.breakout_vol_ratio:.1f}x | Sector={enriched.sector}",
        f"  이벤트: {enriched.earnings_quality}",
        f"  근거: {enriched.reason}",
    ]
    if enriched.sector_summary:
        lines.append(format_event_summary(enriched.sector_summary))
    return "\n".join(lines)
