from pydantic import BaseModel
from typing import Literal, Optional


class BacktestRequest(BaseModel):
    initial_capital: float = 100000
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    universe: Literal["sp500", "sp500_400"] = "sp500"
    event_filter_mode: str = "none"  # use_events=False 시 이벤트 필터 비활성화
    risk_per_trade: float = 0.01
    max_positions: int = 10
    position_size_pct: float = 0.1
    use_events: bool = False  # playwright 의존성 제거 (P2 기능)
    use_macro_filter: bool = True


class BacktestStatus(BaseModel):
    backtest_id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress_pct: Optional[float] = None
