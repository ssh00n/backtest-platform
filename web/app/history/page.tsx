'use client'

import { useEffect, useState } from 'react'
import { ArrowUpRight, ArrowDownRight, Clock, TrendingUp, History } from 'lucide-react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api'

interface BacktestRun {
  id: string
  created_at: string
  start_date: string
  end_date: string
  initial_capital: number
  max_positions: number
  position_size_pct: number
  status: string
  total_return_pct: number | null
  total_trades: number | null
  win_rate_pct: number | null
  sharpe_ratio: number | null
  max_drawdown_pct: number | null
}

export default function HistoryPage() {
  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/history/`)
      .then(r => r.json())
      .then(d => { setRuns(d.runs || []); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  const fmt = (v: number | null, decimals = 2, suffix = '') =>
    v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(decimals)}${suffix}`

  return (
    <div className="min-h-screen bg-[#0f1117] text-[#f3f4f6]">

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="flex items-center gap-3 mb-6">
          <History className="text-[#26a69a]" size={24} />
          <h1 className="text-2xl font-bold">Backtest History</h1>
          <span className="ml-auto text-sm text-[#9ca3af]">{runs.length} runs</span>
        </div>

        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#26a69a]" />
          </div>
        )}

        {error && (
          <div className="bg-[#ef535020] border border-[#ef5350] rounded-lg p-4 text-[#ef5350]">
            Failed to load history: {error}
          </div>
        )}

        {!loading && !error && runs.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 text-[#9ca3af]">
            <Clock size={40} className="mb-3 opacity-40" />
            <p className="text-lg">No backtest runs yet</p>
            <Link href="/strategy" className="mt-4 text-[#26a69a] hover:underline text-sm">
              Run your first backtest →
            </Link>
          </div>
        )}

        {!loading && runs.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-[#1f2937]">
            <table className="w-full text-sm">
              <thead className="bg-[#111827] border-b border-[#1f2937]">
                <tr>
                  {['Date', 'Period', 'Capital', 'Return', 'Trades', 'Win Rate', 'Sharpe', 'Max DD', ''].map(h => (
                    <th key={h} className="px-4 py-3 text-left text-[#9ca3af] font-medium whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r, i) => {
                  const ret = r.total_return_pct
                  const isProfit = ret != null && ret >= 0
                  return (
                    <tr key={r.id} className={`border-b border-[#1f2937] hover:bg-[#111827] transition-colors ${i % 2 === 0 ? '' : 'bg-[#0f1117]'}`}>
                      <td className="px-4 py-3 text-[#9ca3af] whitespace-nowrap">
                        {new Date(r.created_at).toLocaleDateString('ko-KR', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap font-mono text-xs">
                        {r.start_date} ~ {r.end_date}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        ${r.initial_capital.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`flex items-center gap-1 font-semibold ${isProfit ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                          {isProfit ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                          {fmt(ret, 2, '%')}
                        </span>
                      </td>
                      <td className="px-4 py-3">{r.total_trades ?? '—'}</td>
                      <td className="px-4 py-3">{r.win_rate_pct != null ? `${r.win_rate_pct.toFixed(1)}%` : '—'}</td>
                      <td className="px-4 py-3">{r.sharpe_ratio?.toFixed(2) ?? '—'}</td>
                      <td className="px-4 py-3 text-[#ef5350]">
                        {r.max_drawdown_pct != null ? `${r.max_drawdown_pct.toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/results/${r.id}`}
                          className="flex items-center gap-1 text-[#26a69a] hover:underline whitespace-nowrap text-xs"
                        >
                          View <ArrowUpRight size={12} />
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <Link
            href="/strategy"
            className="bg-[#26a69a] hover:bg-[#2bbbad] text-white font-medium px-5 py-2.5 rounded-lg text-sm transition-colors flex items-center gap-2"
          >
            <TrendingUp size={16} />
            New Backtest
          </Link>
        </div>
      </main>
    </div>
  )
}
