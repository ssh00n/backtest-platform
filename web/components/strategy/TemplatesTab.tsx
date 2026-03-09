'use client'

import StrategyCard, { StrategyCardData } from './StrategyCard'
import StrategyParamsPanel from './StrategyParamsPanel'

const STRATEGIES: StrategyCardData[] = [
  {
    id: 'darvas_box',
    name: 'Darvas Box',
    category: 'Breakout',
    difficulty: 'Intermediate',
    icon: 'TrendingUp',
    description: 'Identify stocks making new highs forming box-shaped consolidation patterns, then buy on breakout.',
    winRate: '45–55%',
    sharpe: '0.5–1.2',
    boxPeriod: 55,
    engineType: 'Rule-Based' as const,
    defaultParams: {
      darvas_box_period: 55,
      volume_multiplier: 2.0,
      trailing_stop_r: 4.5,
      darvas_breakout_pct: 0.02,
      darvas_stop_loss_pct: 0.07,
      darvas_trailing_stop: true,
      use_events: false,
      max_positions: 5,
      position_size_pct: 0.2,
      strategy_name: 'darvas_box',
    },
  },
  {
    id: 'momentum',
    name: 'Momentum',
    category: 'Trend',
    difficulty: 'Beginner',
    icon: 'Zap',
    description: 'Buy stocks with strong recent price momentum. Simple and effective in trending markets.',
    winRate: '40–50%',
    sharpe: '0.3–0.9',
    boxPeriod: 20,
    engineType: 'Signal-Based' as const,
    defaultParams: {
      darvas_box_period: 20,
      volume_multiplier: 1.5,
      trailing_stop_r: 3.0,
      darvas_breakout_pct: 0.01,
      darvas_stop_loss_pct: 0.05,
      darvas_trailing_stop: true,
      use_events: false,
      max_positions: 8,
      position_size_pct: 0.15,
      strategy_name: 'momentum',
    },
  },
  {
    id: 'mean_reversion',
    name: 'Mean Reversion',
    category: 'Contrarian',
    difficulty: 'Advanced',
    icon: 'Activity',
    description: 'Trade pullbacks to mean. Enter when price is oversold relative to recent average.',
    winRate: '55–65%',
    sharpe: '0.6–1.4',
    boxPeriod: 30,
    engineType: 'Statistical' as const,
    defaultParams: {
      darvas_box_period: 30,
      volume_multiplier: 1.2,
      trailing_stop_r: 2.5,
      darvas_breakout_pct: 0.03,
      darvas_stop_loss_pct: 0.1,
      darvas_trailing_stop: false,
      use_events: true,
      max_positions: 4,
      position_size_pct: 0.25,
      strategy_name: 'mean_reversion',
    },
  },
]

interface Props {
  selectedTemplate: string | null
  onSelect: (templateId: string, params: Record<string, unknown>) => void
  params: Record<string, unknown>
  onParamChange: (key: string, value: unknown) => void
}

export default function TemplatesTab({ selectedTemplate, onSelect, params, onParamChange }: Props) {
  return (
    <div>
      <p className="text-sm text-[#94a3b8] mb-4">
        Choose a pre-built strategy template to get started quickly.
      </p>

      {/* 3-Column Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {STRATEGIES.map(s => (
          <StrategyCard
            key={s.id}
            strategy={s}
            isSelected={selectedTemplate === s.id}
            onSelect={onSelect}
          />
        ))}
      </div>

      {/* Parameters Panel — expands on card selection */}
      <StrategyParamsPanel
        params={params}
        onChange={onParamChange}
        isVisible={!!selectedTemplate}
      />
    </div>
  )
}
