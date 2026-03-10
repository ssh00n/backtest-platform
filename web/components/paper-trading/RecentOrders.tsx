'use client';

import { Order } from '@/lib/paper-trading-api';

interface Props {
  orders: Order[];
  loading: boolean;
}

const statusConfig = {
  filled: { label: '✅ Filled', className: 'bg-[#26a69a]/10 text-[#26a69a]' },
  pending: { label: '⏳ Pending', className: 'bg-[#f59e0b]/10 text-[#f59e0b]' },
  cancelled: { label: '❌ Cancelled', className: 'bg-[#ef5350]/10 text-[#ef5350]' },
  rejected: { label: '⛔ Rejected', className: 'bg-[#ef5350]/10 text-[#ef5350]' },
};

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  } catch {
    return '--:--';
  }
}

export function RecentOrders({ orders, loading }: Props) {
  if (loading) {
    return <div className="bg-[#111827] rounded-xl p-6 animate-pulse h-40" />;
  }

  return (
    <div className="bg-[#111827] rounded-xl overflow-hidden">
      <div className="px-6 py-4 border-b border-[#1f2937]">
        <h3 className="text-white font-semibold">📜 Recent Orders</h3>
      </div>
      {orders.length === 0 ? (
        <div className="px-6 py-8 text-center text-gray-500">No orders yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-[#1f2937]">
                <th className="px-4 py-3 text-left">Time</th>
                <th className="px-4 py-3 text-left">Ticker</th>
                <th className="px-4 py-3 text-left">Side</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => {
                const sideColor = order.side === 'buy' ? 'text-[#26a69a]' : 'text-[#ef5350]';
                const statusCfg = statusConfig[order.status] ?? statusConfig.pending;
                return (
                  <tr key={order.id} className="border-b border-[#1f2937] hover:bg-[#1f2937] transition-colors">
                    <td className="px-4 py-3 text-gray-400 font-mono">{formatTime(order.created_at)}</td>
                    <td className="px-4 py-3 text-white font-medium">{order.symbol}</td>
                    <td className={`px-4 py-3 font-semibold uppercase ${sideColor}`}>{order.side}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">{order.qty}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {order.filled_price ? fmt(order.filled_price) : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusCfg.className}`}>
                        {statusCfg.label}
                      </span>
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
