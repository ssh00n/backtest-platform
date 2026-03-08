interface Trade {
  date: string
  symbol: string
  pnl_r: number
  exit_action: string
  event_type: string
}

export function TradeTable({ trades }: { trades: Trade[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <h3 className="text-gray-100 font-semibold mb-4">Trade History</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-800">
              {['Date', 'Symbol', 'PnL (R)', 'Exit Action', 'Event'].map(h => (
                <th key={h} className="text-left pb-3 pr-4 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="py-2 pr-4 text-gray-300 font-mono">{t.date}</td>
                <td className="py-2 pr-4 text-gray-100 font-semibold">{t.symbol}</td>
                <td className={`py-2 pr-4 font-mono ${t.pnl_r >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {t.pnl_r >= 0 ? '+' : ''}{t.pnl_r}R
                </td>
                <td className="py-2 pr-4 text-gray-400">{t.exit_action}</td>
                <td className="py-2 text-gray-400">{t.event_type}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {trades.length === 0 && (
          <p className="text-gray-600 text-center py-8">No trades recorded</p>
        )}
      </div>
    </div>
  )
}
