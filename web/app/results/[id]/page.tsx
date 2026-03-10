'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { Navbar } from '@/components/common/Navbar'
import { KPICard } from '@/components/results/KPICard'
import { EquityCurve } from '@/components/results/EquityCurve'
import { TradeTable } from '@/components/results/TradeTable'
import BenchmarkChart from '@/components/results/BenchmarkChart'
import MonthlyHeatmap from '@/components/results/MonthlyHeatmap'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

interface BacktestData {
  backtest_id: string
  status: string
  metrics?: {
    basic?: {
      win_rate_pct?: number
      profit_factor?: number
      max_drawdown_pct?: number
      sharpe_ratio?: number
      total_trades?: number
      total_return_pct?: number
      initial_capital?: number
    }
  }
  equity_curve?: Array<{ date: string; value: number }>
  spy_equity_curve?: Array<{ date: string; value: number }>
  trades?: Array<{
    date: string
    symbol: string
    pnl_r: number
    exit_action: string
    event_type: string
  }>
  initial_capital?: number
}

export default function ResultsPage() {
  const params = useParams()
  const id = params.id as string
  const router = useRouter()
  const [data, setData] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API}/backtest/${id}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [id])

  if (loading) return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#26a69a]" />
    </div>
  )
  if (error) return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
      <p className="text-[#ef5350]">Error: {error}</p>
    </div>
  )
  if (!data) return null

  const m = data.metrics?.basic ?? {}
  const initialCapital = data.initial_capital ?? m.initial_capital ?? 100000
  const kpis = [
    { label: 'Total Return', value: `${m.total_return_pct?.toFixed(2) ?? '-'}%`, positive: (m.total_return_pct ?? 0) > 0 },
    { label: 'Sharpe Ratio', value: m.sharpe_ratio?.toFixed(2) ?? '-', positive: (m.sharpe_ratio ?? 0) > 1 },
    { label: 'Win Rate', value: `${m.win_rate_pct?.toFixed(1) ?? '-'}%`, positive: (m.win_rate_pct ?? 0) > 50 },
    { label: 'Profit Factor', value: m.profit_factor?.toFixed(2) ?? '-', positive: (m.profit_factor ?? 0) > 1 },
    { label: 'Max Drawdown', value: `${m.max_drawdown_pct?.toFixed(2) ?? '-'}%`, positive: null },
    { label: 'Total Trades', value: String(m.total_trades ?? '-'), positive: null },
  ]

  return (
    <div className="min-h-screen bg-[#0f1117] text-[#f3f4f6]">
      <Navbar />

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-xl font-bold">Backtest Results</h1>
            <p className="text-xs text-[#9ca3af] mt-0.5 font-mono">{id}</p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/history"
              className="px-4 py-2 bg-[#1f2937] hover:bg-[#374151] rounded-lg text-sm transition-colors"
            >
              History
            </Link>
            <button
              onClick={() => router.push('/strategy')}
              className="px-4 py-2 bg-[#26a69a] hover:bg-[#2bbbad] rounded-lg text-sm transition-colors font-medium"
            >
              Re-run
            </button>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
          {kpis.map(k => <KPICard key={k.label} {...k} />)}
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
          {/* Equity Curve */}
          <EquityCurve data={data.equity_curve ?? []} />
          {/* Benchmark Comparison */}
          <BenchmarkChart
            equityCurve={data.equity_curve ?? []}
            initialCapital={initialCapital}
            spyBenchmark={data.spy_equity_curve ?? null}
          />
        </div>

        {/* Monthly Heatmap */}
        <div className="mb-4">
          <MonthlyHeatmap
            equityCurve={data.equity_curve ?? []}
            initialCapital={initialCapital}
          />
        </div>

        {/* Trade Table */}
        <TradeTable trades={data.trades ?? []} />
      </main>
    </div>
  )
}
