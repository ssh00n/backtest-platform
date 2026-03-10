const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://backtest-platform-api-production-6ae3.up.railway.app';

export interface Portfolio {
  id: string;
  initial_capital: number;
  cash_balance: number;
  portfolio_value: number;
  total_return_pct: number;
  day_pnl: number;
  day_pnl_pct: number;
  buying_power: number;
  positions_count: number;
  updated_at: string;
}

export interface Position {
  symbol: string;
  shares: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  updated_at: string;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: 'market' | 'limit';
  limit_price?: number;
  filled_price?: number;
  status: 'pending' | 'filled' | 'cancelled' | 'rejected';
  created_at: string;
  filled_at?: string;
}

export interface OrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: 'market' | 'limit';
  limit_price?: number;
}

export interface OrderResult {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  filled_price: number;
  status: string;
  filled_at: string;
  cash_remaining: number;
}

export interface EquityCurvePoint {
  date: string;
  value: number;
}

async function fetchWithAuth(path: string, options: RequestInit = {}) {
  const res = await fetch(`${BASE_URL}/api/paper-trading${path}`, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const paperTradingApi = {
  getPortfolio: (): Promise<Portfolio> =>
    fetchWithAuth('/portfolio'),

  getPositions: (): Promise<{ positions: Position[]; total_market_value: number }> =>
    fetchWithAuth('/positions'),

  getOrders: (limit = 50): Promise<{ orders: Order[] }> =>
    fetchWithAuth(`/orders?limit=${limit}`),

  getEquityCurve: (): Promise<{ equity_curve: EquityCurvePoint[] }> =>
    fetchWithAuth('/equity-curve'),

  submitOrder: (req: OrderRequest): Promise<OrderResult> =>
    fetchWithAuth('/orders', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  resetPortfolio: (): Promise<{ message: string }> =>
    fetchWithAuth('/reset', { method: 'POST' }),
};

export async function cancelOrder(orderId: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/paper-trading/orders/${orderId}`, {
    method: 'DELETE',
    credentials: 'include',
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Cancel failed' }));
    throw new Error(err.detail || 'Cancel failed');
  }
}
