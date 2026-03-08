interface KPICardProps {
  label: string
  value: string
  positive?: boolean | null
}

export function KPICard({ label, value, positive }: KPICardProps) {
  const valueColor =
    positive === true ? 'text-emerald-400' :
    positive === false ? 'text-red-400' :
    'text-gray-100'

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <p className="text-gray-400 text-sm mb-1">{label}</p>
      <p className={`text-2xl font-mono font-semibold ${valueColor}`}>{value}</p>
    </div>
  )
}
