'use client';

import { Portfolio } from '@/lib/paper-trading-api';

interface Props {
  portfolio: Portfolio | null;
  loading: boolean;
}

function StatCard({
  label,
  value,
  subValue,
  colorClass = 'text-white',
}: {
  label: string;
  value: string;
  subValue?: string;
  colorClass?: string;
}) {
  return (
    <div className="bg-[#111827] rounded-xl p-6 flex flex-col gap-2">
      <p className="text-sm text-gray-400 font-medium">{label}</p>
      <p className={`text-2xl font-bold font-mono ${colorClass}`}>{value}</p>
      {subValue && <p className="text-xs text-gray-500">{subValue}</p>}
    </div>
  );
}

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function pctColor(n: number) {
  if (n > 0) return 'text-[#26a69a]';
  if (n < 0) return 'text-[#ef5350]';
  return 'text-white';
}

export function PortfolioOverview({ portfolio, loading }: Props) {
  if (loading || !portfolio) {
    return (
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-[#111827] rounded-xl p-6 animate-pulse h-28" />
        ))}
      </div>
    );
  }

  const { cash_balance, portfolio_value, total_return_pct, day_pnl, day_pnl_pct, buying_power } = portfolio;

  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
      <StatCard
        label="Total Balance"
        value={fmt(portfolio_value)}
        subValue={`Cash: ${fmt(cash_balance)}`}
        colorClass="text-white"
      />
      <StatCard
        label="Day P&L"
        value={`${day_pnl >= 0 ? '+' : ''}${fmt(day_pnl)}`}
        subValue={`${day_pnl_pct >= 0 ? '+' : ''}${day_pnl_pct.toFixed(2)}%`}
        colorClass={pctColor(day_pnl)}
      />
      <StatCard
        label="Total Return"
        value={`${total_return_pct >= 0 ? '+' : ''}${total_return_pct.toFixed(2)}%`}
        subValue={`${fmt(portfolio_value - portfolio.initial_capital)} vs initial`}
        colorClass={pctColor(total_return_pct)}
      />
      <StatCard
        label="Buying Power"
        value={fmt(buying_power)}
        subValue={`${((buying_power / portfolio_value) * 100).toFixed(1)}% available`}
        colorClass="text-white"
      />
    </div>
  );
}
