"""
백테스트 히스토리 조회 API
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from api.db import list_runs, list_runs_by_user, get_run
from api.deps import get_optional_current_user

router = APIRouter()


def _serialize(r: dict) -> dict:
    result = {}
    for k, v in r.items():
        if hasattr(v, "__float__"):
            result[k] = float(v) if v is not None else None
        elif hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


@router.get("/")
async def get_history(
    limit: int = 20,
    current_user: dict | None = Depends(get_optional_current_user),
):
    """백테스트 실행 목록 — 로그인 시 내 것만, 미로그인 시 전체"""
    if current_user:
        runs = list_runs_by_user(current_user["id"], limit=limit)
    else:
        runs = list_runs(limit=limit)
    result = [_serialize(r) for r in runs]
    return {"runs": result, "total": len(result)}


@router.get("/{backtest_id}")
async def get_history_detail(backtest_id: str):
    """단일 백테스트 상세 조회 (equity_curve + trades 포함)"""
    run = get_run(backtest_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    return _serialize(run)
