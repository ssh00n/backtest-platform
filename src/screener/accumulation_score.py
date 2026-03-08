"""
Accumulation Quality Score — 기관 축적 패턴 종합 점수

"이벤트 없음" 소극적 필터 대신, 박스 돌파의 본질(기관 조용한 축적)을 직접 점수화.

총점 구조 (100점 + 보너스):
  [40pt] Volume Profile  — 박스 내 거래량 점진 증가 + 돌파 거래량 강도
  [30pt] Box Quality     — 타이트함 + 기간 충분 (기관 축적 시간)
  [20pt] Price Action    — 갭업 페널티 + 종가 위치 (건강한 돌파 패턴)
  [10pt] Event Score     — 이벤트 페널티/보너스 (이벤트 불확실성 반영)

Alpha 설계 기반, Beta 구현.
기존 box_quality.py와 병행 사용 (box_quality는 단독 필터용으로 유지).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

log = logging.getLogger(__name__)


class AccumulationGrade(str, Enum):
    A_PLUS = "A+"   # 90+: 완벽한 기관 축적 패턴 (풀 사이즈 1R)
    A      = "A"    # 80+: 강한 축적 신호 (풀 사이즈 1R)
    B      = "B"    # 65+: 양호한 축적 (70% 사이즈 0.7R)
    C      = "C"    # 50+: 보통, 진입 가능 (50% 사이즈 0.5R)
    D      = "D"    # 50미만: 차단


@dataclass
class AccumulationScore:
    """Accumulation Quality Score 결과."""

    # 총점
    score: float           # 0~110 (이벤트 보너스 포함 가능)
    grade: AccumulationGrade

    # 세부 점수 (만점 기준)
    vol_profile_score: float    # /40
    box_quality_score: float    # /30
    price_action_score: float   # /20
    event_score: float          # /10 (보너스/페널티, 범위 -20~+10)

    # 세부 지표
    vol_trend_ratio: float      # 박스 후반/전반 거래량 비율
    breakout_vol_ratio: float   # 돌파일 거래량 / 박스 평균
    box_tightness_pct: float    # 박스 범위 / 중간가 (낮을수록 좋음)
    box_duration_days: int
    gap_up_pct: float           # 갭업 비율 (양수 = 갭업)
    close_position: float       # 종가 위치 (0=저가, 1=고가)
    event_type: str             # 감지된 이벤트 유형

    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def pass_filter(self) -> bool:
        return self.grade not in (AccumulationGrade.D,)


def compute_accumulation_score(
    breakout,                        # BoxBreakout
    price_df: pd.DataFrame | None,   # OHLCV DataFrame (index=date)
    event_type: str = "NONE",        # "EARNINGS_BEAT/MISS/CATALYST/NO_EVENT/..."
    min_score: float = 50.0,
) -> AccumulationScore:
    """
    BoxBreakout 데이터로 Accumulation Quality Score 계산.

    Args:
        breakout: BoxBreakout 인스턴스
        price_df: OHLCV DataFrame (index=DatetimeIndex, cols=open/high/low/close/volume)
        event_type: 이벤트 유형 문자열 (event_filter에서 조회)
        min_score: 필터 기준 (기본 50점)

    Returns:
        AccumulationScore
    """
    box = breakout.box
    reasons: list[str] = []
    warnings: list[str] = []

    # ── 1. Volume Profile (40pt) ─────────────────────────────────────────────
    vol_profile_score = 0.0
    vol_trend_ratio   = 1.0
    breakout_vol_ratio = getattr(breakout, "breakout_vol_ratio", 1.0)

    if price_df is not None and not price_df.empty:
        # 박스 기간 슬라이스
        box_data = price_df[
            (price_df.index >= box.box_start) &
            (price_df.index <= box.box_end)
        ].copy()

        if len(box_data) >= 4:
            mid = len(box_data) // 2
            front_vol = box_data["volume"].iloc[:mid].mean()
            back_vol  = box_data["volume"].iloc[mid:].mean()

            if front_vol > 0:
                vol_trend_ratio = back_vol / front_vol
            else:
                vol_trend_ratio = 1.0

            # 점진 증가 (후반 거래량 > 전반): 최대 20pt
            if vol_trend_ratio >= 1.5:
                vol_profile_score += 20
                reasons.append(f"거래량 점진 증가 1.5x+ ({vol_trend_ratio:.2f}x)")
            elif vol_trend_ratio >= 1.2:
                vol_profile_score += 14
                reasons.append(f"거래량 점진 증가 1.2x+ ({vol_trend_ratio:.2f}x)")
            elif vol_trend_ratio >= 1.0:
                vol_profile_score += 8
            else:
                warnings.append(f"거래량 감소 추세 ({vol_trend_ratio:.2f}x)")
        else:
            vol_trend_ratio = 1.0
    else:
        # price_df 없으면 vol_sma 기반으로 추정
        vol_trend_ratio = 1.0

    # 돌파일 거래량 강도: 최대 20pt
    if breakout_vol_ratio >= 3.0:
        vol_profile_score += 20
        reasons.append(f"돌파 거래량 3.0x+ ({breakout_vol_ratio:.1f}x)")
    elif breakout_vol_ratio >= 2.0:
        vol_profile_score += 15
        reasons.append(f"돌파 거래량 2.0x+ ({breakout_vol_ratio:.1f}x)")
    elif breakout_vol_ratio >= 1.5:
        vol_profile_score += 10
    else:
        warnings.append(f"돌파 거래량 약함 ({breakout_vol_ratio:.1f}x)")

    # ── 2. Box Quality (30pt) ────────────────────────────────────────────────
    box_quality_score = 0.0
    mid_price = (box.box_top + box.box_bottom) / 2
    if mid_price <= 0:
        mid_price = 1.0
    tightness_pct = box.box_height / mid_price
    duration_days = box.duration_days

    # 타이트함 (15pt): 박스가 좁을수록 압축 = 축적
    if tightness_pct < 0.06:
        box_quality_score += 15
        reasons.append(f"타이트 박스 {tightness_pct*100:.1f}% (6% 미만)")
    elif tightness_pct < 0.09:
        box_quality_score += 12
        reasons.append(f"박스 타이트 {tightness_pct*100:.1f}%")
    elif tightness_pct < 0.12:
        box_quality_score += 8
    elif tightness_pct < 0.15:
        box_quality_score += 4
    else:
        warnings.append(f"박스 넓음 {tightness_pct*100:.1f}% (15%+)")

    # 기간 (15pt): 긴 압축 = 더 강한 축적
    if duration_days >= 21:
        box_quality_score += 15
        reasons.append(f"장기 축적 {duration_days}일 (21일+)")
    elif duration_days >= 14:
        box_quality_score += 12
        reasons.append(f"충분한 축적 {duration_days}일")
    elif duration_days >= 10:
        box_quality_score += 7
    else:
        warnings.append(f"단기 박스 {duration_days}일 (10일 미만)")

    # ── 3. Price Action (20pt) ───────────────────────────────────────────────
    price_action_score = 0.0
    gap_up_pct    = 0.0
    close_position = 0.5  # 기본값

    if price_df is not None and not price_df.empty:
        bdate = breakout.breakout_date
        # 돌파일 데이터
        if bdate in price_df.index:
            row = price_df.loc[bdate]
            open_p  = float(row.get("open",  row.get("Open",  breakout.breakout_price)))
            high_p  = float(row.get("high",  row.get("High",  breakout.breakout_price)))
            low_p   = float(row.get("low",   row.get("Low",   breakout.breakout_price)))
            close_p = float(row.get("close", row.get("Close", breakout.breakout_price)))

            # 갭업 = 오늘 시가 > 어제 박스 탑
            gap_up_pct = max(0, (open_p - box.box_top) / box.box_top)

            # 종가 위치 (일봉 내 위치)
            day_range = high_p - low_p
            close_position = (close_p - low_p) / day_range if day_range > 0 else 0.5
        else:
            # 날짜 없으면 종가로 추정
            close_p = breakout.breakout_price
            gap_up_pct = max(0, (close_p - box.box_top) / box.box_top)
            close_position = 0.5

    # 갭업 페널티 (클수록 낮은 점수, 최대 0pt)
    if gap_up_pct < 0.01:
        price_action_score += 10  # 갭 없음 = 점진적 돌파 ✅
        reasons.append("갭없는 점진 돌파")
    elif gap_up_pct < 0.03:
        price_action_score += 6   # 소폭 갭
    elif gap_up_pct < 0.05:
        price_action_score += 2   # 중간 갭
    else:
        price_action_score += 0   # 대형 갭업 = 오버슈트 위험
        warnings.append(f"갭업 {gap_up_pct*100:.1f}% (trailing stop 위험)")

    # 종가 위치 (10pt): 고가 근처 마감 = 강한 수요
    if close_position >= 0.8:
        price_action_score += 10
        reasons.append(f"고가 근처 마감 ({close_position:.0%})")
    elif close_position >= 0.6:
        price_action_score += 7
    elif close_position >= 0.4:
        price_action_score += 4
    else:
        warnings.append(f"저가 근처 마감 ({close_position:.0%})")

    # ── 4. Event Score (10pt 기준, 범위 -20~+10) ────────────────────────────
    event_score = 0.0
    et = (event_type or "NONE").upper()

    if "MISS" in et or "EARNINGS_MISS" in et:
        event_score = -20
        warnings.append("어닝 미스 감지 (-20pt, 차단 권장)")
    elif "BEAT" in et or "EARNINGS_BEAT" in et:
        event_score = -10
        warnings.append("어닝 비트 감지 (-10pt, 'sell the news' 위험)")
    elif "EARNINGS" in et and "NO" not in et:
        event_score = -10
        warnings.append("어닝 근처 진입 (-10pt, 불확실성)")
    elif "CATALYST" in et:
        event_score = -5
        warnings.append("8-K 이벤트 감지 (-5pt)")
    elif et in ("NO_EVENT", "NONE", ""):
        event_score = +10
        reasons.append("이벤트 없음 (+10pt 보너스)")

    # ── 총점 & 등급 ──────────────────────────────────────────────────────────
    total = vol_profile_score + box_quality_score + price_action_score + event_score
    total = max(0.0, total)  # 음수 방지

    # Alpha 엔진 기준: A+/A(80+) / B(65+) / C(50+) / D(<50)
    if total >= 90:
        grade = AccumulationGrade.A_PLUS
    elif total >= 80:
        grade = AccumulationGrade.A
    elif total >= 65:
        grade = AccumulationGrade.B
    elif total >= 50:
        grade = AccumulationGrade.C
    else:
        grade = AccumulationGrade.D

    return AccumulationScore(
        score=round(total, 1),
        grade=grade,
        vol_profile_score=round(vol_profile_score, 1),
        box_quality_score=round(box_quality_score, 1),
        price_action_score=round(price_action_score, 1),
        event_score=round(event_score, 1),
        vol_trend_ratio=round(vol_trend_ratio, 3),
        breakout_vol_ratio=round(breakout_vol_ratio, 2),
        box_tightness_pct=round(tightness_pct, 4),
        box_duration_days=duration_days,
        gap_up_pct=round(gap_up_pct, 4),
        close_position=round(close_position, 3),
        event_type=et,
        reasons=reasons,
        warnings=warnings,
    )


# ── 포지션 사이징 매핑 ───────────────────────────────────────────────────────

# 등급별 포지션 비율 (base_size 대비)
# v2: C/B 상향 — 사이징 축소가 수익도 선형 축소하는 문제 완화
_GRADE_SIZE_MAP: dict[AccumulationGrade, float] = {
    AccumulationGrade.A_PLUS: 1.00,   # 풀 사이즈 — 완벽한 기관 축적
    AccumulationGrade.A:      1.00,   # 풀 사이즈 — 강한 축적
    AccumulationGrade.B:      0.85,   # 85% — 양호 (기존 70% → 상향)
    AccumulationGrade.C:      0.70,   # 70% — 진입 허용 (기존 50% → 상향)
    AccumulationGrade.D:      0.00,   # 차단
}


def get_position_size_ratio(
    score: AccumulationScore,
    block_on_d: bool = True,
    block_on_miss: bool = True,
    d_fallback_ratio: float = 0.50,
) -> float:
    """
    AccumulationScore 등급에 따른 포지션 비율 반환.

    Args:
        score: AccumulationScore 인스턴스
        block_on_d: True → D등급 차단(0.0) / False → d_fallback_ratio 적용
        block_on_miss: True → EARNINGS_MISS 무조건 차단 (기본 유지)
        d_fallback_ratio: block_on_d=False 시 D등급 비율 (기본 0.5)

    Returns:
        float: 0.0 ~ 1.0

    사용 예시:
        # 모드 1: D 차단 + 사이징 (기본)
        ratio = get_position_size_ratio(score)

        # 모드 2: miss_block + ACC 사이징만 (차단 없이)
        ratio = get_position_size_ratio(score, block_on_d=False, d_fallback_ratio=0.5)
    """
    # MISS는 설정과 무관하게 항상 차단
    if block_on_miss and "MISS" in score.event_type.upper():
        return 0.0

    if score.grade == AccumulationGrade.D:
        return 0.0 if block_on_d else d_fallback_ratio

    return _GRADE_SIZE_MAP.get(score.grade, 0.0)


def get_position_size(
    score: AccumulationScore,
    base_contracts: int = 1,
    min_contracts: int = 1,
) -> int:
    """
    포지션 계약 수 반환 (최소 1계약 보장, D등급은 0).

    Args:
        score: AccumulationScore
        base_contracts: 기준 계약 수 (기본 1)
        min_contracts: 최소 계약 수 (기본 1, D는 예외)

    Returns:
        int: 계약 수 (0 = 진입 없음)
    """
    ratio = get_position_size_ratio(score)
    if ratio == 0.0:
        return 0
    contracts = max(min_contracts, round(base_contracts * ratio))
    return contracts


def sizing_summary(score: AccumulationScore, base_contracts: int = 1) -> str:
    """포지션 사이징 한 줄 요약."""
    ratio = get_position_size_ratio(score)
    size  = get_position_size(score, base_contracts)
    pct   = int(ratio * 100)
    if ratio == 0.0:
        reason = "EARNINGS_MISS" if "MISS" in score.event_type.upper() else "D등급 (품질 미달)"
        return f"[{score.grade.value}] ⛔ 차단 ({reason})"
    return f"[{score.grade.value}] {pct}% 사이즈 ({size}/{base_contracts}계약) | {score.score:.0f}pt"


def score_summary(s: AccumulationScore) -> str:
    """한 줄 요약 문자열."""
    return (
        f"[{s.grade.value}] {s.score:.0f}pt | "
        f"Vol:{s.vol_profile_score:.0f}/40 Box:{s.box_quality_score:.0f}/30 "
        f"PA:{s.price_action_score:.0f}/20 Evt:{s.event_score:+.0f} | "
        f"Tight:{s.box_tightness_pct*100:.1f}% {s.box_duration_days}d "
        f"BreakVol:{s.breakout_vol_ratio:.1f}x"
    )


# ── 백테스트 통합용 ──────────────────────────────────────────────────────────

def score_from_trade(trade: dict, price_cache: dict | None = None) -> AccumulationScore | None:
    """
    백테스트 trade dict에서 AccumulationScore 계산.
    trade 키: symbol, entry_date, breakout_vol_ratio, box_*, event_type 등

    Args:
        trade: 백테스트 거래 결과 dict
        price_cache: {symbol: DataFrame} 캐시 (없으면 vol/price 추정)
    """
    try:
        from src.screener.darvas_box import DarvasBox, BoxBreakout
        import pandas as pd

        box = DarvasBox(
            box_top       = trade.get("box_top", 0),
            box_bottom    = trade.get("box_bottom", 0),
            box_height    = trade.get("box_height", 0),
            box_start     = pd.Timestamp(trade.get("box_start", trade.get("entry_date", "2020-01-01"))),
            box_end       = pd.Timestamp(trade.get("entry_date", "2020-01-01")),
            duration_days = trade.get("box_duration", trade.get("duration_days", 10)),
            avg_volume    = trade.get("avg_volume", 1e6),
            vol_sma_20    = trade.get("vol_sma_20", 1e6),
        )
        breakout = BoxBreakout(
            symbol             = trade.get("symbol", ""),
            box                = box,
            breakout_date      = pd.Timestamp(trade.get("entry_date", "2020-01-01")),
            breakout_price     = trade.get("entry_price", 0),
            breakout_vol_ratio = trade.get("breakout_vol_ratio", trade.get("vol_ratio", 1.0)),
            stop_loss          = trade.get("stop_loss", 0),
            risk_r             = trade.get("risk_r", 1.0),
            target_price       = trade.get("target_price", 0),
            reward             = trade.get("reward", 0),
            rr_ratio           = trade.get("rr_ratio", 0),
            rr_pass            = True,
        )
        price_df = price_cache.get(trade["symbol"]) if price_cache else None
        event_type = trade.get("event_type", "NONE")

        return compute_accumulation_score(breakout, price_df, event_type=event_type)

    except Exception as e:
        log.debug("score_from_trade 실패: %s", e)
        return None


if __name__ == "__main__":
    """간단한 동작 테스트."""
    import sys
    sys.path.insert(0, ".")
    from src.screener.darvas_box import DarvasBox, BoxBreakout

    # 테스트 케이스 1: 완벽한 기관 축적 패턴
    box_good = DarvasBox(
        box_top=105, box_bottom=98, box_height=7,
        box_start=pd.Timestamp("2024-01-01"),
        box_end=pd.Timestamp("2024-01-22"),
        duration_days=21, avg_volume=1_500_000, vol_sma_20=1_200_000,
    )
    breakout_good = BoxBreakout(
        symbol="TEST", box=box_good,
        breakout_date=pd.Timestamp("2024-01-23"),
        breakout_price=106.0, breakout_vol_ratio=2.8,
        stop_loss=103.25, risk_r=2.75,
        target_price=115.0, reward=9.0, rr_ratio=3.27, rr_pass=True,
    )

    s1 = compute_accumulation_score(breakout_good, None, event_type="NO_EVENT")
    print("=== 케이스 1: 완벽한 축적 패턴 ===")
    print(score_summary(s1))
    print(sizing_summary(s1, base_contracts=5))
    print(f"  이유: {s1.reasons}")
    print(f"  경고: {s1.warnings}")

    # 테스트 케이스 2: 어닝 비트 + 넓은 박스 + 갭업
    box_bad = DarvasBox(
        box_top=120, box_bottom=96, box_height=24,
        box_start=pd.Timestamp("2024-03-01"),
        box_end=pd.Timestamp("2024-03-06"),
        duration_days=5, avg_volume=800_000, vol_sma_20=1_200_000,
    )
    breakout_bad = BoxBreakout(
        symbol="BAD", box=box_bad,
        breakout_date=pd.Timestamp("2024-03-07"),
        breakout_price=128.0, breakout_vol_ratio=1.3,  # 갭업
        stop_loss=114.0, risk_r=14.0,
        target_price=138.0, reward=10.0, rr_ratio=0.71, rr_pass=False,
    )

    s2 = compute_accumulation_score(breakout_bad, None, event_type="EARNINGS_BEAT")
    print("\n=== 케이스 2: 어닝 비트 + 넓은 박스 ===")
    print(score_summary(s2))
    print(sizing_summary(s2, base_contracts=5))
    print(f"  이유: {s2.reasons}")
    print(f"  경고: {s2.warnings}")

    # 케이스 3: CATALYST + 괜찮은 박스 (B등급 → 70%)
    box_mid = DarvasBox(
        box_top=52, box_bottom=47, box_height=5,
        box_start=pd.Timestamp("2024-05-01"),
        box_end=pd.Timestamp("2024-05-15"),
        duration_days=14, avg_volume=900_000, vol_sma_20=800_000,
    )
    breakout_mid = BoxBreakout(
        symbol="MID", box=box_mid,
        breakout_date=pd.Timestamp("2024-05-16"),
        breakout_price=52.5, breakout_vol_ratio=2.1,
        stop_loss=50.75, risk_r=1.75,
        target_price=58.0, reward=5.5, rr_ratio=3.14, rr_pass=True,
    )
    s3 = compute_accumulation_score(breakout_mid, None, event_type="CATALYST")
    print("\n=== 케이스 3: CATALYST + 적당한 박스 ===")
    print(score_summary(s3))
    print(sizing_summary(s3, base_contracts=5))

    # 케이스 4: EARNINGS_MISS → 차단
    s4 = compute_accumulation_score(breakout_good, None, event_type="EARNINGS_MISS")
    print("\n=== 케이스 4: EARNINGS_MISS (차단) ===")
    print(score_summary(s4))
    print(sizing_summary(s4, base_contracts=5))
