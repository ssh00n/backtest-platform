'use client'

import { useState } from 'react'
import { TrendingUp } from 'lucide-react'

interface Indicator {
  id: string
  name: string
  description: string
  params: { key: string; label: string; min: number; max: number; step: number; default: number; format?: (v: number) => string }[]
}

const INDICATORS: Indicator[] = [
  {
    id: 'ma',
    name: 'Moving Average',
    description: 'Trend direction filter',
    params: [{ key: 'ma_period', label: 'Period', min: 5, max: 200, step: 5, default: 20 }],
  },
  {
    id: 'rsi',
    name: 'RSI',
    description: 'Momentum oscillator (14)',
    params: [
      { key: 'rsi_period', label: 'Period', min: 5, max: 30, step: 1, default: 14 },
      { key: 'rsi_overbought', label: 'Overbought', min: 60, max: 90, step: 5, default: 70, format: v => `${v}` },
    ],
  },
  {
    id: 'bollinger',
    name: 'Bollinger Bands',
    description: 'Volatility-based envelope',
    params: [
      { key: 'bb_period', label: 'Period', min: 10, max: 50, step: 5, default: 20 },
      { key: 'bb_std', label: 'Std Dev', min: 1.5, max: 3.0, step: 0.5, default: 2.0, format: v => v.toFixed(1) },
    ],
  },
  {
    id: 'macd',
    name: 'MACD',
    description: 'Trend + momentum',
    params: [
      { key: 'macd_fast', label: 'Fast', min: 5, max: 20, step: 1, default: 12 },
      { key: 'macd_slow', label: 'Slow', min: 15, max: 50, step: 1, default: 26 },
    ],
  },
]

interface Props {
  params: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}

export default function IndicatorsTab({ params, onChange }: Props) {
  const [selected, setSelected] = useState<string[]>(['ma'])
  const [localParams, setLocalParams] = useState<Record<string, number>>({
    ma_period: 20,
    rsi_period: 14, rsi_overbought: 70,
    bb_period: 20, bb_std: 2.0,
    macd_fast: 12, macd_slow: 26,
  })

  const toggle = (id: string) => {
    setSelected(prev =>
      prev.includes(id) ? prev.filter(v => v !== id) : [...prev, id]
    )
  }

  const updateParam = (key: string, value: number) => {
    setLocalParams(prev => ({ ...prev, [key]: value }))
    onChange(key, value)
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[#9ca3af]">Select technical indicators to filter and confirm trade signals.</p>
      <div className="grid gap-3">
        {INDICATORS.map(ind => {
          const isSelected = selected.includes(ind.id)
          return (
            <div
              key={ind.id}
              className={`rounded-xl border transition-all ${
                isSelected ? 'border-[#26a69a]' : 'border-[#1f2937]'
              } bg-[#0f1117]`}
            >
              {/* Header */}
              <button
                onClick={() => toggle(ind.id)}
                className="w-full flex items-center gap-3 p-4 text-left"
              >
                <div className={`p-1.5 rounded-lg ${isSelected ? 'bg-[#26a69a20]' : 'bg-[#1f2937]'}`}>
                  <TrendingUp size={16} className={isSelected ? 'text-[#26a69a]' : 'text-[#9ca3af]'} />
                </div>
                <div className="flex-1">
                  <span className="font-medium text-sm">{ind.name}</span>
                  <p className="text-xs text-[#6b7280]">{ind.description}</p>
                </div>
                <div className={`w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                  isSelected ? 'bg-[#26a69a] border-[#26a69a]' : 'border-[#374151]'
                }`}>
                  {isSelected && <span className="text-white text-xs leading-none">✓</span>}
                </div>
              </button>

              {/* Params (expanded when selected) */}
              {isSelected && (
                <div className="px-4 pb-4 border-t border-[#1f2937] pt-3 space-y-3">
                  {ind.params.map(p => (
                    <div key={p.key}>
                      <div className="flex justify-between mb-1">
                        <span className="text-xs text-[#9ca3af]">{p.label}</span>
                        <span className="text-xs font-mono text-[#f3f4f6]">
                          {p.format ? p.format(localParams[p.key] ?? p.default) : (localParams[p.key] ?? p.default)}
                        </span>
                      </div>
                      <input
                        type="range"
                        min={p.min} max={p.max} step={p.step}
                        value={localParams[p.key] ?? p.default}
                        onChange={e => updateParam(p.key, Number(e.target.value))}
                        className="w-full accent-[#26a69a]"
                      />
                      <div className="flex justify-between text-[10px] text-[#4b5563] mt-0.5">
                        <span>{p.format ? p.format(p.min) : p.min}</span>
                        <span>{p.format ? p.format(p.max) : p.max}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="text-xs text-[#6b7280] bg-[#1f2937] rounded-lg p-3">
        💡 선택한 지표들은 진입 신호 필터로 동작합니다. 지표가 많을수록 신호가 엄격해져 거래 횟수가 줄어들 수 있어요.
      </div>
    </div>
  )
}
