'use client'
import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/api'

const navItems = ['Dashboard', 'Backtest', 'Strategy', 'History']

export default function ProgressPage() {
  const params = useParams()
  const id = params.id as string
  const router = useRouter()
  const wsRef = useRef<WebSocket | null>(null)
  const [progress, setProgress] = useState(0)
  const [feed, setFeed] = useState<string[]>([])
  const [elapsed, setElapsed] = useState(0)
  const [done, setDone] = useState(false)
  const feedRef = useRef<HTMLDivElement>(null)
  const startTime = useRef(Date.now())

  // Elapsed timer
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startTime.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // WebSocket connection
  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/backtest/ws/${id}`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'progress') {
        setProgress(msg.progress_pct ?? 0)
        const line = `[${msg.current_date}] ${msg.symbols_processed}/${msg.total_symbols} symbols | ${msg.open_positions} open positions`
        setFeed(prev => [...prev.slice(-99), line])
      } else if (msg.type === 'completed') {
        setDone(true)
        setProgress(100)
        setFeed(prev => [...prev, '✅ Backtest completed! Redirecting...'])
        setTimeout(() => router.push(`/results/${msg.backtest_id}`), 1500)
      } else if (msg.type === 'error') {
        setFeed(prev => [...prev, `❌ Error: ${msg.message}`])
      }
    }

    ws.onerror = () => {
      setFeed(prev => [...prev, '❌ WebSocket connection error'])
    }

    return () => ws.close()
  }, [id, router])

  // Auto-scroll feed
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight
    }
  }, [feed])

  const handleCancel = () => {
    wsRef.current?.close() // A plan: disconnect WS only
    router.push('/strategy')
  }

  const fmt = (s: number) =>
    `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100 p-6">
      {/* Nav */}
      <nav className="flex items-center gap-6 mb-8 pb-4 border-b border-gray-800">
        <span className="font-bold text-emerald-400 text-lg">WFS</span>
        {navItems.map(tab => (
          <span key={tab} className="text-gray-400 text-sm cursor-pointer hover:text-gray-100 transition-colors">
            {tab}
          </span>
        ))}
      </nav>

      <div className="max-w-2xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-xl font-semibold">
            {done ? '✅ Backtest Complete' : 'Backtest Running...'}
          </h1>
          <span className="text-gray-400 font-mono text-sm">{fmt(elapsed)}</span>
        </div>

        {/* Progress Bar */}
        <div className="bg-gray-800 rounded-full h-3 mb-2 overflow-hidden">
          <div
            className="bg-emerald-500 h-3 rounded-full transition-all duration-700"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-gray-400 text-sm text-right mb-6">{progress.toFixed(0)}%</p>

        {/* Live Feed */}
        <div
          ref={feedRef}
          className="bg-gray-900 border border-gray-800 rounded-xl p-4 h-80 overflow-y-auto font-mono text-xs text-gray-400 mb-6"
        >
          {feed.length === 0 ? (
            <p className="text-gray-600">Connecting to backtest engine...</p>
          ) : (
            feed.map((line, i) => (
              <p key={i} className="mb-0.5 leading-relaxed">{line}</p>
            ))
          )}
        </div>

        {!done && (
          <button
            onClick={handleCancel}
            className="w-full py-3 bg-gray-800 hover:bg-gray-700 rounded-xl text-gray-300 text-sm transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}
