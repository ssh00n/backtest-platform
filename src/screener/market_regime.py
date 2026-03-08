"""
시장 국면 판단 (Market Regime Protocol)

protocol: docs/protocols/market-regime.md

SPY vs SMA(200), VIX, Market Breadth 기반으로
Bull / Sideways / Bear 국면을 분류하고 파라미터 프리셋을 반환한다.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ── 국면별 파라미터 프리셋 ────────────────────────────────────

REGIME_PARAMS = {
    "BULL": {
        "deep_discount_threshold": -0.20,
        "confirmation_vol_ratio": 1.5,
        "box_min_days": 7,
        "box_max_width_pct": 0.20,
        "breakout_vol_ratio": 1.5,
        "time_stop_days": 30,
        "partial_exit_pct": None,  # Bull: 부분 익절 없음
        # 거래량 프로토콜 국면별 임계값
        "vol_accumulation_ratio": 1.5,
        "vol_confirmation_ratio": 1.5,
    },
    "SIDEWAYS": {
        "deep_discount_threshold": -0.30,
        "confirmation_vol_ratio": 2.0,
        "box_min_days": 10,
        "box_max_width_pct": 0.15,
        "breakout_vol_ratio": 2.0,
        "time_stop_days": 20,
        "partial_exit_pct": 0.20,  # Sideways: +20% 도달 시 50% 익절
        "vol_accumulation_ratio": 1.5,
        "vol_confirmation_ratio": 2.0,
    },
    "BEAR": {
        "deep_discount_threshold": -0.40,
        "confirmation_vol_ratio": 3.0,
        "box_min_days": 15,
        "box_max_width_pct": 0.10,
        "breakout_vol_ratio": 3.0,
        "time_stop_days": 15,
        "partial_exit_pct": 0.15,  # Bear: +15% 도달 시 50% 익절
        "vol_accumulation_ratio": 2.0,
        "vol_confirmation_ratio": 3.0,
    },
}


@dataclass
class MarketRegime:
    regime: str  # "BULL" | "SIDEWAYS" | "BEAR"
    spy_price: float
    sma_200: float
    sma_200_slope: float  # 20일 전 대비 변화율
    vix: float | None
    breadth_pct: float | None  # 50일선 위 종목 비율
    bear_exit_conditions_met: int  # 0~3
    params: dict


# ── 핵심 함수 ─────────────────────────────────────────────


def compute_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=window).mean()


def _check_selling_exhaustion(spy_df: pd.DataFrame, window: int = 20) -> bool:
    """
    Bear 탈출 조건 3: 거래량 구조 신호 (매도 소진) 자동 탐지.

    두 가지 패턴을 동시에 확인한다:
    1. 수평 횡보 + 거래량 유지/증가 (매물 소화)
    2. 하락일 거래량이 점진적으로 감소 (매도 에너지 고갈)

    Args:
        spy_df: SPY OHLCV DataFrame
        window: 분석 윈도우 (기본 20거래일)
    """
    if len(spy_df) < window + 10:
        return False

    recent = spy_df.iloc[-window:]
    close = recent["close"]
    volume = recent["volume"]

    # 1) 횡보 확인: 최근 window일의 가격 변동폭이 좁은가
    price_range = (close.max() - close.min()) / close.mean()
    is_sideways = price_range < 0.08  # 8% 이내 변동

    # 2) 거래량 유지/증가: 최근 window일 평균 >= 직전 window일 평균
    if len(spy_df) < window * 2 + 10:
        vol_maintained = True  # 데이터 부족 시 조건 생략
    else:
        prev_vol = spy_df["volume"].iloc[-(window * 2):-window].mean()
        curr_vol = volume.mean()
        vol_maintained = curr_vol >= prev_vol * 0.9

    # 3) 하락일 거래량 감소 추세
    daily_returns = close.pct_change()
    down_days = recent[daily_returns < 0]

    if len(down_days) < 4:
        declining_down_vol = True  # 하락일이 거의 없음 = 매도 소진
    else:
        down_vols = down_days["volume"].values
        half = len(down_vols) // 2
        first_half_avg = float(np.mean(down_vols[:half]))
        second_half_avg = float(np.mean(down_vols[half:]))
        declining_down_vol = second_half_avg < first_half_avg * 0.85

    return is_sideways and vol_maintained and declining_down_vol


def classify_regime(
    spy_df: pd.DataFrame,
    vix_df: pd.DataFrame | None = None,
    breadth_pct: float | None = None,
    bear_exit_overrides: dict[int, bool] | None = None,
) -> MarketRegime:
    """
    SPY 일봉 데이터를 기반으로 시장 국면을 판단한다.

    Args:
        spy_df: SPY OHLCV (DatetimeIndex, columns: open/high/low/close/volume)
        vix_df: VIX 일봉 (optional, columns: close). None이면 VIX 판단 스킵.
        breadth_pct: 50일선 위 종목 비율 (0~1). None이면 breadth 판단 스킵.
        bear_exit_overrides: Bear 탈출 조건 수동 충족 (예: {1: True, 2: True}).
            키: 조건 번호 (1=Macro 기대 변화, 2=시장 반응 변화, 3=거래량 구조 신호)
            값: True이면 해당 조건 수동 충족

    Returns:
        MarketRegime dataclass
    """
    if len(spy_df) < 220:
        raise ValueError(f"SPY data too short ({len(spy_df)} rows, need >=220)")

    spy_close = spy_df["close"]
    sma_200 = compute_sma(spy_close, 200)

    latest_price = float(spy_close.iloc[-1])
    latest_sma = float(sma_200.iloc[-1])
    sma_20d_ago = float(sma_200.iloc[-20]) if len(sma_200) >= 20 else latest_sma
    sma_slope = (latest_sma - sma_20d_ago) / sma_20d_ago  # SMA(200) 기울기

    # VIX
    vix_value = None
    if vix_df is not None and not vix_df.empty:
        vix_value = float(vix_df["close"].iloc[-1])

    # ── 국면 판정 로직 (프로토콜 조건식 우선, 점수 기반 fallback) ──

    price_above_sma = latest_price > latest_sma
    pct_from_sma = (latest_price - latest_sma) / latest_sma

    # 프로토콜 조건식 기반 판정 (market-regime.md 참조)
    # Bull: SPY > SMA200 AND slope > 0 AND (breadth > 60% OR vix < 20)
    bull_condition = (
        price_above_sma
        and sma_slope > 0
        and (
            (breadth_pct is not None and breadth_pct > 0.60)
            or (vix_value is not None and vix_value < 20)
        )
    )

    # Bear: SPY < SMA200 AND slope < 0 AND (breadth < 40% OR vix > 25)
    bear_condition = (
        not price_above_sma
        and sma_slope < 0
        and (
            (breadth_pct is not None and breadth_pct < 0.40)
            or (vix_value is not None and vix_value > 25)
        )
    )

    # Sideways: abs(pct_from_sma) < 3% AND abs(slope) < 0.5%
    sideways_condition = abs(pct_from_sma) < 0.03 and abs(sma_slope) < 0.005

    # 조건식 기반 판정
    regime = None
    if bull_condition:
        regime = "BULL"
    elif bear_condition:
        regime = "BEAR"
    elif sideways_condition:
        regime = "SIDEWAYS"

    # Fallback: 조건식으로 판정되지 않으면 점수 기반 판정 사용.
    # 이유: VIX/Breadth 데이터가 없거나, 전환 구간(조건식이 어정쩡한 경우)에서
    # 합리적인 기본값을 제공하기 위해 보조 지표로 점수 로직을 유지한다.
    if regime is None:
        score = 0

        # 1) SPY vs SMA(200)
        if price_above_sma:
            score += 1
        else:
            score -= 1

        # 2) SMA(200) 기울기
        if sma_slope > 0.005:
            score += 1
        elif sma_slope < -0.005:
            score -= 1

        # 3) VIX
        if vix_value is not None:
            if vix_value < 20:
                score += 1
            elif vix_value > 25:
                score -= 1

        # 4) Market Breadth
        if breadth_pct is not None:
            if breadth_pct > 0.60:
                score += 1
            elif breadth_pct < 0.40:
                score -= 1

        # Fallback 판정
        if score >= 2:
            regime = "BULL"
        elif score <= -2:
            regime = "BEAR"
        elif abs(pct_from_sma) < 0.03 and abs(sma_slope) < 0.005:
            regime = "SIDEWAYS"
        elif score > 0:
            regime = "BULL"
        elif score < 0:
            regime = "BEAR"
        else:
            regime = "SIDEWAYS"

    # ── Bear 탈출 조건 판정 (반자동) ──
    bear_exit_count = 0
    if bear_exit_overrides is None:
        bear_exit_overrides = {}

    # 조건 1: Macro 기대 변화 (수동)
    if bear_exit_overrides.get(1, False):
        bear_exit_count += 1

    # 조건 2: 시장 반응 변화 (수동)
    if bear_exit_overrides.get(2, False):
        bear_exit_count += 1

    # 조건 3: 거래량 구조 신호 — 매도 소진 (자동 탐지)
    if bear_exit_overrides.get(3, False) or _check_selling_exhaustion(spy_df):
        bear_exit_count += 1

    return MarketRegime(
        regime=regime,
        spy_price=latest_price,
        sma_200=latest_sma,
        sma_200_slope=sma_slope,
        vix=vix_value,
        breadth_pct=breadth_pct,
        bear_exit_conditions_met=bear_exit_count,
        params=REGIME_PARAMS[regime],
    )


def compute_breadth(all_bars: pd.DataFrame, window: int = 50) -> float:
    """
    전 종목의 50일 이동평균 위 비율을 계산한다.

    Args:
        all_bars: MultiIndex(symbol, timestamp) OHLCV
        window: 이동평균 기간

    Returns:
        0.0 ~ 1.0 (50일선 위 종목 비율)
    """
    above_count = 0
    total_count = 0

    for symbol, group_df in all_bars.groupby(level="symbol"):
        group_df = group_df.droplevel("symbol")
        if len(group_df) < window:
            continue

        sma = group_df["close"].rolling(window).mean()
        latest_close = group_df["close"].iloc[-1]
        latest_sma = sma.iloc[-1]

        if pd.notna(latest_sma):
            total_count += 1
            if latest_close > latest_sma:
                above_count += 1

    if total_count == 0:
        return 0.5  # 데이터 부족 시 중립

    return above_count / total_count


def get_regime_params(regime: str) -> dict:
    """국면에 해당하는 파라미터 프리셋을 반환한다."""
    return REGIME_PARAMS.get(regime, REGIME_PARAMS["SIDEWAYS"])


def format_regime_report(mr: MarketRegime) -> str:
    """MarketRegime을 사람이 읽을 수 있는 리포트로 포맷한다."""
    pct_from_sma = (mr.spy_price / mr.sma_200 * 100 - 100) if mr.sma_200 > 0 else 0
    lines = [
        f"Market Regime: {mr.regime}",
        f"  SPY: ${mr.spy_price:.2f}  |  SMA(200): ${mr.sma_200:.2f}  ({pct_from_sma:+.1f}%)",
        f"  SMA(200) Slope (20d): {mr.sma_200_slope * 100:+.2f}%",
    ]
    if mr.vix is not None:
        lines.append(f"  VIX: {mr.vix:.1f}")
    if mr.breadth_pct is not None:
        lines.append(f"  Breadth (>50d SMA): {mr.breadth_pct * 100:.1f}%")
    if mr.bear_exit_conditions_met > 0:
        lines.append(f"  Bear Exit Conditions: {mr.bear_exit_conditions_met}/3")
    return "\n".join(lines)
