'use client';

import { useState } from 'react';
import { usePaperTrading } from '@/hooks/usePaperTrading';
import { PortfolioOverview } from '@/components/paper-trading/PortfolioOverview';
import { OrderEntry } from '@/components/paper-trading/OrderEntry';
import { PositionsTable } from '@/components/paper-trading/PositionsTable';
import { RecentOrders } from '@/components/paper-trading/RecentOrders';
import { MiniEquityCurve } from '@/components/paper-trading/MiniEquityCurve';

export default function PaperTradingPage() {
  const {
    portfolio,
    positions,
    orders,
    equityCurve,
    loading,
    submitting,
    submitOrder,
    resetPortfolio,
    syncNow,
  } = usePaperTrading();

  const [prefilledSymbol, setPrefilledSymbol] = useState<string | undefined>();
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    setResetting(true);
    try {
      await resetPortfolio();
    } finally {
      setResetting(false);
      setShowResetModal(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] text-white">

      <div className="max-w-[1400px] mx-auto px-4 py-6 space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Paper Trading</h1>
            <p className="text-sm text-gray-400 mt-1">Virtual portfolio with real market data</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => syncNow()}
              className="bg-[#26a69a]/10 text-[#26a69a] hover:bg-[#26a69a]/20 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            >
              🔄 Sync
            </button>
            <button
              onClick={() => setShowResetModal(true)}
              className="bg-[#ef5350]/10 text-[#ef5350] hover:bg-[#ef5350]/20 rounded-lg px-4 py-2 text-sm font-medium transition-colors"
            >
              🗑 Reset
            </button>
          </div>
        </div>

        {/* Portfolio Overview Cards */}
        <PortfolioOverview portfolio={portfolio} loading={loading} />

        {/* Main Layout: Left (charts + positions) | Right (order entry) */}
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
          {/* Left Column */}
          <div className="space-y-6">
            <MiniEquityCurve data={equityCurve} loading={loading} />
            <PositionsTable
              positions={positions}
              loading={loading}
              onSelectSymbol={(sym) => setPrefilledSymbol(sym)}
            />
          </div>

          {/* Right Column — Order Entry */}
          <OrderEntry
            onSubmit={submitOrder}
            submitting={submitting}
            prefilledSymbol={prefilledSymbol}
            buyingPower={portfolio?.buying_power ?? 0}
          />
        </div>

        {/* Recent Orders */}
        <RecentOrders orders={orders} loading={loading} />
      </div>
      </div>

      {/* Reset Confirm Modal */}
      {showResetModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#111827] rounded-2xl p-8 max-w-sm w-full mx-4 border border-[#1f2937]">
            <h2 className="text-xl font-bold text-white mb-3">Reset Portfolio?</h2>
            <p className="text-gray-400 text-sm mb-6">
              모든 포지션과 주문 기록이 초기화됩니다. 가상 자금이 $100,000으로 리셋돼요.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowResetModal(false)}
                className="flex-1 py-2 rounded-lg bg-[#1f2937] text-gray-300 hover:bg-[#374151] transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleReset}
                disabled={resetting}
                className="flex-1 py-2 rounded-lg bg-[#ef5350] hover:bg-[#f06560] text-white font-semibold transition-colors disabled:opacity-50"
              >
                {resetting ? '초기화 중...' : '리셋'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
