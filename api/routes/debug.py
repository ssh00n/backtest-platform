"""
임시 진단 엔드포인트 — SPY 데이터 구조 확인용
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/spy")
async def debug_spy():
    """SPY 데이터 fetch + 구조 진단"""
    try:
        from datetime import datetime, timedelta
        from src.data.client import fetch_daily_bars

        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)
        bars = fetch_daily_bars(["SPY"], start, end)

        if bars.empty:
            return {"status": "ok", "bars_empty": True}

        info = {
            "bars_shape": list(bars.shape),
            "bars_index_names": list(bars.index.names),
            "bars_columns": list(bars.columns),
        }

        try:
            spy_df = bars.xs("SPY", level="symbol").sort_index()
            info["xs_ok"] = True
            info["spy_df_len"] = len(spy_df)
            info["spy_cols"] = list(spy_df.columns)
            if len(spy_df) > 0:
                info["spy_index_tz"] = str(spy_df.index.tz)
                info["spy_first_ts"] = str(spy_df.index[0])
            if "close" in spy_df.columns:
                spy_raw = spy_df["close"]
                filtered = [
                    ts.strftime("%Y-%m-%d")
                    for ts in spy_raw.index
                    if "2024-01-01" <= ts.strftime("%Y-%m-%d") <= "2024-03-31"
                ]
                info["filtered_count"] = len(filtered)
                info["filtered_sample"] = filtered[:3]
        except Exception as e:
            info["xs_error"] = str(e)

        return {"status": "ok", "info": info}
    except Exception as e:
        return {"status": "error", "error": str(e)}
