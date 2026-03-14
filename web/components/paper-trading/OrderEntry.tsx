'use client';

import { useState, useEffect } from 'react';
import { Order, OrderRequest } from '@/lib/paper-trading-api';

interface Props {
  onSubmit: (req: OrderRequest) => Promise<string>;
  submitting: boolean;
  prefilledSymbol?: string;
  buyingPower: number;
  pendingOrders?: Order[];
}

type Side = 'buy' | 'sell';
type OrderType = 'market' | 'limit';

function fmt(n: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);
}

function useMarketStatus() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    function check() {
      const now = new Date();
      const nyTime = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
      const day = nyTime.getDay(); // 0=Sun, 6=Sat
      if (day === 0 || day === 6) { setIsOpen(false); return; }
      const minutes = nyTime.getHours() * 60 + nyTime.getMinutes();
      setIsOpen(minutes >= 9 * 60 + 30 && minutes < 16 * 60);
    }
    check();
    const t = setInterval(check, 30_000);
    return () => clearInterval(t);
  }, []);

  return isOpen;
}

export function OrderEntry({ onSubmit, submitting, prefilledSymbol, buyingPower, pendingOrders }: Props) {
  const [symbol, setSymbol] = useState(prefilledSymbol ?? '');
  const [side, setSide] = useState<Side>('buy');
  const [qty, setQty] = useState('');
  const [orderType, setOrderType] = useState<OrderType>('market');
  const [limitPrice, setLimitPrice] = useState('');
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const marketOpen = useMarketStatus();
  const hasPendingBuys = pendingOrders?.some(o => o.side === 'buy' && o.status === 'pending') ?? false;

  useEffect(() => {
    if (prefilledSymbol) setSymbol(prefilledSymbol);
  }, [prefilledSymbol]);

  const estCost = Number(qty) > 0 ? Number(qty) * (orderType === 'limit' && limitPrice ? Number(limitPrice) : 0) : 0;
  const canSubmit = symbol.trim() && Number(qty) > 0 && !submitting &&
    (orderType === 'market' || (orderType === 'limit' && Number(limitPrice) > 0));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const msg = await onSubmit({
        symbol: symbol.trim().toUpperCase(),
        side,
        qty: Number(qty),
        order_type: orderType,
        limit_price: orderType === 'limit' ? Number(limitPrice) : undefined,
      });
      setToast({ msg, ok: true });
      setQty('');
      setLimitPrice('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Order failed';
      setToast({ msg, ok: false });
    } finally {
      setTimeout(() => setToast(null), 4000);
    }
  }

  return (
    <div className="bg-[#111827] rounded-xl p-6 flex flex-col gap-4 xl:sticky xl:top-6">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold">📋 Order Entry</h3>
        {marketOpen ? (
          <span className="text-[#26a69a] text-xs">🟢 Market Open</span>
        ) : (
          <span className="text-[#ef5350] text-xs">🔴 Market Closed · Orders will fill at open</span>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className={`text-sm px-3 py-2 rounded-lg font-medium ${
          toast.ok ? 'bg-[#26a69a]/10 text-[#26a69a]' : 'bg-[#ef5350]/10 text-[#ef5350]'
        }`}>
          {toast.msg}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {/* Symbol Input */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Stock Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL"
            maxLength={10}
            className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-4 py-3
                       text-white placeholder-gray-500 font-mono uppercase
                       focus:border-[#26a69a] focus:ring-1 focus:ring-[#26a69a]/20 outline-none transition"
          />
        </div>

        {/* Buy / Sell Toggle */}
        <div className="flex gap-2">
          {(['buy', 'sell'] as Side[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={`flex-1 py-2 rounded-lg font-semibold text-sm uppercase transition-colors ${
                side === s
                  ? s === 'buy'
                    ? 'bg-[#26a69a] text-white'
                    : 'bg-[#ef5350] text-white'
                  : 'bg-[#1f2937] text-gray-400 hover:text-white'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Quantity */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Quantity (shares)</label>
          <input
            type="number"
            value={qty}
            onChange={(e) => setQty(e.target.value)}
            placeholder="0"
            min="1"
            step="1"
            className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-4 py-3
                       text-white font-mono focus:border-[#26a69a] focus:ring-1 focus:ring-[#26a69a]/20 outline-none transition"
          />
        </div>

        {/* Order Type */}
        <div>
          <label className="text-xs text-gray-400 mb-1 block">Order Type</label>
          <select
            value={orderType}
            onChange={(e) => setOrderType(e.target.value as OrderType)}
            className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-4 py-3
                       text-white focus:border-[#26a69a] outline-none transition"
          >
            <option value="market">Market</option>
            <option value="limit">Limit</option>
          </select>
        </div>

        {/* Limit Price (conditional) */}
        {orderType === 'limit' && (
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Limit Price ($)</label>
            <input
              type="number"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder="0.00"
              step="0.01"
              min="0.01"
              className="w-full bg-[#1f2937] border border-[#374151] rounded-lg px-4 py-3
                         text-white font-mono focus:border-[#26a69a] focus:ring-1 focus:ring-[#26a69a]/20 outline-none transition"
            />
          </div>
        )}

        {/* Estimated Cost */}
        {estCost > 0 && (
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Estimated Cost</span>
            <span className="text-white font-mono">{fmt(estCost)}</span>
          </div>
        )}

        {/* Buying Power */}
        <div className="flex justify-between text-sm">
          <span className="text-gray-400 flex items-center gap-1">
            Buying Power
            {hasPendingBuys && <span className="text-gray-500 text-xs">(잠정)</span>}
          </span>
          <span className="text-white font-mono">{fmt(buyingPower)}</span>
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={!canSubmit}
          className={`w-full py-3 rounded-lg font-semibold text-white transition-colors
            ${!canSubmit ? 'opacity-50 cursor-not-allowed' : ''}
            ${side === 'buy'
              ? 'bg-[#26a69a] hover:bg-[#2bbd9e]'
              : 'bg-[#ef5350] hover:bg-[#f06560]'
            }`}
        >
          {submitting ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              Processing...
            </span>
          ) : (
            `${side === 'buy' ? 'Buy' : 'Sell'} ${symbol || '—'}`
          )}
        </button>
      </form>

      <p className="text-xs text-gray-500 text-center">
        ⏰ Market orders fill during 9:30–16:00 ET
      </p>
    </div>
  );
}
