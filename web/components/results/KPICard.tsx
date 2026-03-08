interface KPICardProps {
  label: string
  value: string
  positive?: boolean | null
}

export function KPICard({ label, value, positive }: KPICardProps) {
  const valueColor =
    positive === true ? 'text-[#26a69a]' :
    positive === false ? 'text-[#ef5350]' :
    'text-gray-100'

  return (
    <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6">
      <p className="text-[#9ca3af] text-sm mb-1">{label}</p>
      <p className={`text-xl lg:text-lg font-mono font-semibold ${valueColor}`}>{value}</p>
    </div>
  )
}
