"""
Paper Trading API Routes (HOO-9)
Auth 필수: 전체 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional

from api.deps import get_current_user
from api.db import get_orders, get_equity_curve, get_or_create_portfolio
from api.services.paper_trading_service import (
    cancel_paper_order,
    get_portfolio_overview,
    get_positions_with_prices,
    submit_order,
    reset_paper_portfolio,
    InsufficientFundsError,
    InsufficientSharesError,
    PriceUnavailableError,
)

router = APIRouter()


class OrderRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    side: str = Field(..., pattern="^(buy|sell)$")
    qty: float = Field(..., gt=0)
    order_type: str = Field("market", pattern="^(market|limit)$")
    limit_price: Optional[float] = Field(None, gt=0)


# ── GET /portfolio ──────────────────────────────────────────────────────────

@router.get("/portfolio")
async def get_portfolio(current_user: dict = Depends(get_current_user)):
    """포트폴리오 개요 (balance, P&L, buying power)"""
    try:
        return get_portfolio_overview(current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /orders ─────────────────────────────────────────────────────────────

@router.post("/orders", status_code=status.HTTP_201_CREATED)
async def place_order(
    req: OrderRequest,
    current_user: dict = Depends(get_current_user),
):
    """주문 제출 (buy/sell)"""
    try:
        result = submit_order(
            user_id=current_user["id"],
            symbol=req.symbol,
            side=req.side,
            qty=req.qty,
            order_type=req.order_type,
            limit_price=req.limit_price,
        )
        # 포트폴리오 잔고 업데이트 반영
        portfolio = get_or_create_portfolio(current_user["id"])
        return {
            "order": result,
            "cash_remaining": float(portfolio["cash_balance"]) if portfolio else None,
        }
    except InsufficientFundsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsufficientSharesError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PriceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /positions ────────────────────────────────────────────────────────────

@router.get("/positions")
async def get_positions(current_user: dict = Depends(get_current_user)):
    """보유 종목 목록 (현재 시세 포함)"""
    try:
        return get_positions_with_prices(current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /orders ───────────────────────────────────────────────────────────────

@router.get("/orders")
async def get_order_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """최근 주문 기록"""
    try:
        portfolio = get_or_create_portfolio(current_user["id"])
        if not portfolio:
            return {"orders": []}
        orders = get_orders(portfolio["id"], limit=limit)
        return {"orders": orders}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /equity-curve ─────────────────────────────────────────────────────────

@router.get("/equity-curve")
async def get_equity_curve_endpoint(current_user: dict = Depends(get_current_user)):
    """포트폴리오 가치 히스토리"""
    try:
        portfolio = get_or_create_portfolio(current_user["id"])
        if not portfolio:
            return {"equity_curve": []}
        curve = get_equity_curve(portfolio["id"])
        return {"equity_curve": curve}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /reset ───────────────────────────────────────────────────────────────

@router.post("/reset")
async def reset_portfolio_endpoint(current_user: dict = Depends(get_current_user)):
    """포트폴리오 초기화 ($100,000 리셋)"""
    try:
        result = reset_paper_portfolio(current_user["id"])
        return {"message": "Portfolio reset successfully", "portfolio": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order_endpoint(
    order_id: str,
    current_user: dict = Depends(get_current_user),
):
    """pending 상태 주문 취소"""
    try:
        result = cancel_paper_order(current_user["id"], order_id)
        return {"message": "Order cancelled", "order": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
