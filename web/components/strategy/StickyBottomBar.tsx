'use client'

interface Props {
  strategyName: string
  universe: string
  startDate: string
  endDate: string
  initialCapital: number
  loading: boolean
  onRun: () => void
}

export default function StickyBottomBar({
  strategyName,
  universe,
  startDate,
  endDate,
  initialCapital,
  loading,
  onRun,
}: Props) {
  const universeLabel = universe === 'sp500' ? 'S&P 500' : 'S&P 500+400'

  return (
    <>
      <div className="fixed bottom-0 left-0 right-0 z-50
        bg-[#111827]/95 backdrop-blur-sm border-t border-[#1f2937]
        px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {/* Left: Config Summary (desktop only) */}
          <div className="hidden md:flex items-center gap-3 text-sm text-[#94a3b8]">
            <span className="font-medium text-white">{strategyName || 'No Strategy'}</span>
            <span>•</span>
            <span>{universeLabel}</span>
            <span>•</span>
            <span>{startDate} ~ {endDate}</span>
            <span>•</span>
            <span className="font-mono">${initialCapital.toLocaleString()}</span>
          </div>

          {/* Mobile: just the button full width */}
          <div className="flex md:hidden w-full">
            <button
              onClick={onRun}
              disabled={loading}
              className="w-full px-6 py-2.5 rounded-lg font-semibold text-white
                bg-gradient-to-r from-[#26a69a] to-[#2dd4bf]
                hover:from-[#2dd4bf] hover:to-[#26a69a]
                disabled:from-[#374151] disabled:to-[#374151] disabled:cursor-not-allowed
                transition-all duration-200 shadow-lg shadow-[#26a69a]/20
                flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                  Starting...
                </>
              ) : '▶ Run Backtest'}
            </button>
          </div>

          {/* Desktop: CTA button */}
          <button
            onClick={onRun}
            disabled={loading}
            className="hidden md:flex px-6 py-2.5 rounded-lg font-semibold text-white
              bg-gradient-to-r from-[#26a69a] to-[#2dd4bf]
              hover:from-[#2dd4bf] hover:to-[#26a69a]
              disabled:from-[#374151] disabled:to-[#374151] disabled:cursor-not-allowed
              transition-all duration-200 shadow-lg shadow-[#26a69a]/20
              items-center gap-2"
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

      {/* Spacer for sticky bar */}
      <div className="pb-20" />
    </>
  )
}
