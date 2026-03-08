'use client'

import { Zap, TrendingDown, BarChart2, CheckCircle2 } from 'lucide-react'

const TEMPLATES = [
  {
    id: 'darvas_box',
    name: 'Darvas Box',
    category: 'Breakout',
    difficulty: 'Intermediate',
    difficultyColor: '#f59e0b',
    icon: BarChart2,
    description: 'Identify stocks making new highs forming box-shaped consolidation patterns, then buy on breakout.',
    tags: ['Trend Following', 'Momentum'],
    defaultParams: {
      darvas_box_period: 55,
      darvas_breakout_pct: 0.02,
      darvas_stop_loss_pct: 0.07,
      darvas_trailing_stop: true,
      max_positions: 5,
      position_size_pct: 0.2,
    },
    winRateHint: '45–55%',
    sharpHint: '0.5–1.2',
  },
  {
    id: 'momentum',
    name: 'Momentum',
    category: 'Momentum',
    difficulty: 'Beginner',
    difficultyColor: '#26a69a',
    icon: Zap,
    description: 'Buy stocks with strong recent price momentum. Simple and effective in trending markets.',
    tags: ['Momentum', 'Easy'],
    defaultParams: {
      darvas_box_period: 20,
      darvas_breakout_pct: 0.01,
      darvas_stop_loss_pct: 0.05,
      darvas_trailing_stop: true,
      max_positions: 8,
      position_size_pct: 0.15,
    },
    winRateHint: '40–50%',
    sharpHint: '0.3–0.9',
  },
  {
    id: 'mean_reversion',
    name: 'Mean Reversion',
    category: 'Mean Reversion',
    difficulty: 'Advanced',
    difficultyColor: '#ef5350',
    icon: TrendingDown,
    description: 'Trade pullbacks to mean. Enter when price is oversold relative to recent average.',
    tags: ['Contrarian', 'Range'],
    defaultParams: {
      darvas_box_period: 30,
      darvas_breakout_pct: 0.03,
      darvas_stop_loss_pct: 0.1,
      darvas_trailing_stop: false,
      max_positions: 4,
      position_size_pct: 0.25,
    },
    winRateHint: '55–65%',
    sharpHint: '0.6–1.4',
  },
]

interface Props {
  selectedTemplate: string | null
  onSelect: (templateId: string, params: Record<string, unknown>) => void
}

export default function TemplatesTab({ selectedTemplate, onSelect }: Props) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-[#9ca3af]">Choose a pre-built strategy template to get started quickly.</p>
      <div className="grid gap-3">
        {TEMPLATES.map(t => {
          const Icon = t.icon
          const isSelected = selectedTemplate === t.id
          return (
            <button
              key={t.id}
              onClick={() => onSelect(t.id, t.defaultParams)}
              className={`text-left w-full rounded-xl border p-4 transition-all ${
                isSelected
                  ? 'border-[#26a69a] bg-[#26a69a10]'
                  : 'border-[#1f2937] bg-[#0f1117] hover:border-[#374151]'
              }`}
            >
              <div className="flex items-start gap-4">
                <div className={`p-2 rounded-lg ${isSelected ? 'bg-[#26a69a20]' : 'bg-[#1f2937]'}`}>
                  <Icon size={20} className={isSelected ? 'text-[#26a69a]' : 'text-[#9ca3af]'} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold">{t.name}</span>
                    <span className="text-xs px-2 py-0.5 rounded-full border text-[#9ca3af] border-[#374151]">
                      {t.category}
                    </span>
                    <span className="text-xs font-medium" style={{ color: t.difficultyColor }}>
                      ● {t.difficulty}
                    </span>
                    {isSelected && <CheckCircle2 size={14} className="text-[#26a69a] ml-auto" />}
                  </div>
                  <p className="text-sm text-[#9ca3af] mt-1">{t.description}</p>
                  <div className="flex gap-4 mt-2 text-xs text-[#6b7280]">
                    <span>Win Rate: <span className="text-[#9ca3af]">{t.winRateHint}</span></span>
                    <span>Sharpe: <span className="text-[#9ca3af]">{t.sharpHint}</span></span>
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
