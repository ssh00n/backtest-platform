"""
박스 품질 스코어 (Box Quality Score)

핵심 아이디어: 기관이 조용히 포지션을 쌓는 패턴에는 구조적 특징이 있다.
  - 박스가 타이트함 (변동성 낮음) = 매집 과정의 정숙함
  - 박스 기간이 충분함 (최소 14일+) = 충분한 축적
  - 박스 내 거래량 후반부 증가 = 관심 증가 신호

L2 필터로 사용: quality_score >= min_score 인 돌파만 진입.
더 많은 데이터가 쌓여도 robust하게 작동하는 기준.

Breakout Quality (서브스코어 — Alpha 설계):
  - 갭업 페널티: 시가 > 전일 종가 * 1.03 → 이벤트/뉴스 반응 돌파 경고
  - 종가 위치: (종가-저가)/(고가-저가) > 0.7 → 강한 매수세 확인

Usage:
    from src.screener.box_quality import compute_box_quality, compute_breakout_quality
    from src.screener.darvas_box import DarvasBox, BoxBreakout

    quality = compute_box_quality(box, price_df)
    bq = compute_breakout_quality(breakout, price_df)
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from src.screener.darvas_box import DarvasBox


@dataclass
class BoxQuality:
    """박스 품질 평가 결과."""
    score: float                     # 0~100 종합 점수
    tightness_score: float           # 박스 타이트함 (0~40점)
    duration_score: float            # 박스 기간 (0~30점)
    vol_trend_score: float           # 거래량 추세 (0~30점)
    tightness_pct: float             # 실제 (high-low)/mid 값
    duration_days: int               # 박스 기간 (일)
    vol_trend_ratio: float           # 후반부/전반부 거래량 비율
    reasons: list[str] = field(default_factory=list)

    @property
    def grade(self) -> str:
        """A/B/C/D 등급."""
        if self.score >= 75:
            return "A"
        if self.score >= 55:
            return "B"
        if self.score >= 35:
            return "C"
        return "D"


def compute_box_quality(
    box: DarvasBox,
    price_df: pd.DataFrame | None = None,
) -> BoxQuality:
    """
    박스 품질 종합 평가.

    Args:
        box: DarvasBox 객체 (box_top, box_bottom, duration_days, avg_volume 포함)
        price_df: OHLCV DataFrame (DatetimeIndex). None이면 거래량 추세 스킵.

    Returns:
        BoxQuality (score 0~100)

    점수 구성:
        타이트함 (40점): 박스 높이 / 중심가격 → 낮을수록 고점
        기간    (30점): duration_days → 길수록 고점
        거래량   (30점): 박스 후반부 거래량 > 전반부 → 축적 신호
    """
    reasons: list[str] = []

    # ── 1. 타이트함 점수 (0~40) ─────────────────────────────
    box_mid = (box.box_top + box.box_bottom) / 2.0
    if box_mid <= 0:
        tightness_pct = 1.0
    else:
        tightness_pct = (box.box_top - box.box_bottom) / box_mid

    # 선형 스케일: 0% → 40점, 25%+ → 0점
    tightness_score = max(0.0, 40.0 * (1.0 - tightness_pct / 0.25))
    reasons.append(
        f"타이트함 {tightness_pct:.1%} → {tightness_score:.0f}/40점"
        + (" (타이트 ✅)" if tightness_pct < 0.12 else " (보통)" if tightness_pct < 0.20 else " (넓음 ⚠️)")
    )

    # ── 2. 기간 점수 (0~30) ──────────────────────────────────
    dur = box.duration_days
    if dur >= 30:
        duration_score = 30.0
    elif dur >= 14:
        duration_score = 15.0 + (dur - 14) / 16.0 * 15.0   # 14→15, 30→30
    elif dur >= 7:
        duration_score = 5.0 + (dur - 7) / 7.0 * 10.0      # 7→5, 14→15
    else:
        duration_score = 0.0
    reasons.append(
        f"기간 {dur}일 → {duration_score:.0f}/30점"
        + (" (충분 ✅)" if dur >= 14 else " (짧음 ⚠️)")
    )

    # ── 3. 거래량 추세 점수 (0~30) ───────────────────────────
    vol_trend_ratio = 1.0  # 기본값 (데이터 없으면 중립)
    vol_trend_score = 15.0

    if price_df is not None and not price_df.empty:
        try:
            box_data = price_df.loc[
                (price_df.index >= box.box_start) &
                (price_df.index <= box.box_end),
                "volume"
            ]
            if len(box_data) >= 6:
                half = len(box_data) // 2
                front_avg = box_data.iloc[:half].mean()
                back_avg  = box_data.iloc[half:].mean()
                vol_trend_ratio = back_avg / front_avg if front_avg > 0 else 1.0

                # 비율 1.0 = 중립(15점), 1.5+ = 30점, 0.5- = 0점
                vol_trend_score = max(0.0, min(30.0, 15.0 + (vol_trend_ratio - 1.0) * 30.0))
                reasons.append(
                    f"거래량 추세 {vol_trend_ratio:.2f}x (후반/전반) → {vol_trend_score:.0f}/30점"
                    + (" (축적 ✅)" if vol_trend_ratio >= 1.2 else " (분산 ⚠️)" if vol_trend_ratio < 0.8 else " (중립)")
                )
            else:
                reasons.append(f"거래량 데이터 부족 ({len(box_data)}일) → 중립 15점")
        except Exception as e:
            reasons.append(f"거래량 계산 오류: {e} → 중립 15점")
    else:
        reasons.append("price_df 없음 → 거래량 중립 15점")

    score = tightness_score + duration_score + vol_trend_score

    return BoxQuality(
        score=score,
        tightness_score=tightness_score,
        duration_score=duration_score,
        vol_trend_score=vol_trend_score,
        tightness_pct=tightness_pct,
        duration_days=dur,
        vol_trend_ratio=vol_trend_ratio,
        reasons=reasons,
    )


# ── Breakout Quality 서브스코어 (Alpha 설계) ──────────────────────────────

@dataclass
class BreakoutQuality:
    """돌파 품질 서브스코어 (0~20점)."""
    score: float              # 0~20 종합
    gap_score: float          # 0~10 (갭 없음 = 좋음)
    close_pos_score: float    # 0~10 (고가 근처 마감 = 좋음)
    gap_up_pct: float         # 갭업 비율 (0 = 갭 없음, 양수 = 갭업)
    close_position: float     # 종가 위치 0~1 (1 = 고가 마감)
    reasons: list[str] = field(default_factory=list)


def compute_breakout_quality(
    breakout,                         # BoxBreakout
    price_df: pd.DataFrame | None,
) -> BreakoutQuality:
    """
    돌파일 가격 행동 품질 계산 (20점 만점).

    [10pt] 갭업 페널티:
        갭 < 1%  → 10pt  (점진 돌파 — 기관 조용한 진입)
        갭 1~3%  →  6pt
        갭 3~5%  →  2pt
        갭 5%+   →  0pt  (이벤트/뉴스 반응 의심)

    [10pt] 종가 위치:
        (종가-저가)/(고가-저가) ≥ 0.7 → 10pt  (강한 매수세 마감)
        ≥ 0.5 →  6pt
        ≥ 0.3 →  3pt
        < 0.3 →  0pt  (약세 마감)

    Args:
        breakout: BoxBreakout 인스턴스
        price_df: OHLCV DataFrame (index=DatetimeIndex)

    Returns:
        BreakoutQuality
    """
    reasons: list[str] = []
    gap_up_pct    = 0.0
    close_position = 0.5
    gap_score      = 6.0   # 기본값 (price_df 없을 때)
    close_pos_score = 5.0  # 기본값

    if price_df is not None and not price_df.empty:
        bdate = breakout.breakout_date

        # 컬럼명 정규화
        col_map = {c.lower(): c for c in price_df.columns}
        def _col(name: str):
            return col_map.get(name, col_map.get(name.capitalize(), name))

        if bdate in price_df.index:
            row    = price_df.loc[bdate]
            open_p = float(row[_col("open")])
            high_p = float(row[_col("high")])
            low_p  = float(row[_col("low")])
            close_p = float(row[_col("close")])

            # 갭업: 오늘 시가 vs 박스 탑
            box_top = breakout.box.box_top
            gap_up_pct = max(0.0, (open_p - box_top) / box_top)

            # 종가 위치 (일봉 내)
            day_range = high_p - low_p
            close_position = (close_p - low_p) / day_range if day_range > 0 else 0.5

    # 갭업 점수
    if gap_up_pct < 0.01:
        gap_score = 10.0
        reasons.append(f"점진 돌파 (갭 {gap_up_pct:.1%}) ✅")
    elif gap_up_pct < 0.03:
        gap_score = 6.0
        reasons.append(f"소폭 갭업 ({gap_up_pct:.1%})")
    elif gap_up_pct < 0.05:
        gap_score = 2.0
        reasons.append(f"갭업 주의 ({gap_up_pct:.1%}) ⚠️")
    else:
        gap_score = 0.0
        reasons.append(f"대형 갭업 ({gap_up_pct:.1%}) ⛔ 이벤트 반응 의심")

    # 종가 위치 점수 (Alpha 기준: 0.7+)
    if close_position >= 0.7:
        close_pos_score = 10.0
        reasons.append(f"고가 근처 마감 ({close_position:.0%}) ✅ 강한 매수세")
    elif close_position >= 0.5:
        close_pos_score = 6.0
        reasons.append(f"중립 마감 ({close_position:.0%})")
    elif close_position >= 0.3:
        close_pos_score = 3.0
        reasons.append(f"약세 마감 ({close_position:.0%}) ⚠️")
    else:
        close_pos_score = 0.0
        reasons.append(f"저가 마감 ({close_position:.0%}) ⛔")

    return BreakoutQuality(
        score=gap_score + close_pos_score,
        gap_score=gap_score,
        close_pos_score=close_pos_score,
        gap_up_pct=gap_up_pct,
        close_position=close_position,
        reasons=reasons,
    )


# ── 이벤트 타이밍 필터 (L3 개선) ──────────────────────────────────────────

def check_event_timing(
    symbol: str,
    entry_date: pd.Timestamp,
    window_days: int = 7,
    fail_open: bool = True,
) -> tuple[bool, str]:
    """
    돌파 직전 N일 이내 EARNINGS 이벤트 유무 체크 (타이밍 기반).

    이벤트 존재 자체가 아닌 '직전 타이밍'만 차단.
    → 오래 전 이벤트(PF 무관)는 허용, 최근 이벤트만 차단.

    Args:
        symbol: 종목 심볼
        entry_date: 돌파(진입) 날짜
        window_days: 직전 차단 일수 (기본 7일)
        fail_open: API 실패 시 통과(True) / 차단(False)

    Returns:
        (allow: bool, reason: str)
    """
    try:
        from src.events.earnings_calendar import find_events_near_breakout

        events = find_events_near_breakout(
            symbol, entry_date,
            window_before=window_days,
            window_after=0,  # 미래 이벤트는 관계없음
        )
        earnings = [
            e for e in events
            if e.event_type == "EARNINGS" and e.days_from_breakout <= 0
        ]
        if earnings:
            ev = min(earnings, key=lambda e: abs(e.days_from_breakout))
            return False, (
                f"어닝 직전 차단 (delta={ev.days_from_breakout}d, "
                f"{'BEAT' if ev.beat else 'MISS' if ev.beat is False else '?'})"
            )
        return True, "직전 어닝 없음 — 통과"

    except Exception as e:
        return fail_open, f"API 실패({'통과' if fail_open else '차단'}): {e}"
