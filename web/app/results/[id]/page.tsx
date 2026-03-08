'use client'
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { KPICard } from '@/components/results/KPICard'
import { EquityCurve } from '@/components/results/EquityCurve'
import { TradeTable } from '@/components/results/TradeTable'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

const navItems = ['Dashboard', 'Backtest', 'Strategy', 'History']

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
    }
  }
  equity_curve?: Array<{ date: string; value: number }>
  trades?: Array<{
    date: string
    symbol: string
    pnl_r: number
    exit_action: string
    event_type: string
  }>
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
      .then(d => {
        setData(d)
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }, [id])

  if (loading) return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
      <p className="text-gray-400">Loading results...</p>
    </div>
  )

  if (error) return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
      <p className="text-red-400">Error: {error}</p>
    </div>
  )

  if (!data) return null

  const m = data.metrics?.basic ?? {}
  const kpis = [
    { label: 'Win Rate', value: `${m.win_rate_pct?.toFixed(1) ?? '-'}%`, positive: (m.win_rate_pct ?? 0) > 50 },
    { label: 'Profit Factor', value: m.profit_factor?.toFixed(2) ?? '-', positive: (m.profit_factor ?? 0) > 1 },
    { label: 'Max Drawdown', value: `${m.max_drawdown_pct?.toFixed(1) ?? '-'}%`, positive: null },
    { label: 'Sharpe Ratio', value: m.sharpe_ratio?.toFixed(2) ?? '-', positive: (m.sharpe_ratio ?? 0) > 1 },
    { label: 'Total Trades', value: String(m.total_trades ?? '-'), positive: null },
    { label: 'Total Return', value: `${m.total_return_pct?.toFixed(1) ?? '-'}%`, positive: (m.total_return_pct ?? 0) > 0 },
  ]

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-6">
      {/* Nav */}
      <nav className="flex items-center gap-6 mb-8 pb-4 border-b border-gray-800">
        <span className="font-bold text-emerald-400 text-lg">WFS</span>
        {navItems.map(tab => (
          <span
            key={tab}
            className="text-gray-400 hover:text-gray-100 cursor-pointer text-sm transition-colors"
          >
            {tab}
          </span>
        ))}
      </nav>

      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-xl font-semibold">Backtest Results</h1>
        <div className="flex gap-3">
          <button className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors">
            Export CSV
          </button>
          <button
            onClick={() => router.push('/strategy')}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm transition-colors"
          >
            Re-run
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
        {kpis.map(k => <KPICard key={k.label} {...k} />)}
      </div>

      {/* Equity Curve */}
      <div className="mb-6">
        <EquityCurve data={data.equity_curve ?? []} />
      </div>

      {/* Trade Table */}
      <TradeTable trades={data.trades ?? []} />
    </div>
  )
}
