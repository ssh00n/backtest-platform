'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

const defaultConfig = {
  initial_capital: 100000,
  start_date: '2020-01-01',
  end_date: '2024-12-31',
  universe: 'sp500' as 'sp500' | 'sp500_400',
  event_filter_mode: 'earnings_block',
  risk_per_trade: 0.01,
}

const navItems = ['Dashboard', 'Backtest', 'Strategy', 'History']

export default function StrategyPage() {
  const router = useRouter()
  const [config, setConfig] = useState(defaultConfig)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = (k: string, v: string | number) =>
    setConfig(prev => ({ ...prev, [k]: v }))

  const handleRun = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...config, strategy: 'darvas_box' }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      router.push(`/backtest/${data.backtest_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start backtest')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-6">
      {/* Nav */}
      <nav className="flex items-center gap-6 mb-8 pb-4 border-b border-gray-800">
        <span className="font-bold text-emerald-400 text-lg">WFS</span>
        {navItems.map(tab => (
          <span
            key={tab}
            className={`text-sm cursor-pointer transition-colors ${
              tab === 'Strategy' ? 'text-emerald-400' : 'text-gray-400 hover:text-gray-100'
            }`}
          >
            {tab}
          </span>
        ))}
      </nav>

      <div className="max-w-xl mx-auto">
        <h1 className="text-xl font-semibold mb-6">Strategy Setup</h1>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-5">
          {/* Strategy */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Strategy</label>
            <select className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:ring-1 focus:ring-emerald-500">
              <option value="darvas_box">Darvas Box</option>
            </select>
          </div>

          {/* Universe */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Universe</label>
            <select
              value={config.universe}
              onChange={e => update('universe', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="sp500">S&P 500</option>
              <option value="sp500_400">S&P 500 + S&P 400</option>
            </select>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            {[['Start Date', 'start_date'], ['End Date', 'end_date']] as const}
              { /* eslint-disable-next-line @typescript-eslint/no-explicit-any */ }
            {([['Start Date', 'start_date'], ['End Date', 'end_date']] as [string, string][]).map(([label, key]) => (
              <div key={key}>
                <label className="text-gray-400 text-sm block mb-1">{label}</label>
                <input
                  type="date"
                  value={(config as Record<string, string | number>)[key] as string}
                  onChange={e => update(key, e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                />
              </div>
            ))}
          </div>

          {/* Capital */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Initial Capital ($)</label>
            <input
              type="number"
              value={config.initial_capital}
              min={10000}
              max={10000000}
              step={10000}
              onChange={e => update('initial_capital', Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 font-mono focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          {/* Risk per trade */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">
              Risk per Trade ({(config.risk_per_trade * 100).toFixed(1)}%)
            </label>
            <input
              type="range"
              min={0.001}
              max={0.05}
              step={0.001}
              value={config.risk_per_trade}
              onChange={e => update('risk_per_trade', Number(e.target.value))}
              className="w-full accent-emerald-500"
            />
          </div>

          {/* Event Filter */}
          <div>
            <label className="text-gray-400 text-sm block mb-1">Event Filter</label>
            <select
              value={config.event_filter_mode}
              onChange={e => update('event_filter_mode', e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            >
              <option value="earnings_block">Earnings Block</option>
              <option value="miss_block">Miss Block</option>
              <option value="no_event_only">No Event Only</option>
              <option value="none">None</option>
            </select>
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-800 rounded-lg px-4 py-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <button
            onClick={handleRun}
            disabled={loading}
            className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-xl font-semibold text-sm transition-colors"
          >
            {loading ? 'Starting...' : '▶ Run Backtest'}
          </button>
        </div>
      </div>
    </div>
  )
}
