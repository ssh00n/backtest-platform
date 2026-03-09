'use client'

interface SliderParam {
  key: string
  label: string
  min: number
  max: number
  step: number
  unit: string
  tooltip: string
}

const PARAMS: SliderParam[] = [
  {
    key: 'darvas_box_period',
    label: 'Box Period',
    min: 20,
    max: 100,
    step: 5,
    unit: '일',
    tooltip: 'Darvas Box 패턴 형성 기간. 높을수록 신호는 적지만 더 강한 돌파를 잡습니다.',
  },
  {
    key: 'volume_multiplier',
    label: 'Volume Multiplier',
    min: 1.0,
    max: 3.0,
    step: 0.1,
    unit: 'x',
    tooltip: '20일 평균 대비 최소 거래량 배수. 높을수록 강한 돌파 확인.',
  },
  {
    key: 'trailing_stop_r',
    label: 'R:R Ratio',
    min: 2.0,
    max: 8.0,
    step: 0.5,
    unit: '',
    tooltip: '목표 수익 대 리스크 비율. 4.5 = 손절 거리의 4.5배를 목표.',
  },
]

function Tooltip({ text }: { text: string }) {
  return (
    <div className="group relative inline-block">
      <span className="text-[#64748b] cursor-help text-xs">ℹ️</span>
      <div className="invisible group-hover:visible absolute z-10 bottom-full left-1/2 -translate-x-1/2 mb-2
        bg-[#1e293b] border border-[#334155] text-[#e2e8f0] text-xs rounded-md px-3 py-2
        max-w-[280px] whitespace-normal shadow-lg w-max">
        {text}
      </div>
    </div>
  )
}

interface Props {
  params: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
  isVisible: boolean
}

export default function StrategyParamsPanel({ params, onChange, isVisible }: Props) {
  return (
    <div className={`overflow-hidden transition-all duration-300 ease-in-out
      ${isVisible ? 'max-h-[600px] opacity-100 mt-6' : 'max-h-0 opacity-0'}`}>
      <div className="bg-[#111827] border border-[#1f2937] rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-4">Strategy Parameters</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {PARAMS.map(param => {
            const rawValue = params[param.key]
            const value = typeof rawValue === 'number' ? rawValue : param.min

            return (
              <div key={param.key} className="flex flex-col gap-2">
                {/* Label + Tooltip + Value */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1">
                    <label className="text-sm font-medium text-[#94a3b8]">{param.label}</label>
                    <Tooltip text={param.tooltip} />
                  </div>
                  <span className="text-sm font-mono font-semibold text-white">
                    {value}{param.unit}
                  </span>
                </div>

                {/* Range Slider */}
                <input
                  type="range"
                  min={param.min}
                  max={param.max}
                  step={param.step}
                  value={value}
                  onChange={e => onChange(param.key, Number(e.target.value))}
                  className="w-full h-1.5 rounded-full appearance-none bg-[#1f2937]
                    [&::-webkit-slider-thumb]:appearance-none
                    [&::-webkit-slider-thumb]:w-4
                    [&::-webkit-slider-thumb]:h-4
                    [&::-webkit-slider-thumb]:rounded-full
                    [&::-webkit-slider-thumb]:bg-[#26a69a]
                    [&::-webkit-slider-thumb]:cursor-pointer"
                />
              </div>
            )
          })}

          {/* Event Filter Toggle */}
          <div className="flex items-center justify-between p-3 bg-[#0f1117] rounded-lg">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-[#94a3b8]">Earnings Block</span>
              <Tooltip text="실적 발표 기간 중 신규 진입을 차단합니다. 변동성 리스크 감소에 효과적." />
            </div>
            <button
              onClick={() => onChange('use_events', !params['use_events'])}
              className={`relative w-10 h-5 rounded-full transition-colors duration-200
                ${params['use_events'] ? 'bg-[#26a69a]' : 'bg-[#374151]'}`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform duration-200
                ${params['use_events'] ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
