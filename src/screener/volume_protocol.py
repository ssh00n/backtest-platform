"""
거래량 프로토콜 (Volume Protocol)

전략의 핵심: 차트에서 유일하게 신뢰할 수 있는 데이터 = 거래량(행동의 결과)

4가지 시나리오 탐지:
  1 매집 (Accumulation): 가격 횡보 + 거래량 증가 -> 관심 종목 등록
  2 확인 (Confirmation): 가격 상승 + 거래량 증가 -> 매수 검토
  3 관성 (Momentum Fade): 가격 상승 + 거래량 감소 -> 추격 매수 금지
  4 흡수 (Absorption): 가격 변화 없음 + 거래량 급증 -> 추세 전환 주시
"""

import pandas as pd


def compute_volume_signals(
    df: pd.DataFrame,
    window: int = 20,
    regime: str = "SIDEWAYS",
) -> pd.DataFrame:
    """
    단일 종목의 OHLCV DataFrame에 거래량 프로토콜 시그널을 추가한다.

    국면별 임계값:
      Bull:     accumulation 1.5x, confirmation 1.5x
      Sideways: accumulation 1.5x, confirmation 2.0x
      Bear:     accumulation 2.0x, confirmation 3.0x

    Args:
        df: columns=[open, high, low, close, volume] (single symbol, DatetimeIndex)
        window: 이동평균 기간 (기본 20일)
        regime: 시장 국면 ("BULL", "SIDEWAYS", "BEAR")

    Returns:
        원본 + 시그널 컬럼이 추가된 DataFrame
    """
    # 국면별 임계값
    thresholds = {
        "BULL": {"accumulation": 1.5, "confirmation": 1.5},
        "SIDEWAYS": {"accumulation": 1.5, "confirmation": 2.0},
        "BEAR": {"accumulation": 2.0, "confirmation": 3.0},
    }
    t = thresholds.get(regime, thresholds["SIDEWAYS"])

    out = df.copy()

    # 기본 지표
    out["vol_sma"] = out["volume"].rolling(window).mean()
    out["vol_ratio"] = out["volume"] / out["vol_sma"]
    out["price_change_pct"] = out["close"].pct_change()
    out["price_range_ratio"] = (
        out["high"].rolling(window).max() - out["low"].rolling(window).min()
    ) / out["close"]

    # 5일 수익률 (단기 추세)
    out["return_5d"] = out["close"].pct_change(5)

    # 1 매집 (Accumulation): 가격 횡보(range < 10%) + 거래량 증가
    out["sig_accumulation"] = (out["price_range_ratio"] < 0.10) & (
        out["vol_ratio"] > t["accumulation"]
    )

    # 2 확인 (Confirmation): 가격 상승 + 거래량 기준 이상
    out["sig_confirmation"] = (out["price_change_pct"] > 0.01) & (
        out["vol_ratio"] > t["confirmation"]
    )

    # 3 관성 (Momentum Fade): 가격 상승 + 거래량 감소
    out["sig_momentum_fade"] = (out["return_5d"] > 0.03) & (out["vol_ratio"] < 0.7)

    # 4 흡수 (Absorption): 가격 변화 미미 + 거래량 급증
    out["sig_absorption"] = (out["price_change_pct"].abs() < 0.005) & (
        out["vol_ratio"] > 3.0
    )

    return out


def classify_volume_regime(row: pd.Series) -> str:
    """단일 행의 거래량 레짐을 분류한다."""
    if row.get("sig_confirmation"):
        return "CONFIRMATION"
    if row.get("sig_accumulation"):
        return "ACCUMULATION"
    if row.get("sig_absorption"):
        return "ABSORPTION"
    if row.get("sig_momentum_fade"):
        return "MOMENTUM_FADE"
    return "NEUTRAL"
