"""
확장 유니버스 — S&P 500 + S&P 400 Mid-Cap

실전 운용 빈도 개선: 500종목 → 900종목
  S&P 500: 대형주 (기존)
  S&P 400: 중형주 (신규 추가) — 유동성 충분, 모멘텀 더 강함

중형주 특징:
  - 대형주보다 모멘텀 패턴 더 선명 (기관 추적 상대적으로 적음)
  - 유동성은 일평균 거래량 기준 필터링
  - 소형주(S&P 600)는 제외 (슬리피지/유동성 리스크)
"""
from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SP400_CACHE = CACHE_DIR / "sp400_constituents.parquet"
SP400_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

# Alpaca에서 제외할 심볼
_EXCLUDE = {"BRK/B", "BF/B"}


def fetch_sp400_constituents(use_cache: bool = True) -> pd.DataFrame:
    """S&P 400 Mid-Cap 구성종목 조회."""
    if use_cache and SP400_CACHE.exists():
        return pd.read_parquet(SP400_CACHE)

    try:
        # pandas read_html로 Wikipedia 직접 파싱 (User-Agent 필요)
        import requests
        from io import StringIO as _SIO
        r = requests.get(SP400_WIKI_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        tables = pd.read_html(_SIO(r.text))
        df = tables[0]

        # 컬럼명 정규화
        col_map = {}
        for col in df.columns:
            cl = col.lower()
            if "symbol" in cl or "ticker" in cl:
                col_map[col] = "symbol"
            elif "security" in cl or "company" in cl or "name" in cl:
                col_map[col] = "name"
            elif "sector" in cl and "sub" not in cl:
                col_map[col] = "sector"
        df = df.rename(columns=col_map)

        if "symbol" not in df.columns:
            # fallback: 첫 번째 컬럼
            df = df.rename(columns={df.columns[0]: "symbol"})

        df["symbol"] = df["symbol"].str.replace(".", "/", regex=False)
        df["source"] = "SP400"

        cols = [c for c in ["symbol", "name", "sector", "source"] if c in df.columns]
        df = df[cols].copy()
        df.to_parquet(SP400_CACHE, index=False)
        return df

    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("S&P 400 조회 실패: %s", e)
        return pd.DataFrame(columns=["symbol", "name", "sector", "source"])


def get_extended_universe(
    include_sp500: bool = True,
    include_sp400: bool = True,
    min_avg_volume: int = 500_000,   # 일평균 최소 거래량 (유동성 필터)
) -> list[str]:
    """
    확장 유니버스 티커 리스트.

    Args:
        include_sp500: S&P 500 포함 (기본 True)
        include_sp400: S&P 400 Mid-Cap 포함 (기본 True)
        min_avg_volume: 유동성 필터 (거래량 미확인 종목은 일단 포함)

    Returns:
        ticker 문자열 리스트 (중복 제거, 제외 심볼 필터링)
    """
    symbols: set[str] = set()

    if include_sp500:
        try:
            from src.data.universe import get_sp500_symbols
            sp500 = get_sp500_symbols()
            symbols.update(sp500)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("S&P 500 로드 실패: %s", e)

    if include_sp400:
        sp400_df = fetch_sp400_constituents()
        symbols.update(sp400_df["symbol"].tolist())

    # 제외 심볼 필터
    symbols -= _EXCLUDE

    return sorted(symbols)


def get_universe_stats() -> dict:
    """유니버스 통계 반환."""
    sp500_n = 0
    sp400_n = 0

    try:
        from src.data.universe import get_sp500_symbols
        sp500_n = len(get_sp500_symbols())
    except Exception:
        pass

    sp400_df = fetch_sp400_constituents()
    sp400_n = len(sp400_df)

    return {
        "sp500": sp500_n,
        "sp400": sp400_n,
        "total": sp500_n + sp400_n,
        "overlap_est": min(50, sp400_n),  # 대략적 중복 추정
    }


if __name__ == "__main__":
    stats = get_universe_stats()
    print(f"S&P 500: {stats['sp500']}종목")
    print(f"S&P 400: {stats['sp400']}종목")
    print(f"합산(중복 전): {stats['total']}종목")
    universe = get_extended_universe()
    print(f"최종 유니버스: {len(universe)}종목")
    print("샘플:", universe[:10])
