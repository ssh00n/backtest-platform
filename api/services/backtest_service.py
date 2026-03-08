import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict, Any

from api.models.backtest import BacktestRequest

executor = ThreadPoolExecutor(max_workers=2)

# In-memory store for backtest jobs
backtest_store: Dict[str, Any] = {}
backtest_results: Dict[str, Any] = {}

HEARTBEAT_STEPS = [10, 20, 35, 50, 65, 80, 92]


def _run_backtest_sync(backtest_id: str, request: BacktestRequest):
    """Synchronous backtest runner - called in thread pool."""
    try:
        from datetime import datetime, timedelta
        from src.data.client import fetch_daily_bars
        from src.data.universe import get_sp500_symbols
        from src.backtest.engine import run_backtest
        from src.backtest.metrics import compute_metrics
        from src.backtest.portfolio import BacktestConfig

        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(request.end_date, "%Y-%m-%d")
        lookback_start = start_date - timedelta(days=400)

        symbols = get_sp500_symbols()
        excluded = {"BRK/B", "BF/B"}
        symbols = [s for s in symbols if s not in excluded]

        # SPY를 함께 로드해 timezone/index 형식 통일 (Alpaca 기준)
        all_symbols = list(set(symbols + ["SPY"]))
        bars = fetch_daily_bars(all_symbols, lookback_start, end_date)

        # SPY 추출 (Alpaca MultiIndex: (symbol, timestamp))
        spy_df = bars.xs("SPY", level="symbol").sort_index()

        config = BacktestConfig(
            initial_capital=request.initial_capital,
            max_positions=request.max_positions,
            position_size_pct=request.position_size_pct,
            event_filter_mode=request.event_filter_mode,
            use_events=False,  # Playwright(news crawler) 의존성 제거를 위해 비활성화
            use_macro_filter=request.use_macro_filter,
        )

        # run_backtest는 start_date/end_date를 str로 받음 (내부에서 pd.Timestamp 변환)
        result = run_backtest(
            bars, spy_df, config,
            start_date=request.start_date,
            end_date=request.end_date,
        )
        metrics = compute_metrics(result.portfolio, result.regime_history)

        equity_curve = [
            {"date": ts.strftime("%Y-%m-%d"), "value": round(v, 2)}
            for ts, v in result.portfolio.equity_curve
        ]

        trades = [
            {
                "date": t.exit_date.strftime("%Y-%m-%d"),
                "symbol": t.symbol,
                "pnl_r": round(t.pnl_r, 2),
                "exit_action": t.exit_action,
                "event_type": getattr(t, "event_type", "-"),
            }
            for t in result.portfolio.closed_trades
        ]

        def sanitize(obj):
            """inf/nan → null 변환 (JSON 직렬화 안전)"""
            import math
            if isinstance(obj, float):
                if math.isinf(obj) or math.isnan(obj):
                    return None
                return obj
            if isinstance(obj, dict):
                return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [sanitize(v) for v in obj]
            return obj

        result_data = {
            "backtest_id": backtest_id,
            "status": "completed",
            "metrics": sanitize(metrics),
            "equity_curve": equity_curve,
            "trades": trades,
        }
        backtest_results[backtest_id] = result_data
        backtest_store[backtest_id]["status"] = "completed"

        # DB 저장 (비동기 안전하게 try/except)
        try:
            from api.db import save_result
            save_result(backtest_id, request.__dict__, result_data)
        except Exception as db_err:
            print(f"[DB] save_result skipped: {db_err}")

    except Exception as e:
        backtest_store[backtest_id]["status"] = "failed"
        backtest_store[backtest_id]["error"] = str(e)


async def start_backtest(request: BacktestRequest) -> str:
    backtest_id = str(uuid.uuid4())
    backtest_store[backtest_id] = {
        "status": "running",
        "progress_pct": 0,
        "step_index": 0,
        "started_at": datetime.utcnow().isoformat(),
    }

    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, _run_backtest_sync, backtest_id, request)

    return backtest_id


def get_next_heartbeat(backtest_id: str) -> dict:
    job = backtest_store.get(backtest_id)
    if not job:
        return {"type": "error", "message": "Not found"}

    if job["status"] == "completed":
        return {"type": "completed", "backtest_id": backtest_id}

    if job["status"] == "failed":
        return {"type": "error", "message": job.get("error", "Unknown error")}

    idx = job.get("step_index", 0)
    if idx < len(HEARTBEAT_STEPS):
        pct = HEARTBEAT_STEPS[idx]
        job["step_index"] = idx + 1
        job["progress_pct"] = pct
    else:
        pct = job.get("progress_pct", 92)

    return {
        "type": "progress",
        "progress_pct": pct,
        "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "symbols_processed": int(pct * 5),
        "total_symbols": 500,
        "open_positions": 3,
    }
