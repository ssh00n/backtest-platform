'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { BarChart2, History, Layers, Settings2, BarChart } from 'lucide-react'
import TemplatesTab from '@/components/strategy/TemplatesTab'
import RuleBuilderTab from '@/components/strategy/RuleBuilderTab'
import IndicatorsTab from '@/components/strategy/IndicatorsTab'

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

const TABS = [
  { id: 'templates', label: 'Templates', icon: Layers, hint: 'Beginner' },
  { id: 'rules', label: 'Rule Builder', icon: Settings2, hint: 'Intermediate' },
  { id: 'indicators', label: 'Indicators', icon: BarChart, hint: 'Advanced' },
]

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
    </div>
  )
}

export default function StrategyPage() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState('templates')
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>('darvas_box')
  const [config, setConfig] = useState<Record<string, unknown>>(defaultConfig)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const update = (k: string, v: unknown) =>
    setConfig(prev => ({ ...prev, [k]: v }))

  const handleTemplateSelect = (templateId: string, params: Record<string, unknown>) => {
    setSelectedTemplate(templateId)
    setConfig(prev => ({ ...prev, ...params, strategy_name: templateId }))
  }

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
        <h1 className="text-xl font-bold mb-1">Strategy Builder</h1>
        <p className="text-sm text-[#9ca3af] mb-6">Build your trading strategy from templates, rules, or indicators</p>

        {/* 3-Tab Navigation */}
        <div className="flex gap-1 bg-[#111827] border border-[#1f2937] rounded-xl p-1 mb-5">
          {TABS.map(tab => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 px-3 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'bg-[#26a69a] text-white shadow-sm'
                    : 'text-[#9ca3af] hover:text-[#f3f4f6]'
                }`}
              >
                <Icon size={16} />
                <span>{tab.label}</span>
                <span className={`text-[10px] ${isActive ? 'text-white/70' : 'text-[#6b7280]'}`}>{tab.hint}</span>
              </button>
            )
          })}
        </div>

        {/* Tab Content */}
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5 mb-5">
          {activeTab === 'templates' && (
            <TemplatesTab selectedTemplate={selectedTemplate} onSelect={handleTemplateSelect} />
          )}
          {activeTab === 'rules' && (
            <RuleBuilderTab params={config} onChange={update} />
          )}
          {activeTab === 'indicators' && (
            <IndicatorsTab params={config} onChange={update} />
          )}
        </div>

        {/* Common Params */}
        <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-5 space-y-5 mb-5">
          <h3 className="text-sm font-semibold text-[#9ca3af] uppercase tracking-wider">Backtest Parameters</h3>

          {/* Universe */}
          <div>
            <label className="text-[#9ca3af] text-sm block mb-1.5">Universe</label>
            <select
              value={config.universe as string}
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
                  value={config[key] as string}
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
                value={config.initial_capital as number}
                min={10000} max={10000000} step={10000}
                onChange={e => update('initial_capital', Number(e.target.value))}
                className="w-full bg-[#1f2937] border border-[#374151] rounded-lg pl-7 pr-3 py-2.5 text-[#f3f4f6] font-mono focus:outline-none focus:ring-1 focus:ring-[#26a69a]"
              />
            </div>
          </div>

          <SliderField
            label="Position Size per Trade"
            value={config.position_size_pct as number}
            min={0.05} max={0.5} step={0.05}
            format={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => update('position_size_pct', v)}
          />
          <SliderField
            label="Max Positions"
            value={config.max_positions as number}
            min={1} max={20} step={1}
            onChange={v => update('max_positions', v)}
          />
        </div>

        {error && (
          <div className="bg-[#ef535020] border border-[#ef5350] rounded-lg px-4 py-3 text-[#ef5350] text-sm mb-4">
            {error}
          </div>
        )}

        <button
          onClick={handleRun}
          disabled={loading}
          className="w-full py-3.5 bg-[#26a69a] hover:bg-[#2bbbad] disabled:bg-[#374151] disabled:cursor-not-allowed rounded-xl font-semibold text-sm transition-colors flex items-center justify-center gap-2"
        >
          {loading ? (
            <>
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
              Starting Backtest...
            </>
          ) : '▶ Run Backtest'}
        </button>
      </div>
    </div>
  )
}
