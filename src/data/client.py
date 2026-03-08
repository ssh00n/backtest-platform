"""
Alpaca API 클라이언트 래퍼
- 환경변수 기반 인증
- OHLCV 데이터 수집 + Parquet 캐싱
"""

import hashlib
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_keys() -> tuple[str, str]:
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        raise ValueError("ALPACA_API_KEY / ALPACA_API_SECRET not set in .env")
    return api_key, api_secret


def get_trading_client() -> TradingClient:
    key, secret = _get_keys()
    return TradingClient(key, secret, paper=True)


def get_data_client() -> StockHistoricalDataClient:
    key, secret = _get_keys()
    return StockHistoricalDataClient(key, secret)


def fetch_daily_bars(
    symbols: list[str],
    start: datetime,
    end: datetime | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    일봉 OHLCV 데이터를 가져온다. Parquet 캐시 지원.

    Returns:
        MultiIndex DataFrame (symbol, timestamp) with columns:
        open, high, low, close, volume, trade_count, vwap
    """
    if end is None:
        end = datetime.now() - timedelta(days=1)

    symbols_hash = hashlib.md5("_".join(sorted(symbols)).encode()).hexdigest()[:12]
    cache_key = f"bars_{len(symbols)}sym_{symbols_hash}_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
    cache_path = CACHE_DIR / cache_key

    if use_cache and cache_path.exists():
        return pd.read_parquet(cache_path)

    client = get_data_client()

    # Alpaca는 한 번에 최대 10,000 bars 반환 — 종목이 많으면 배치 처리
    all_frames = []
    failed_symbols = []
    batch_size = 20
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    for idx, i in enumerate(range(0, len(symbols), batch_size)):
        batch = symbols[i : i + batch_size]
        try:
            request = StockBarsRequest(
                symbol_or_symbols=batch,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )
            bars = client.get_stock_bars(request)
            if bars.df is not None and not bars.df.empty:
                all_frames.append(bars.df)
            if (idx + 1) % 5 == 0 or idx == total_batches - 1:
                log.debug("batch %d/%d complete", idx + 1, total_batches)
        except Exception as e:
            failed_symbols.extend(batch)
            log.warning("batch %d/%d failed (%s~): %s", idx + 1, total_batches, batch[0], e)

    if failed_symbols:
        log.warning("%d symbols failed: %s...", len(failed_symbols), failed_symbols[:10])

    if not all_frames:
        return pd.DataFrame()

    df = pd.concat(all_frames)
    df.to_parquet(cache_path)
    return df
