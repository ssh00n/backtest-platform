interface Trade {
  date: string
  symbol: string
  pnl_r: number
  exit_action: string
  event_type: string
}

function exportCSV(trades: Trade[]) {
  const headers = ['Date', 'Symbol', 'PnL (R)', 'Exit Action', 'Event']
  const rows = trades.map(t =>
    [t.date, t.symbol, t.pnl_r, t.exit_action, t.event_type].join(',')
  )
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `trades_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function TradeTable({ trades }: { trades: Trade[] }) {
  const showEventCol = trades.some(t => t.event_type && t.event_type !== '-')
  const headers = ['Date', 'Symbol', 'PnL (R)', 'Exit Action', ...(showEventCol ? ['Event'] : [])]

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[#f3f4f6] font-semibold">Trade History</h3>
        <button
          onClick={() => exportCSV(trades)}
          disabled={trades.length === 0}
          className="text-xs px-3 py-1.5 rounded-lg border border-[#1f2937] text-[#9ca3af] hover:text-gray-100 hover:border-gray-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          ↓ Export CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[#9ca3af] border-b border-[#1f2937]">
              {headers.map(h => (
                <th key={h} className="text-left pb-3 pr-4 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-[#1f2937]/50 hover:bg-gray-800/30 transition-colors">
                <td className="py-2 pr-4 text-gray-300 font-mono">{t.date}</td>
                <td className="py-2 pr-4 text-[#f3f4f6] font-semibold">{t.symbol}</td>
                <td className={`py-2 pr-4 font-mono ${t.pnl_r >= 0 ? 'text-[#26a69a]' : 'text-[#ef5350]'}`}>
                  {t.pnl_r >= 0 ? '+' : ''}{t.pnl_r}R
                </td>
                <td className="py-2 pr-4 text-[#9ca3af]">{t.exit_action}</td>
                {showEventCol && <td className="py-2 text-[#9ca3af]">{t.event_type}</td>}
              </tr>
            ))}
          </tbody>
        </table>

        {trades.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-[#9ca3af]">
            <svg className="w-10 h-10 mb-3 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-sm">No trades recorded</p>
            <p className="text-xs mt-1 opacity-60">Adjust your strategy parameters and run again</p>
          </div>
        )}
      </div>
    </div>
  )
}
