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
