from pydantic import BaseModel
from typing import Literal, Optional


class BacktestRequest(BaseModel):
    initial_capital: float = 100000
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    universe: Literal["sp500", "sp500_400"] = "sp500"
    event_filter_mode: str = "earnings_block"
    risk_per_trade: float = 0.01
    max_positions: int = 10
    position_size_pct: float = 0.1
    use_events: bool = True
    use_macro_filter: bool = True


class BacktestStatus(BaseModel):
    backtest_id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress_pct: Optional[float] = None
