import asyncio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from api.models.backtest import BacktestRequest
from api.services.backtest_service import (
    start_backtest, get_next_heartbeat, backtest_store, backtest_results
)

router = APIRouter()


@router.post("")
async def create_backtest(request: BacktestRequest):
    backtest_id = await start_backtest(request)
    return {"backtest_id": backtest_id, "status": "running"}


@router.get("/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    result = backtest_results.get(backtest_id)
    if not result:
        job = backtest_store.get(backtest_id)
        if not job:
            raise HTTPException(status_code=404, detail="Backtest not found")
        return {"backtest_id": backtest_id, "status": job.get("status", "running")}
    return result


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
