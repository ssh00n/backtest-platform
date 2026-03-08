from fastapi import APIRouter

router = APIRouter()


@router.get("/config")
async def get_strategy_config():
    return {
        "fields": [
            {"name": "initial_capital", "type": "number", "min": 10000, "max": 10000000, "default": 100000},
            {"name": "start_date", "type": "date", "default": "2020-01-01"},
            {"name": "end_date", "type": "date", "default": "2024-12-31"},
            {"name": "universe", "type": "select", "options": ["sp500", "sp500_400"], "default": "sp500"},
            {"name": "event_filter_mode", "type": "select",
             "options": ["earnings_block", "miss_block", "no_event_only", "none"],
             "default": "earnings_block"},
            {"name": "risk_per_trade", "type": "number", "min": 0.001, "max": 0.05, "step": 0.001, "default": 0.01},
        ]
    }
