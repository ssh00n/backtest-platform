'use client';

import { useState } from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  defs,
  linearGradient,
  stop,
} from 'recharts';
import { EquityCurvePoint } from '@/lib/paper-trading-api';

interface Props {
  data: EquityCurvePoint[];
  loading: boolean;
}

type Period = '1W' | '1M' | 'ALL';

function filterByPeriod(data: EquityCurvePoint[], period: Period): EquityCurvePoint[] {
  if (period === 'ALL' || data.length === 0) return data;
  const now = new Date();
  const cutoff = new Date();
  if (period === '1W') cutoff.setDate(now.getDate() - 7);
  if (period === '1M') cutoff.setMonth(now.getMonth() - 1);
  return data.filter((d) => new Date(d.date) >= cutoff);
}

export function MiniEquityCurve({ data, loading }: Props) {
  const [period, setPeriod] = useState<Period>('ALL');
  const filtered = filterByPeriod(data, period);

  if (loading) {
    return <div className="bg-[#111827] rounded-xl p-6 animate-pulse h-40" />;
  }

  return (
    <div className="bg-[#111827] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-white font-semibold">📈 Equity Curve</h3>
        <div className="flex gap-1">
          {(['1W', '1M', 'ALL'] as Period[]).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`text-xs px-3 py-1 rounded-full transition-colors ${
                period === p
                  ? 'bg-[#26a69a]/20 text-[#26a69a]'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>
      {filtered.length < 2 ? (
        <div className="h-32 flex items-center justify-center text-gray-500 text-sm">
          No data yet. Place your first trade to start tracking!
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={filtered} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="ptGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#26a69a" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#26a69a" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: '#6b7280', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => v.slice(5)}
            />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              width={44}
            />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 8 }}
              labelStyle={{ color: '#9ca3af', fontSize: 11 }}
              itemStyle={{ color: '#26a69a', fontFamily: 'monospace' }}
              formatter={(v: number) =>
                new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v)
              }
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#26a69a"
              strokeWidth={2}
              fill="url(#ptGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
