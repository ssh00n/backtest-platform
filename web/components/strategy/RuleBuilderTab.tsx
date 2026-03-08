'use client'

import { useState } from 'react'

// 엔진 지원 여부 표시
const ENTRY_CONDITIONS = [
  { label: 'Price breaks above 55-day high', supported: true },
  { label: 'Price breaks above 20-day high', supported: true },
  { label: 'Volume > 1.5x 20-day average', supported: true },
  { label: 'RSI crosses above 50', supported: false },
  { label: 'MACD bullish crossover', supported: false },
  { label: 'Price breaks above Bollinger upper band', supported: false },
]

const EXIT_CONDITIONS = [
  { label: 'Trailing stop 7%', supported: true },
  { label: 'Price drops below entry -7%', supported: true },
  { label: 'Hold for max 20 days', supported: true },
  { label: 'RSI > 80 (overbought)', supported: false },
  { label: 'Price touches Bollinger lower band', supported: false },
]

interface SliderProps {
  label: string; value: number; min: number; max: number; step: number
  format: (v: number) => string; onChange: (v: number) => void
}

function MiniSlider({ label, value, min, max, step, format, onChange }: SliderProps) {
  return (
    <div>
      <div className="flex justify-between mb-1">
        <span className="text-xs text-[#9ca3af]">{label}</span>
        <span className="text-xs font-mono text-[#f3f4f6]">{format(value)}</span>
      </div>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-[#26a69a]"
      />
    </div>
  )
}

interface Props {
  params: Record<string, unknown>
  onChange: (k: string, v: unknown) => void
}

export default function RuleBuilderTab({ params, onChange }: Props) {
  const [selectedEntries, setSelectedEntries] = useState<string[]>([ENTRY_CONDITIONS[0].label])
  const [selectedExits, setSelectedExits] = useState<string[]>([EXIT_CONDITIONS[0].label])

  const toggleCondition = (list: string[], setList: (v: string[]) => void, item: { label: string; supported: boolean }) => {
    if (!item.supported) return
    const label = item.label
    if (list.includes(label)) {
      if (list.length > 1) setList(list.filter(v => v !== label))
    } else {
      setList([...list, label])
    }
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-[#9ca3af]">Combine entry/exit conditions to define your custom strategy logic.</p>

      {/* Entry Conditions */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-[#26a69a]" />
          <span className="text-sm font-medium">Entry Conditions</span>
          <span className="text-xs text-[#6b7280] ml-auto">Select all that apply (AND)</span>
        </div>
        <div className="space-y-1.5">
          {ENTRY_CONDITIONS.map(c => {
            const isSelected = selectedEntries.includes(c.label)
            return (
              <button
                key={c.label}
                onClick={() => toggleCondition(selectedEntries, setSelectedEntries, c)}
                disabled={!c.supported}
                className={`w-full text-left text-sm px-3 py-2.5 rounded-lg border transition-colors flex items-center justify-between ${
                  !c.supported
                    ? 'border-[#1f2937] bg-[#0f1117] text-[#4b5563] cursor-not-allowed opacity-50'
                    : isSelected
                      ? 'border-[#26a69a] bg-[#26a69a10] text-[#f3f4f6]'
                      : 'border-[#1f2937] bg-[#0f1117] text-[#9ca3af] hover:border-[#374151]'
                }`}
              >
                <span>
                  <span className="mr-2">{isSelected ? '✓' : '○'}</span>
                  {c.label}
                </span>
                {!c.supported && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#f59e0b20] text-[#f59e0b] border border-[#f59e0b30] ml-2 shrink-0">
                    Soon
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Exit Conditions */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-[#ef5350]" />
          <span className="text-sm font-medium">Exit Conditions</span>
          <span className="text-xs text-[#6b7280] ml-auto">First triggered exits</span>
        </div>
        <div className="space-y-1.5">
          {EXIT_CONDITIONS.map(c => {
            const isSelected = selectedExits.includes(c.label)
            return (
              <button
                key={c.label}
                onClick={() => toggleCondition(selectedExits, setSelectedExits, c)}
                disabled={!c.supported}
                className={`w-full text-left text-sm px-3 py-2.5 rounded-lg border transition-colors flex items-center justify-between ${
                  !c.supported
                    ? 'border-[#1f2937] bg-[#0f1117] text-[#4b5563] cursor-not-allowed opacity-50'
                    : isSelected
                      ? 'border-[#ef5350] bg-[#ef535010] text-[#f3f4f6]'
                      : 'border-[#1f2937] bg-[#0f1117] text-[#9ca3af] hover:border-[#374151]'
                }`}
              >
                <span>
                  <span className="mr-2">{isSelected ? '✓' : '○'}</span>
                  {c.label}
                </span>
                {!c.supported && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-[#f59e0b20] text-[#f59e0b] border border-[#f59e0b30] ml-2 shrink-0">
                    Soon
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* Risk Params */}
      <div className="border border-[#1f2937] rounded-lg p-4 bg-[#0f1117] space-y-4">
        <span className="text-sm font-medium">Risk Parameters</span>
        <MiniSlider
          label="Take Profit (R-multiple)"
          value={Math.round(((params.darvas_breakout_pct as number) * 100 || 2) * 10) / 10}
          min={1} max={5} step={0.5}
          format={v => `${v.toFixed(1)}R`}
          onChange={v => onChange('darvas_breakout_pct', v / 100)}
        />
        <MiniSlider
          label="Stop Loss"
          value={Math.round(((params.darvas_stop_loss_pct as number) * 100 || 7) * 10) / 10}
          min={3} max={15} step={1}
          format={v => `${v.toFixed(0)}%`}
          onChange={v => onChange('darvas_stop_loss_pct', v / 100)}
        />
        {/* Toggles */}
        {[
          ['Trailing Stop', 'darvas_trailing_stop'],
          ['Volume Filter (>1.5x avg)', 'use_macro_filter'],
        ].map(([label, key]) => (
          <div key={key} className="flex items-center justify-between">
            <span className="text-xs text-[#9ca3af]">{label}</span>
            <button
              onClick={() => onChange(key, !params[key])}
              className={`relative inline-flex h-5 w-10 rounded-full transition-colors ${params[key] ? 'bg-[#26a69a]' : 'bg-[#374151]'}`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform mt-0.5 ${params[key] ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
