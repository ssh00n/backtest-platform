'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { BarChart2, ChevronDown, ChevronUp, History } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000/api'

const defaultConfig = {
  initial_capital: 100000,
  start_date: '2023-01-01',
  end_date: '2023-12-31',
  universe: 'sp500' as 'sp500' | 'sp500_400',
  event_filter_mode: 'none',
  max_positions: 5,
  position_size_pct: 0.2,
  use_events: false,
  use_macro_filter: false,
  // Darvas Box params
  darvas_box_period: 55,
  darvas_breakout_pct: 0.02,
  darvas_stop_loss_pct: 0.07,
  darvas_trailing_stop: true,
  strategy_name: 'darvas_box',
}

function SliderField({
  label, value, min, max, step, format, onChange
}: {
  label: string; value: number; min: number; max: number; step: number
  format?: (v: number) => string; onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <label className="text-[#9ca3af] text-sm">{label}</label>
        <span className="text-[#f3f4f6] text-sm font-mono font-medium">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-[#26a69a]"
      />
      <div className="flex justify-between text-[10px] text-[#4b5563] mt-0.5">
        <span>{format ? format(min) : min}</span>
        <span>{format ? format(max) : max}</span>
      </div>
    </div>
  )
}

export default function StrategyPage() {
  const router = useRouter()
  const [config, setConfig] = useState(defaultConfig)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const update = (k: string, v: string | number | boolean) =>
    setConfig(prev => ({ ...prev, [k]: v }))

  const handleRun = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API}/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
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
    <div className="min-h-screen bg-[#0f1117] text-[#f3f4f6]">
      {/* Nav */}
      <nav className="border-b border-[#1f2937] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BarChart2 className="text-[#26a69a]" size={22} />
          <span className="font-semibold text-lg tracking-tight">WFS Backtest</span>
        </div>
        <div className="flex gap-6 text-sm text-[#9ca3af]">
          <Link href="/strategy" className="text-[#26a69a] font-medium">Strategy</Link>
          <Link href="/history" className="hover:text-[#f3f4f6] transition-colors flex items-center gap-1">
            <History size={14} /> History
          </Link>
        </div>
      </nav>

      <div className="max-w-2xl mx-auto px-6 py-8">
        <h1 className="text-xl font-bold mb-2">Strategy Setup</h1>
        <p className="text-sm text-[#9ca3af] mb-6">Configure your backtest parameters and run the simulation</p>

        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6 space-y-5">
          {/* Strategy */}
          <div>
            <label className="text-[#9ca3af] text-sm block mb-1.5">Strategy</label>
            <select className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2.5 text-[#f3f4f6] focus:outline-none focus:ring-1 focus:ring-[#26a69a]">
              <option value="darvas_box">Darvas Box</option>
            </select>
          </div>

          {/* Universe */}
          <div>
            <label className="text-[#9ca3af] text-sm block mb-1.5">Universe</label>
            <select
              value={config.universe}
              onChange={e => update('universe', e.target.value)}
              className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2.5 text-[#f3f4f6] focus:outline-none focus:ring-1 focus:ring-[#26a69a]"
            >
              <option value="sp500">S&P 500 (503 stocks)</option>
              <option value="sp500_400">S&P 500 + S&P 400</option>
            </select>
          </div>

          {/* Dates */}
          <div className="grid grid-cols-2 gap-4">
            {([['Start Date', 'start_date'], ['End Date', 'end_date']] as [string, string][]).map(([label, key]) => (
              <div key={key}>
                <label className="text-[#9ca3af] text-sm block mb-1.5">{label}</label>
                <input
                  type="date"
                  value={(config as Record<string, string | number | boolean>)[key] as string}
                  onChange={e => update(key, e.target.value)}
                  className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2.5 text-[#f3f4f6] focus:outline-none focus:ring-1 focus:ring-[#26a69a]"
                />
              </div>
            ))}
          </div>

          {/* Capital */}
          <div>
            <label className="text-[#9ca3af] text-sm block mb-1.5">Initial Capital</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]">$</span>
              <input
                type="number"
                value={config.initial_capital}
                min={10000} max={10000000} step={10000}
                onChange={e => update('initial_capital', Number(e.target.value))}
                className="w-full bg-[#1f2937] border border-[#374151] rounded-lg pl-7 pr-3 py-2.5 text-[#f3f4f6] font-mono focus:outline-none focus:ring-1 focus:ring-[#26a69a]"
              />
            </div>
          </div>

          {/* Portfolio Params */}
          <SliderField
            label="Position Size per Trade"
            value={config.position_size_pct}
            min={0.05} max={0.5} step={0.05}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => update('position_size_pct', v)}
          />
          <SliderField
            label="Max Positions"
            value={config.max_positions}
            min={1} max={20} step={1}
            onChange={v => update('max_positions', v)}
          />

          {/* Event Filter */}
          <div>
            <label className="text-[#9ca3af] text-sm block mb-1.5">Event Filter</label>
            <select
              value={config.event_filter_mode}
              onChange={e => update('event_filter_mode', e.target.value)}
              className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-3 py-2.5 text-[#f3f4f6] focus:outline-none focus:ring-1 focus:ring-[#26a69a]"
            >
              <option value="none">None</option>
              <option value="earnings_block">Earnings Block</option>
              <option value="miss_block">Miss Block</option>
              <option value="no_event_only">No Event Only</option>
            </select>
          </div>

          {/* Advanced: Darvas Box params */}
          <div className="border-t border-[#1f2937] pt-4">
            <button
              onClick={() => setShowAdvanced(v => !v)}
              className="flex items-center gap-2 text-sm text-[#9ca3af] hover:text-[#f3f4f6] transition-colors w-full"
            >
              {showAdvanced ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              Advanced: Darvas Box Parameters
            </button>

            {showAdvanced && (
              <div className="mt-4 space-y-5 border border-[#1f2937] rounded-lg p-4 bg-[#0f1117]">
                <p className="text-xs text-[#6b7280]">Fine-tune the Darvas Box strategy parameters</p>

                <SliderField
                  label="Box Formation Period (candles)"
                  value={config.darvas_box_period}
                  min={20} max={120} step={5}
                  onChange={v => update('darvas_box_period', v)}
                />
                <SliderField
                  label="Breakout Buffer"
                  value={config.darvas_breakout_pct}
                  min={0.005} max={0.05} step={0.005}
                  format={v => `${(v * 100).toFixed(1)}%`}
                  onChange={v => update('darvas_breakout_pct', v)}
                />
                <SliderField
                  label="Stop Loss"
                  value={config.darvas_stop_loss_pct}
                  min={0.03} max={0.15} step={0.01}
                  format={v => `${(v * 100).toFixed(0)}%`}
                  onChange={v => update('darvas_stop_loss_pct', v)}
                />

                <div className="flex items-center justify-between">
                  <label className="text-[#9ca3af] text-sm">Trailing Stop</label>
                  <button
                    onClick={() => update('darvas_trailing_stop', !config.darvas_trailing_stop)}
                    className={`relative inline-flex h-6 w-11 rounded-full transition-colors ${config.darvas_trailing_stop ? 'bg-[#26a69a]' : 'bg-[#374151]'}`}
                  >
                    <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform mt-0.5 ${config.darvas_trailing_stop ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="bg-[#ef535020] border border-[#ef5350] rounded-lg px-4 py-3 text-[#ef5350] text-sm">
              {error}
            </div>
          )}

          <button
            onClick={handleRun}
            disabled={loading}
            className="w-full py-3 bg-[#26a69a] hover:bg-[#2bbbad] disabled:bg-[#374151] disabled:cursor-not-allowed rounded-xl font-semibold text-sm transition-colors flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                Starting...
              </>
            ) : '▶ Run Backtest'}
          </button>
        </div>
      </div>
    </div>
  )
}
