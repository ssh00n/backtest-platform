"""
가격 기반 스크리너

TA 지양 원칙: 기술적 분석 지표(SMA 크로스오버, RSI 등)를 매매 판단에 사용하지 않는다.
가격 프로토콜은 오직 '사실 데이터'만 다룬다:
  - 52주 고점 대비 하락률 (구조적 할인 구간 탐지)
  - 회복 증거는 거래량 프로토콜(volume-protocol)에 위임
"""

import pandas as pd


def compute_price_signals(
    df: pd.DataFrame,
    deep_discount_threshold: float = -0.30,
) -> pd.DataFrame:
    """
    단일 종목의 OHLCV DataFrame에 가격 기반 시그널을 추가한다.

    TA 지양 원칙에 따라 SMA 크로스오버, RSI 등의 기술적 지표는 계산하지 않는다.
    회복 증거 확인은 거래량 프로토콜(volume_protocol.py)에서 처리한다.

    Args:
        df: columns=[open, high, low, close, volume] (single symbol, DatetimeIndex)
        deep_discount_threshold: 52주 고점 대비 하락률 임계값 (기본 -30%)

    Returns:
        원본 + 시그널 컬럼이 추가된 DataFrame
    """
    out = df.copy()

    # 52주 (252 거래일) 최고가 & 하락률 — 사실 데이터
    out["high_52w"] = out["high"].rolling(252, min_periods=60).max()
    out["drawdown_from_high"] = (out["close"] - out["high_52w"]) / out["high_52w"]

    # Deep Discount 조건 (국면별 임계값 사용)
    out["sig_deep_discount"] = out["drawdown_from_high"] <= deep_discount_threshold

    return out
