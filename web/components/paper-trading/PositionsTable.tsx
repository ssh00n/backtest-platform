'use client';

import { Position } from '@/lib/paper-trading-api';

interface Props {
  positions: Position[];
  loading: boolean;
  onSelectSymbol?: (symbol: string) => void;
}

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

export function PositionsTable({ positions, loading, onSelectSymbol }: Props) {
  if (loading) {
    return <div className="bg-[#111827] rounded-xl p-6 animate-pulse h-40" />;
  }

  return (
    <div className="bg-[#111827] rounded-xl overflow-hidden">
      <div className="px-6 py-4 border-b border-[#1f2937]">
        <h3 className="text-white font-semibold">📊 Open Positions</h3>
      </div>
      {positions.length === 0 ? (
        <div className="px-6 py-10 text-center text-gray-500">
          No open positions. Place your first order! 🚀
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-[#1f2937]">
                <th className="px-4 py-3 text-left">Ticker</th>
                <th className="px-4 py-3 text-right">Shares</th>
                <th className="px-4 py-3 text-right">Avg Cost</th>
                <th className="px-4 py-3 text-right">Current</th>
                <th className="px-4 py-3 text-right">P&L</th>
                <th className="px-4 py-3 text-right">Change</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const pnlColor = pos.unrealized_pnl >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]';
                return (
                  <tr
                    key={pos.symbol}
                    onClick={() => onSelectSymbol?.(pos.symbol)}
                    className="border-b border-[#1f2937] hover:bg-[#1f2937] cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 text-white font-bold">{pos.symbol}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{pos.shares}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{fmt(pos.avg_cost)}</td>
                    <td className="px-4 py-3 text-right text-white font-mono">{fmt(pos.current_price)}</td>
                    <td className={`px-4 py-3 text-right font-mono ${pnlColor}`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}{fmt(pos.unrealized_pnl)}
                    </td>
                    <td className={`px-4 py-3 text-right font-mono ${pnlColor}`}>
                      {pos.unrealized_pnl_pct >= 0 ? '+' : ''}{pos.unrealized_pnl_pct.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
