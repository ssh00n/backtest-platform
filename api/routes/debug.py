"""
임시 진단 엔드포인트 — SPY 데이터 구조 확인용
"""
from fastapi import APIRouter
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/spy")
async def debug_spy():
    """SPY 데이터 fetch + 구조 진단"""
    try:
        from src.data.client import fetch_daily_bars
        start = datetime(2024, 1, 1)
        end = datetime(2024, 3, 31)
        bars = fetch_daily_bars(["SPY"], start, end)

        info = {
            "bars_empty": bars.empty,
            "bars_shape": list(bars.shape) if not bars.empty else None,
            "bars_index_names": list(bars.index.names) if not bars.empty else None,
            "bars_columns": list(bars.columns) if not bars.empty else None,
        }

        if not bars.empty:
            try:
                spy_df = bars.xs("SPY", level="symbol").sort_index()
                info["xs_symbol_ok"] = True
                info["spy_df_len"] = len(spy_df)
                info["spy_df_cols"] = list(spy_df.columns)
                info["spy_index_tz"] = str(spy_df.index.tz)
                info["spy_first_idx"] = str(spy_df.index[0]) if len(spy_df) > 0 else None
                if "close" in spy_df.columns:
                    spy_raw = spy_df["close"].sort_index()
                    filtered = [
                        ts.strftime("%Y-%m-%d")
                        for ts in spy_raw.index
                        if "2024-01-01" <= ts.strftime("%Y-%m-%d") <= "2024-03-31"
                    ]
                    info["string_filter_count"] = len(filtered)
                    info["string_filter_sample"] = filtered[:3]
            except Exception as e:
                info["xs_symbol_ok"] = False
                info["xs_error"] = str(e)
                # Try level=0
                try:
                    spy_df2 = bars.xs("SPY", level=0).sort_index()
                    info["xs_level0_ok"] = True
                    info["xs_level0_len"] = len(spy_df2)
                except Exception as e2:
                    info["xs_level0_error"] = str(e2)

        return {"status": "ok", "info": info}
    except Exception as e:
        return {"status": "error", "error": str(e)}
