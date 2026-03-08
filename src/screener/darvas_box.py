"""
다바스 박스 실행 엔진 (Darvas Box Execution Engine)

protocol: docs/protocols/execution-protocol.md

박스 탐지 → 돌파 확인 → R:R 계산 → Time Stop 관리
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class DarvasBox:
    """탐지된 다바스 박스 하나를 표현한다."""

    box_top: float
    box_bottom: float
    box_height: float
    box_start: pd.Timestamp  # 박스 시작일
    box_end: pd.Timestamp  # 박스 종료일 (돌파일 또는 현재)
    duration_days: int
    avg_volume: float
    vol_sma_20: float  # 20일 평균 거래량 (비교 기준)


@dataclass
class BoxBreakout:
    """박스 돌파 이벤트."""

    symbol: str
    box: DarvasBox
    breakout_date: pd.Timestamp
    breakout_price: float  # 돌파일 종가
    breakout_vol_ratio: float  # 돌파일 거래량 / 20일 평균

    # R:R 계산
    stop_loss: float  # Box Top - Box Height × 0.25
    risk_r: float  # Entry - Stop Loss
    target_price: float  # 전고점 -5%
    reward: float  # Target - Entry
    rr_ratio: float  # Reward / Risk

    # 상태
    rr_pass: bool  # R:R ≥ 3.0 여부


# ── 박스 탐지 ─────────────────────────────────────────────


def find_darvas_boxes(
    df: pd.DataFrame,
    min_days: int = 10,
    max_width_pct: float = 0.15,
    min_vol_ratio: float = 0.8,
    vol_window: int = 20,
) -> list[DarvasBox]:
    """
    단일 종목의 OHLCV DataFrame에서 다바스 박스를 탐지한다.

    알고리즘:
    1. 새로운 N일 고점이 설정되면 박스 상단 후보로 등록
    2. 이후 3거래일 연속으로 신고가를 갱신하지 못하면 Box Top 확정
    3. Box Top 확정 후, 해당 구간의 최저가를 Box Bottom으로 설정
    4. 박스가 유효 조건(기간, 폭, 거래량)을 충족하면 리스트에 추가

    Args:
        df: columns=[open, high, low, close, volume] (single symbol, DatetimeIndex)
        min_days: 박스 최소 기간 (거래일)
        max_width_pct: 박스 폭 제한 (Box Height / Box Midpoint)
        min_vol_ratio: 박스 내 평균 거래량 / 20일 SMA 최소 비율
        vol_window: 거래량 이동평균 기간

    Returns:
        탐지된 DarvasBox 리스트 (시간순)
    """
    if len(df) < max(min_days + 10, vol_window + 5):
        return []

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    volumes = df["volume"].values
    dates = df.index

    vol_sma = pd.Series(volumes).rolling(vol_window).mean().values

    boxes: list[DarvasBox] = []

    i = vol_window  # vol_sma가 유효한 지점부터 시작
    n = len(df)

    while i < n - 3:
        # Step 1: 새 고점 후보 찾기
        # 현재 high가 직전 min_days일 최고가보다 높거나 같으면 고점 후보
        lookback_start = max(0, i - min_days)
        if highs[i] < max(highs[lookback_start:i]):
            i += 1
            continue

        candidate_top = highs[i]
        top_idx = i

        # Step 2: 3거래일 연속 신고가 미갱신 → Box Top 확정
        confirmed = True
        for j in range(1, 4):
            if top_idx + j >= n:
                confirmed = False
                break
            if highs[top_idx + j] > candidate_top:
                # 새 고점 발생 → 후보 갱신
                candidate_top = highs[top_idx + j]
                top_idx = top_idx + j
                confirmed = False
                break

        if not confirmed:
            i = top_idx
            continue

        box_top = candidate_top

        # Step 3: Box Bottom 확정 — 이후 가격이 박스 안에 머무르는 동안 최저가 추적
        box_start_idx = top_idx
        box_bottom = min(lows[top_idx : top_idx + 4])
        box_end_idx = top_idx + 3

        # 박스 확장: 가격이 box_top/box_bottom 안에 머무르는 한 계속
        # 하단 이탈 허용치 2%: 일중 노이즈(위킹)로 인한 거짓 무효화 방지 목적
        k = top_idx + 4
        bottom_broken = False
        while k < n:
            if highs[k] > box_top:
                # 박스 상단 돌파 → 박스 종료 (돌파 시점)
                break
            if lows[k] < box_bottom * 0.98:
                # 박스 하단을 2% 이상 이탈 → 박스 무효화
                bottom_broken = True
                box_end_idx = k
                break
            box_bottom = min(box_bottom, lows[k])
            box_end_idx = k
            k += 1

        if bottom_broken:
            i = box_end_idx + 1
            continue

        # Step 4: 유효성 검증
        duration = box_end_idx - box_start_idx + 1
        box_height = box_top - box_bottom
        box_mid = (box_top + box_bottom) / 2

        if duration < min_days:
            i = box_end_idx + 1
            continue

        if box_mid == 0 or box_height / box_mid > max_width_pct:
            i = box_end_idx + 1
            continue

        # 거래량 조건: 박스 내 평균 거래량 ≥ 20일 SMA × min_vol_ratio
        box_volumes = volumes[box_start_idx : box_end_idx + 1]
        avg_box_vol = float(np.mean(box_volumes))
        ref_vol_sma = float(vol_sma[box_start_idx]) if not np.isnan(vol_sma[box_start_idx]) else 0

        if ref_vol_sma > 0 and avg_box_vol < ref_vol_sma * min_vol_ratio:
            i = box_end_idx + 1
            continue

        boxes.append(
            DarvasBox(
                box_top=float(box_top),
                box_bottom=float(box_bottom),
                box_height=float(box_height),
                box_start=dates[box_start_idx],
                box_end=dates[box_end_idx],
                duration_days=duration,
                avg_volume=avg_box_vol,
                vol_sma_20=ref_vol_sma,
            )
        )

        i = box_end_idx + 1

    return boxes


# ── 돌파 탐지 ─────────────────────────────────────────────


def detect_breakouts(
    df: pd.DataFrame,
    boxes: list[DarvasBox],
    breakout_vol_ratio: float = 2.0,
    high_52w: float | None = None,
    target_discount: float = 0.05,
    symbol: str = "",
) -> list[BoxBreakout]:
    """
    박스 목록에서 거래량 동반 돌파를 탐지하고 R:R을 계산한다.

    Args:
        df: 원본 OHLCV DataFrame
        boxes: find_darvas_boxes()의 결과
        breakout_vol_ratio: 돌파 확인 최소 거래량 비율
        high_52w: 52주 최고가 (목표가 계산용). None이면 df에서 계산.
        target_discount: 전고점 대비 할인율 (기본 5%)
        symbol: 종목 심볼

    Returns:
        BoxBreakout 리스트
    """
    if not boxes:
        return []

    closes = df["close"]
    volumes = df["volume"]
    vol_sma = volumes.rolling(20).mean()

    if high_52w is None:
        high_52w = float(df["high"].rolling(252, min_periods=60).max().iloc[-1])

    target_price = high_52w * (1 - target_discount)

    breakouts: list[BoxBreakout] = []

    for box in boxes:
        # 박스 종료 다음 날부터 탐색 (최대 5거래일 이내)
        box_end_loc = df.index.get_loc(box.box_end)
        search_start = box_end_loc + 1
        search_end = min(box_end_loc + 6, len(df))

        for idx in range(search_start, search_end):
            date = df.index[idx]
            close = float(closes.iloc[idx])
            vol = float(volumes.iloc[idx])
            v_sma = float(vol_sma.iloc[idx]) if not np.isnan(vol_sma.iloc[idx]) else 1

            vol_ratio = vol / v_sma if v_sma > 0 else 0

            # 돌파 조건: 종가 > Box Top AND 거래량 ≥ 기준
            if close > box.box_top and vol_ratio >= breakout_vol_ratio:
                entry_price = close
                stop_loss = box.box_top - (box.box_height * 0.25)
                risk_r = entry_price - stop_loss
                reward = target_price - entry_price
                rr_ratio = reward / risk_r if risk_r > 0 else 0

                breakouts.append(
                    BoxBreakout(
                        symbol=symbol,
                        box=box,
                        breakout_date=date,
                        breakout_price=entry_price,
                        breakout_vol_ratio=round(vol_ratio, 2),
                        stop_loss=round(stop_loss, 2),
                        risk_r=round(risk_r, 2),
                        target_price=round(target_price, 2),
                        reward=round(reward, 2),
                        rr_ratio=round(rr_ratio, 2),
                        rr_pass=rr_ratio >= 3.0,
                    )
                )
                break  # 한 박스당 최초 돌파 1건만

    return breakouts


# ── 통합 분석 ─────────────────────────────────────────────


def analyze_symbol(
    df: pd.DataFrame,
    symbol: str = "",
    min_days: int = 10,
    max_width_pct: float = 0.15,
    breakout_vol_ratio: float = 2.0,
    min_rr: float = 3.0,
) -> dict:
    """
    단일 종목에 대해 박스 탐지 → 돌파 확인 → R:R 필터를 실행한다.

    Returns:
        {
            "symbol": str,
            "boxes": list[DarvasBox],
            "breakouts": list[BoxBreakout],
            "actionable": list[BoxBreakout],  # R:R ≥ min_rr 통과
            "latest_box": DarvasBox | None,    # 현재 형성 중인 박스
        }
    """
    boxes = find_darvas_boxes(
        df,
        min_days=min_days,
        max_width_pct=max_width_pct,
    )

    breakouts = detect_breakouts(
        df,
        boxes,
        breakout_vol_ratio=breakout_vol_ratio,
        symbol=symbol,
    )

    actionable = [b for b in breakouts if b.rr_ratio >= min_rr]

    # 현재 형성 중인 박스 (마지막 박스가 아직 돌파되지 않았으면)
    latest_box = None
    if boxes:
        last_box = boxes[-1]
        last_close = float(df["close"].iloc[-1])
        if last_close <= last_box.box_top:
            latest_box = last_box

    return {
        "symbol": symbol,
        "boxes": boxes,
        "breakouts": breakouts,
        "actionable": actionable,
        "latest_box": latest_box,
    }


def format_breakout_report(breakout: BoxBreakout) -> str:
    """BoxBreakout을 사람이 읽을 수 있는 리포트로 포맷한다."""
    b = breakout
    rr_status = "PASS" if b.rr_pass else "FAIL"
    return (
        f"[{b.symbol}] Box Breakout @ {b.breakout_date:%Y-%m-%d}\n"
        f"  Box: ${b.box.box_bottom:.2f} — ${b.box.box_top:.2f} "
        f"(H=${b.box.box_height:.2f}, {b.box.duration_days}d)\n"
        f"  Entry: ${b.breakout_price:.2f}  |  Vol: {b.breakout_vol_ratio:.1f}x\n"
        f"  Stop: ${b.stop_loss:.2f}  |  Target: ${b.target_price:.2f}\n"
        f"  R=${b.risk_r:.2f}  |  Reward=${b.reward:.2f}  |  "
        f"R:R={b.rr_ratio:.1f} [{rr_status}]"
    )
