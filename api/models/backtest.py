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
    # Darvas Box 파라미터 확장
    darvas_box_period: int = 55           # 박스 형성 기간 (캔들 수)
    darvas_breakout_pct: float = 0.02     # 박스 상단 돌파 여유 (2%)
    darvas_stop_loss_pct: float = 0.07    # 손절 %
    darvas_trailing_stop: bool = True     # 트레일링 스탑 여부
    strategy_name: str = "darvas_box"     # 전략명 (미래 확장용)


class BacktestStatus(BaseModel):
    backtest_id: str
    status: Literal["pending", "running", "completed", "failed"]
    progress_pct: Optional[float] = None
