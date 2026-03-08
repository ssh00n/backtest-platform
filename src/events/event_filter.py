"""
이벤트 기반 진입 필터 (v3 — 승훈 전략 방향)

핵심 인사이트:
    이벤트 반응 예측 = 불확실성 ↑
    NO_EVENT (순수 기술적 돌파)가 WR/PF 모두 압도적으로 우수
    → 이벤트 근처 진입 차단이 성과 개선에 도움

모드별 동작:
    no_event_only   — 이벤트 없는 종목만 진입 (권장)
    miss_block      — EARNINGS_MISS만 차단
    earnings_block  — 어닝 근처 전부 차단
    none            — 필터 없음
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.backtest.portfolio import BacktestConfig

log = logging.getLogger(__name__)


@dataclass
class EventFilterResult:
    """이벤트 필터 결과."""
    allow: bool                      # 진입 허용 여부
    quality: str                     # "NO_EVENT" | "EARNINGS_BEAT" | "EARNINGS_MISS" | "CATALYST" | "ERROR"
    reason: str                      # 차단/허용 이유
    delta_days: int | None = None    # 이벤트 날짜 기준 상대 일수 (음수=돌파 이전)


def check_event_filter(
    symbol: str,
    entry_date: pd.Timestamp,
    config: "BacktestConfig",
) -> EventFilterResult:
    """
    이벤트 필터 체크 — engine.py _scan_entries에서 호출.

    Args:
        symbol: 종목 심볼
        entry_date: 돌파(진입) 날짜
        config: BacktestConfig (event_filter_mode, event_window_* 포함)

    Returns:
        EventFilterResult (allow=False면 진입 차단)

    Usage (engine.py):
        from src.events.event_filter import check_event_filter

        if config.use_events:
            result = check_event_filter(symbol, today, config)
            if not result.allow:
                log.debug("[EVENT BLOCK] %s: %s", symbol, result.reason)
                continue
    """
    mode = getattr(config, "event_filter_mode", "none")

    # 필터 없음 — 바로 통과
    if mode == "none":
        return EventFilterResult(allow=True, quality="NO_EVENT", reason="필터 없음")

    # 이벤트 조회
    try:
        from src.events.earnings_calendar import find_events_near_breakout

        events = find_events_near_breakout(
            symbol, entry_date,
            window_before=getattr(config, "event_window_before", 7),
            window_after=getattr(config, "event_window_after", 3),
        )
    except Exception as e:
        log.debug("이벤트 조회 실패 [%s]: %s", symbol, e)
        fail_open = getattr(config, "event_fail_open", True)
        quality = "ERROR"
        return EventFilterResult(
            allow=fail_open,
            quality=quality,
            reason=f"API 실패({'통과' if fail_open else '차단'}): {e}",
        )

    # 이벤트 없음 → 항상 통과
    earnings = [e for e in events if e.event_type == "EARNINGS"]
    catalysts = [e for e in events if e.event_type in ("8-K", "CATALYST")]

    if not events:
        return EventFilterResult(allow=True, quality="NO_EVENT", reason="이벤트 없음 — 순수 기술적 돌파")

    # ── 모드별 판단 ─────────────────────────────────────────

    if mode == "no_event_only":
        # 이벤트 있으면 전부 차단 (NO_EVENT만 통과)
        all_events = earnings or catalysts
        if not all_events:
            return EventFilterResult(allow=True, quality="NO_EVENT", reason="이벤트 없음 — 순수 기술적 돌파")
        ev = all_events[0]
        quality = _classify_quality(ev)
        return EventFilterResult(
            allow=False,
            quality=quality,
            reason=f"이벤트 근처 차단 ({quality}, delta={ev.days_from_breakout}d) — no_event_only 모드",
            delta_days=ev.days_from_breakout,
        )

    if mode == "miss_block":
        # EARNINGS_MISS만 차단
        for ev in earnings:
            if ev.beat is False:
                return EventFilterResult(
                    allow=False,
                    quality="EARNINGS_MISS",
                    reason=f"EARNINGS_MISS 차단 (delta={ev.days_from_breakout}d, EPS={ev.eps_actual} vs {ev.eps_estimate})",
                    delta_days=ev.days_from_breakout,
                )
        # 그 외 통과
        quality = _classify_quality((earnings or catalysts or [None])[0]) if events else "NO_EVENT"
        return EventFilterResult(allow=True, quality=quality, reason="MISS 없음 — 통과")

    if mode == "earnings_block":
        # 어닝 이벤트 근처 전부 차단 (8-K CATALYST는 허용)
        if earnings:
            ev = earnings[0]
            quality = _classify_quality(ev)
            return EventFilterResult(
                allow=False,
                quality=quality,
                reason=f"어닝 근처 차단 ({quality}, delta={ev.days_from_breakout}d)",
                delta_days=ev.days_from_breakout,
            )
        # 8-K만 있으면 통과
        return EventFilterResult(allow=True, quality="CATALYST", reason="어닝 없음, 8-K만 — 통과")

    # 알 수 없는 모드 → 통과
    return EventFilterResult(allow=True, quality="UNKNOWN", reason=f"알 수 없는 모드: {mode}")


def _classify_quality(ev) -> str:
    """EarningsEvent → 품질 문자열."""
    if ev is None:
        return "NO_EVENT"
    if ev.event_type == "EARNINGS":
        if ev.beat is True:
            return "EARNINGS_BEAT"
        if ev.beat is False:
            return "EARNINGS_MISS"
        return "EARNINGS"
    return "CATALYST"
