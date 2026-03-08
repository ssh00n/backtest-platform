"""
이벤트 분석 모듈 (Event Analysis)

Darvas Box 돌파 신호에 이벤트 컨텍스트를 결합하여
'시간의 압축 지점(이벤트)에서만 집행'하는 원칙을 구현한다.

주요 모듈:
  - earnings_calendar: SEC EDGAR + Alpaca로 실적 이벤트 수집
  - news_crawler: 종목/섹터/매크로 뉴스 수집
  - event_matcher: 돌파 신호와 이벤트 결합 → 진입 점수 계산
"""

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
from src.events.event_matcher import (
    EnrichedBreakout,
    enrich_breakout,
    enrich_breakout_list,
    format_enriched_report,
)

__all__ = [
    "EarningsEvent",
    "find_events_near_breakout",
    "classify_event_quality",
    "SectorEventSummary",
    "build_sector_event_summary",
    "format_event_summary",
    "EnrichedBreakout",
    "enrich_breakout",
    "enrich_breakout_list",
    "format_enriched_report",
]
