"""
Alpaca Market Data Service — 현재 시세 조회
REST API 사용 (Paper Trading용)
"""
import os
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")


def _get_client() -> StockHistoricalDataClient:
    return StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)


def get_current_price(symbol: str) -> float | None:
    """단일 종목 현재가 조회 (ask price 우선, trade price 폴백)"""
    try:
        client = _get_client()
        # 최근 거래 가격 사용 (장 외에도 동작)
        req = StockLatestTradeRequest(symbol_or_symbols=symbol)
        trades = client.get_stock_latest_trade(req)
        if symbol in trades and trades[symbol].price:
            return float(trades[symbol].price)
        # 폴백: quote ask price
        quote_req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        quotes = client.get_stock_latest_quote(quote_req)
        if symbol in quotes:
            ask = quotes[symbol].ask_price
            bid = quotes[symbol].bid_price
            if ask and ask > 0:
                return float(ask)
            if bid and bid > 0:
                return float(bid)
        return None
    except Exception as e:
        print(f"[Alpaca] get_current_price error for {symbol}: {e}")
        return None


def get_prices(symbols: list[str]) -> dict[str, float]:
    """복수 종목 현재가 일괄 조회"""
    if not symbols:
        return {}
    try:
        client = _get_client()
        req = StockLatestTradeRequest(symbol_or_symbols=symbols)
        trades = client.get_stock_latest_trade(req)
        result = {}
        for sym in symbols:
            if sym in trades and trades[sym].price:
                result[sym] = float(trades[sym].price)
        return result
    except Exception as e:
        print(f"[Alpaca] get_prices error: {e}")
        return {}
