"""
백테스트 히스토리 조회 API
"""
from fastapi import APIRouter, HTTPException
from api.db import list_runs, get_run

router = APIRouter()


@router.get("/")
async def get_history(limit: int = 20):
    """백테스트 실행 목록 반환"""
    runs = list_runs(limit=limit)
    # Decimal/datetime 직렬화 처리
    result = []
    for r in runs:
        item = {}
        for k, v in r.items():
            if hasattr(v, "__float__"):
                item[k] = float(v) if v is not None else None
            elif hasattr(v, "isoformat"):
                item[k] = v.isoformat()
            else:
                item[k] = v
        result.append(item)
    return {"runs": result, "total": len(result)}


@router.get("/{backtest_id}")
async def get_history_detail(backtest_id: str):
    """단일 백테스트 상세 조회 (equity_curve + trades 포함)"""
    run = get_run(backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    result = {}
    for k, v in run.items():
        if hasattr(v, "__float__"):
            result[k] = float(v) if v is not None else None
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
