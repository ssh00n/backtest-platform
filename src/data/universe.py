"""
S&P 500 Universe 관리
- Playwright로 Wikipedia 스크래핑
- Parquet 캐싱
"""

from io import StringIO
from pathlib import Path

import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)

from src.utils.browser import BrowserClient

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SP500_CACHE = CACHE_DIR / "sp500_constituents.parquet"
SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500_constituents(use_cache: bool = True) -> pd.DataFrame:
    """
    S&P 500 구성종목 리스트를 가져온다.

    Returns:
        DataFrame with columns: symbol, name, sector, sub_industry
    """
    if use_cache and SP500_CACHE.exists():
        return pd.read_parquet(SP500_CACHE)

    with BrowserClient() as browser:
        html = browser.get_page_html(SP500_WIKI_URL)

    tables = pd.read_html(StringIO(html), header=0)
    df = tables[0]

    df = df.rename(
        columns={
            "Symbol": "symbol",
            "Security": "name",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
        }
    )

    # Alpaca 티커 형식: BRK.B → BRK/B, BF.B → BF/B
    df["symbol"] = df["symbol"].str.replace(".", "/", regex=False)

    df = df[["symbol", "name", "sector", "sub_industry"]].copy()
    df.to_parquet(SP500_CACHE, index=False)
    return df


def get_sp500_symbols(use_cache: bool = True) -> list[str]:
    """S&P 500 티커 리스트만 반환"""
    df = fetch_sp500_constituents(use_cache=use_cache)
    return df["symbol"].tolist()


def get_sectors() -> dict[str, list[str]]:
    """섹터별 종목 딕셔너리 반환"""
    df = fetch_sp500_constituents()
    return df.groupby("sector")["symbol"].apply(list).to_dict()
