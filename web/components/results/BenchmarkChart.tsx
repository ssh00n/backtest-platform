'use client'

import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  Tooltip, Legend, ReferenceLine, CartesianGrid
} from 'recharts'

interface EquityPoint { date: string; value: number }

interface Props {
  equityCurve: EquityPoint[]
  initialCapital: number
  spyBenchmark?: EquityPoint[] | null
}

interface TooltipProps {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-[#1f2937] border border-[#374151] rounded-lg p-3 text-sm shadow-xl">
      <p className="text-[#9ca3af] mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full" style={{ background: p.color }} />
          <span className="text-[#9ca3af]">{p.name}:</span>
          <span className="font-semibold" style={{ color: p.color }}>
            {p.value >= 0 ? '+' : ''}{p.value.toFixed(2)}%
          </span>
        </div>
      ))}
    </div>
  )
}

export default function BenchmarkChart({ equityCurve, initialCapital, spyBenchmark }: Props) {
  if (!equityCurve?.length) return null

  // 누적 수익률 % 변환
  const strategyData = equityCurve.map(pt => ({
    date: pt.date,
    strategy: parseFloat(((pt.value - initialCapital) / initialCapital * 100).toFixed(2)),
  }))

  // SPY 벤치마크가 있으면 병합, 없으면 strategy만
  const chartData = strategyData.map((d, i) => ({
    ...d,
    spy: spyBenchmark?.[i]
      ? parseFloat(((spyBenchmark[i].value - (spyBenchmark[0]?.value ?? 1)) / (spyBenchmark[0]?.value ?? 1) * 100).toFixed(2))
      : undefined,
  }))

  const tickFormatter = (dateStr: string) => {
    const d = new Date(dateStr)
    return `${d.getMonth() + 1}/${d.getDate()}`
  }

  return (
    <div className="bg-[#111827] rounded-xl border border-[#1f2937] p-5">
      <h3 className="text-sm font-semibold text-[#9ca3af] uppercase tracking-wider mb-4">
        Cumulative Return vs SPY
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: '#6b7280', fontSize: 11 }}
            tickFormatter={tickFormatter}
            interval="preserveStartEnd"
            minTickGap={50}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: '#6b7280', fontSize: 11 }}
            tickFormatter={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`}
            domain={['auto', 'auto']}
            axisLine={false}
            tickLine={false}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0} stroke="#374151" strokeDasharray="4 2" />
          <Legend
            wrapperStyle={{ fontSize: 12, color: '#9ca3af', paddingTop: 8 }}
            formatter={(value) => value === 'strategy' ? 'Darvas Box' : 'SPY (Benchmark)'}
          />
          <Line
            type="monotone"
            dataKey="strategy"
            stroke="#26a69a"
            dot={false}
            strokeWidth={2}
            name="strategy"
          />
          {spyBenchmark && (
            <Line
              type="monotone"
              dataKey="spy"
              stroke="#9ca3af"
              dot={false}
              strokeWidth={1.5}
              strokeDasharray="5 3"
              name="spy"
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
