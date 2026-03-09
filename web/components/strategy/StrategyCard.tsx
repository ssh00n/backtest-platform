'use client'

import { TrendingUp, Zap, Activity } from 'lucide-react'

export interface StrategyCardData {
  id: string
  name: string
  category: string
  difficulty: string
  icon: 'TrendingUp' | 'Zap' | 'Activity'
  description: string
  winRate: string
  sharpe: string
  boxPeriod: number
  engineType: 'Rule-Based' | 'Signal-Based' | 'Statistical'
  defaultParams: Record<string, unknown>
}

const ICON_MAP = { TrendingUp, Zap, Activity }

interface Props {
  strategy: StrategyCardData
  isSelected: boolean
  onSelect: (id: string, params: Record<string, unknown>) => void
}

export default function StrategyCard({ strategy, isSelected, onSelect }: Props) {
  const Icon = ICON_MAP[strategy.icon]

  return (
    <div
      onClick={() => onSelect(strategy.id, strategy.defaultParams)}
      className={`
        rounded-xl p-6 cursor-pointer transition-all duration-200
        ${isSelected
          ? 'bg-[#111827] border-2 border-[#26a69a] shadow-[0_0_12px_rgba(38,166,154,0.15)]'
          : 'bg-[#111827] border border-[#1f2937] hover:border-[#374151] hover:scale-[1.01]'
        }
      `}
    >
      <div className="flex flex-col gap-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className="w-5 h-5 text-[#26a69a]" />
            <h3 className="text-lg font-semibold text-white">{strategy.name}</h3>
          </div>
          {isSelected && (
            <div className="w-2 h-2 rounded-full bg-[#26a69a]" />
          )}
        </div>

        {/* Tags */}
        <div className="flex gap-2 flex-wrap">
          <span className="px-2 py-0.5 text-xs font-medium bg-[#1e293b] text-[#94a3b8] rounded-md">
            {strategy.category}
          </span>
          <span className={`px-2 py-0.5 text-xs font-medium rounded-md ${
            strategy.difficulty === 'Beginner'
              ? 'text-green-400 bg-green-400/10'
              : strategy.difficulty === 'Intermediate'
              ? 'text-yellow-400 bg-yellow-400/10'
              : 'text-red-400 bg-red-400/10'
          }`}>
            {strategy.difficulty}
          </span>
        </div>

        {/* Description */}
        <p className="text-sm text-[#94a3b8] leading-relaxed">{strategy.description}</p>

        {/* Metrics — box style */}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-[#1f2937]">
          <div className="bg-[#0f1117] rounded-lg p-2">
            <p className="text-xs text-[#64748b]">Win Rate</p>
            <p className="text-sm font-mono font-semibold text-white">{strategy.winRate}</p>
          </div>
          <div className="bg-[#0f1117] rounded-lg p-2">
            <p className="text-xs text-[#64748b]">Sharpe Ratio</p>
            <p className="text-sm font-mono font-semibold text-white">{strategy.sharpe}</p>
          </div>
        </div>

        {/* Engine Footer */}
        <p className="text-xs text-[#64748b] pt-2 border-t border-[#1f2937]">
          ⚙ Engine: {strategy.engineType}
        </p>
      </div>
    </div>
  )
}
