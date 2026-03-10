"""
Paper Trading Service — 주문 처리 및 포트폴리오 관리 로직
"""
from api.db import (
    get_or_create_portfolio,
    get_portfolio,
    get_positions,
    get_orders,
    get_equity_curve,
    execute_paper_order,
    reset_portfolio,
)
from api.services.alpaca_market_service import get_current_price, get_prices


class InsufficientFundsError(Exception):
    pass


class InsufficientSharesError(Exception):
    pass


class PriceUnavailableError(Exception):
    pass


def get_portfolio_overview(user_id: str) -> dict:
    """포트폴리오 개요 조회 (현재 시세 포함)"""
    portfolio = get_or_create_portfolio(user_id)
    if not portfolio:
        raise RuntimeError("Failed to get or create portfolio")

    portfolio_id = portfolio["id"]
    cash_balance = float(portfolio["cash_balance"])
    initial_capital = float(portfolio["initial_capital"])

    # 포지션 현재가 조회
    positions = get_positions(portfolio_id)
    symbols = [p["symbol"] for p in positions]
    prices = get_prices(symbols) if symbols else {}

    total_market_value = 0.0
    for pos in positions:
        sym = pos["symbol"]
        current_price = prices.get(sym, float(pos["avg_cost"]))
        total_market_value += float(pos["shares"]) * current_price

    portfolio_value = cash_balance + total_market_value
    total_return_pct = ((portfolio_value - initial_capital) / initial_capital) * 100

    # 미체결 매수 주문 기준 buying_power 계산
    pending_orders = get_orders(portfolio_id, limit=200)
    pending_buy_value = sum(
        float(o["qty"]) * float(o.get("limit_price") or 0)
        for o in pending_orders
        if o["status"] == "pending" and o["side"] == "buy"
    )
    buying_power = max(0.0, cash_balance - pending_buy_value)

    return {
        "id": portfolio_id,
        "initial_capital": initial_capital,
        "cash_balance": cash_balance,
        "portfolio_value": round(portfolio_value, 2),
        "total_return_pct": round(total_return_pct, 2),
        "day_pnl": 0.0,      # TODO: 일별 P&L (equity curve 활용)
        "day_pnl_pct": 0.0,
        "buying_power": round(buying_power, 2),
        "positions_count": len([p for p in positions if float(p["shares"]) > 0]),
        "updated_at": portfolio.get("updated_at"),
    }


def get_positions_with_prices(user_id: str) -> dict:
    """보유 포지션 + 현재가 조회"""
    portfolio = get_or_create_portfolio(user_id)
    if not portfolio:
        raise RuntimeError("Failed to get portfolio")

    positions = get_positions(portfolio["id"])
    symbols = [p["symbol"] for p in positions]
    prices = get_prices(symbols) if symbols else {}

    result = []
    total_market_value = 0.0
    for pos in positions:
        sym = pos["symbol"]
        shares = float(pos["shares"])
        avg_cost = float(pos["avg_cost"])
        current_price = prices.get(sym, avg_cost)
        market_value = shares * current_price
        unrealized_pnl = shares * (current_price - avg_cost)
        unrealized_pnl_pct = ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0

        total_market_value += market_value
        result.append({
            "symbol": sym,
            "shares": shares,
            "avg_cost": round(avg_cost, 2),
            "current_price": round(current_price, 2),
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "updated_at": pos.get("updated_at"),
        })

    return {
        "positions": result,
        "total_market_value": round(total_market_value, 2),
    }


def submit_order(
    user_id: str,
    symbol: str,
    side: str,
    qty: float,
    order_type: str = "market",
    limit_price: float | None = None,
) -> dict:
    """주문 제출 및 체결 처리"""
    symbol = symbol.upper().strip()
    portfolio = get_or_create_portfolio(user_id)
    if not portfolio:
        raise RuntimeError("Failed to get portfolio")

    portfolio_id = portfolio["id"]
    cash_balance = float(portfolio["cash_balance"])

    # 현재가 조회
    current_price = get_current_price(symbol)
    if current_price is None or current_price <= 0:
        raise PriceUnavailableError(f"Unable to get price for {symbol}. Market may be closed.")

    # 체결가 결정
    if order_type == "market":
        filled_price = current_price
    else:
        # Limit order: 현재가가 limit_price 범위 내면 즉시 체결 (단순화)
        if limit_price is None:
            raise ValueError("limit_price required for limit orders")
        if side == "buy" and current_price <= limit_price:
            filled_price = current_price
        elif side == "sell" and current_price >= limit_price:
            filled_price = current_price
        else:
            # 조건 미충족 → pending (현재는 단순화를 위해 에러)
            raise ValueError(
                f"Limit order condition not met. Current price: ${current_price:.2f}, "
                f"Limit: ${limit_price:.2f}. Limit orders execute only when price crosses limit."
            )

    trade_value = qty * filled_price

    # 잔고/수량 검증
    if side == "buy":
        if trade_value > cash_balance:
            raise InsufficientFundsError(
                f"Insufficient funds. Required: ${trade_value:.2f}, Available: ${cash_balance:.2f}"
            )
    else:
        positions = get_positions(portfolio_id)
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos or float(pos["shares"]) < qty:
            available = float(pos["shares"]) if pos else 0
            raise InsufficientSharesError(
                f"Insufficient shares. Required: {qty}, Available: {available}"
            )

    # 주문 체결
    result = execute_paper_order(
        portfolio_id=portfolio_id,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        filled_price=filled_price,
        limit_price=limit_price,
    )
    if not result:
        raise RuntimeError("Order execution failed")

    return result


def reset_paper_portfolio(user_id: str) -> dict:
    """포트폴리오 초기화"""
    result = reset_portfolio(user_id)
    if not result:
        raise RuntimeError("Failed to reset portfolio")
    return result


def cancel_paper_order(user_id: str, order_id: str) -> dict:
    """pending 상태 주문 취소"""
    result = db.cancel_order(user_id, order_id)
    if not result:
        raise ValueError("Order not found or not cancellable (only pending orders can be cancelled)")
    return result
