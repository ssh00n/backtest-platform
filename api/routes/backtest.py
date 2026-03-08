import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from api.models.backtest import BacktestRequest
from api.services.backtest_service import (
    start_backtest, get_next_heartbeat, backtest_store, backtest_results
)
from api.db import get_run

router = APIRouter()


@router.post("")
async def create_backtest(request: BacktestRequest):
    backtest_id = await start_backtest(request)
    return {"backtest_id": backtest_id, "status": "running"}


@router.get("/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    # 1. in-memory store (실행 직후)
    result = backtest_results.get(backtest_id)
    if result:
        return result

    # 2. 실행 중 상태 확인
    job = backtest_store.get(backtest_id)
    if job and job.get("status") == "running":
        return {"backtest_id": backtest_id, "status": "running"}

    # 3. DB fallback (재배포 후 메모리 초기화된 경우)
    db_row = get_run(backtest_id)
    if db_row:
        # DB row 전체를 반환 (metrics, equity_curve, trades, spy_equity_curve 등 포함)
        return {
            "backtest_id": db_row.get("id", backtest_id),
            "status": db_row.get("status", "completed"),
            "metrics": db_row.get("metrics") or {},
            "equity_curve": db_row.get("equity_curve") or [],
            "spy_equity_curve": db_row.get("spy_equity_curve") or [],
            "trades": db_row.get("trades") or [],
            "start_date": db_row.get("start_date"),
            "end_date": db_row.get("end_date"),
        }

    raise HTTPException(status_code=404, detail="Backtest not found")


@router.websocket("/ws/{backtest_id}")
async def backtest_ws(websocket: WebSocket, backtest_id: str):
    await websocket.accept()
    try:
        while True:
            msg = get_next_heartbeat(backtest_id)
            await websocket.send_json(msg)

            if msg["type"] in ("completed", "error"):
                break

            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    finally:
        await websocket.close()


@router.get("/debug/spy")
async def debug_spy():
    """SPY 데이터 직접 진단 - Alpaca MultiIndex 구조 확인"""
    from datetime import date, timedelta
    from src.data.fetcher import fetch_daily_bars
    from src.data.universe_extended import get_sp500_symbols
    try:
        symbols = ["SPY", "AAPL"]
        end_date = date.today()
        start_date = end_date - timedelta(days=10)
        bars = fetch_daily_bars(symbols, start_date, end_date)
        spy_df = bars.xs("SPY", level="symbol").sort_index()
        spy_raw = spy_df["close"].sort_index()
        return {
            "spy_raw_len": len(spy_raw),
            "index_tz": str(spy_raw.index.tz) if len(spy_raw) > 0 else None,
            "first_ts": repr(spy_raw.index[0]) if len(spy_raw) > 0 else None,
            "first_ts_str": spy_raw.index[0].strftime("%Y-%m-%d") if len(spy_raw) > 0 else None,
            "columns": list(spy_df.columns),
            "sample": [{"date": ts.strftime("%Y-%m-%d"), "v": float(v)} for ts, v in list(spy_raw.items())[:3]],
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
