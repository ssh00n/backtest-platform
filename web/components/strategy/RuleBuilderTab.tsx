'use client'

import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'

const ENTRY_CONDITIONS = [
  'Price breaks above 20-day high',
  'Price breaks above 55-day high',
  'RSI crosses above 50',
  'MACD bullish crossover',
  'Price breaks above Bollinger upper band',
  'Volume > 1.5x 20-day average',
]

const EXIT_CONDITIONS = [
  'Price drops below entry -7%',
  'Trailing stop 7%',
  'RSI > 80 (overbought)',
  'Price touches Bollinger lower band',
  'Hold for max 20 days',
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
  const [selectedEntries, setSelectedEntries] = useState<string[]>([ENTRY_CONDITIONS[0]])
  const [selectedExits, setSelectedExits] = useState<string[]>([EXIT_CONDITIONS[0]])

  const toggleCondition = (list: string[], setList: (v: string[]) => void, item: string) => {
    if (list.includes(item)) {
      if (list.length > 1) setList(list.filter(v => v !== item))
    } else {
      setList([...list, item])
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
          {ENTRY_CONDITIONS.map(c => (
            <button
              key={c}
              onClick={() => toggleCondition(selectedEntries, setSelectedEntries, c)}
              className={`w-full text-left text-sm px-3 py-2.5 rounded-lg border transition-colors ${
                selectedEntries.includes(c)
                  ? 'border-[#26a69a] bg-[#26a69a10] text-[#f3f4f6]'
                  : 'border-[#1f2937] bg-[#0f1117] text-[#9ca3af] hover:border-[#374151]'
              }`}
            >
              <span className="mr-2">{selectedEntries.includes(c) ? '✓' : '○'}</span>
              {c}
            </button>
          ))}
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
          {EXIT_CONDITIONS.map(c => (
            <button
              key={c}
              onClick={() => toggleCondition(selectedExits, setSelectedExits, c)}
              className={`w-full text-left text-sm px-3 py-2.5 rounded-lg border transition-colors ${
                selectedExits.includes(c)
                  ? 'border-[#ef5350] bg-[#ef535010] text-[#f3f4f6]'
                  : 'border-[#1f2937] bg-[#0f1117] text-[#9ca3af] hover:border-[#374151]'
              }`}
            >
              <span className="mr-2">{selectedExits.includes(c) ? '✓' : '○'}</span>
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Risk Params */}
      <div className="border border-[#1f2937] rounded-lg p-4 bg-[#0f1117] space-y-4">
        <span className="text-sm font-medium">Risk Parameters</span>
        <MiniSlider
          label="Take Profit (R-multiple)"
          value={(params.darvas_breakout_pct as number) * 100 || 2}
          min={1} max={5} step={0.5}
          format={v => `${v}R`}
          onChange={v => onChange('darvas_breakout_pct', v / 100)}
        />
        <MiniSlider
          label="Stop Loss"
          value={(params.darvas_stop_loss_pct as number) * 100 || 7}
          min={3} max={15} step={1}
          format={v => `${v}%`}
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
