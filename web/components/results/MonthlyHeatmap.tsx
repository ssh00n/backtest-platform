'use client'

interface EquityPoint { date: string; value: number }

interface Props {
  equityCurve: EquityPoint[]
  initialCapital: number
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function getColor(pct: number | null): string {
  if (pct === null) return '#1f2937'
  if (pct > 5) return '#1a6b5e'
  if (pct > 2) return '#1e8573'
  if (pct > 0.5) return '#26a69a'
  if (pct > -0.5) return '#374151'
  if (pct > -2) return '#8b3a3a'
  if (pct > -5) return '#b74343'
  return '#ef5350'
}

function getTextColor(pct: number | null): string {
  if (pct === null) return '#4b5563'
  return '#f3f4f6'
}

export default function MonthlyHeatmap({ equityCurve, initialCapital }: Props) {
  if (!equityCurve?.length) return null

  // 월별 첫날/마지막날 값 추출 → 월간 수익률 계산
  const monthlyMap: Record<string, { first: number; last: number }> = {}

  equityCurve.forEach(({ date, value }) => {
    const d = new Date(date)
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    if (!monthlyMap[key]) monthlyMap[key] = { first: value, last: value }
    else monthlyMap[key].last = value
  })

  const years = [...new Set(Object.keys(monthlyMap).map(k => k.split('-')[0]))].sort()

  const data: Record<string, Record<number, number | null>> = {}
  years.forEach(y => { data[y] = {} })
  Object.entries(monthlyMap).forEach(([key, { first, last }]) => {
    const [y, m] = key.split('-')
    data[y][parseInt(m)] = parseFloat(((last - first) / first * 100).toFixed(2))
  })

  return (
    <div className="bg-[#111827] rounded-xl border border-[#1f2937] p-5">
      <h3 className="text-sm font-semibold text-[#9ca3af] uppercase tracking-wider mb-4">
        Monthly Returns Heatmap
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-separate" style={{ borderSpacing: '2px' }}>
          <thead>
            <tr>
              <th className="text-left text-[#6b7280] pb-2 pr-3 font-normal">Year</th>
              {MONTHS.map(m => (
                <th key={m} className="text-center text-[#6b7280] pb-2 font-normal w-12">{m}</th>
              ))}
              <th className="text-center text-[#6b7280] pb-2 font-normal px-2">YTD</th>
            </tr>
          </thead>
          <tbody>
            {years.map(year => {
              const ytd = Object.values(data[year]).reduce((acc, v) => {
                if (v == null) return acc
                return (acc ?? 1) * (1 + v / 100)
              }, 1)
              const ytdPct = ((ytd ?? 1) - 1) * 100

              return (
                <tr key={year}>
                  <td className="text-[#9ca3af] pr-3 font-medium py-0.5">{year}</td>
                  {Array.from({ length: 12 }, (_, i) => i + 1).map(month => {
                    const val = data[year][month] ?? null
                    return (
                      <td key={month} className="text-center py-0.5">
                        <div
                          className="rounded px-1 py-1.5 mx-0.5 font-mono transition-opacity hover:opacity-80"
                          style={{
                            background: getColor(val),
                            color: getTextColor(val),
                            minWidth: '2.5rem',
                          }}
                        >
                          {val == null ? '' : `${val > 0 ? '+' : ''}${val.toFixed(1)}%`}
                        </div>
                      </td>
                    )
                  })}
                  <td className="text-center py-0.5">
                    <div
                      className="rounded px-1 py-1.5 mx-1 font-mono font-semibold"
                      style={{
                        background: getColor(ytdPct),
                        color: getTextColor(ytdPct),
                      }}
                    >
                      {`${ytdPct > 0 ? '+' : ''}${ytdPct.toFixed(1)}%`}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-2 mt-4 text-[10px] text-[#6b7280]">
        <span>Loss</span>
        {['#ef5350', '#b74343', '#8b3a3a', '#374151', '#26a69a', '#1e8573', '#1a6b5e'].map(c => (
          <div key={c} className="w-5 h-3 rounded" style={{ background: c }} />
        ))}
        <span>Gain</span>
      </div>
    </div>
  )
}
