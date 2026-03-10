'use client';

import { useState, useEffect, useCallback } from 'react';
import { paperTradingApi, Portfolio, Position, Order, OrderRequest, EquityCurvePoint } from '@/lib/paper-trading-api';

export function usePaperTrading() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [totalMarketValue, setTotalMarketValue] = useState(0);
  const [orders, setOrders] = useState<Order[]>([]);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPortfolio = useCallback(async () => {
    try {
      const data = await paperTradingApi.getPortfolio();
      setPortfolio(data);
    } catch (e) {
      console.error('fetchPortfolio error:', e);
    }
  }, []);

  const fetchPositions = useCallback(async () => {
    try {
      const data = await paperTradingApi.getPositions();
      setPositions(data.positions);
      setTotalMarketValue(data.total_market_value);
    } catch (e) {
      console.error('fetchPositions error:', e);
    }
  }, []);

  const fetchOrders = useCallback(async () => {
    try {
      const data = await paperTradingApi.getOrders();
      setOrders(data.orders);
    } catch (e) {
      console.error('fetchOrders error:', e);
    }
  }, []);

  const fetchEquityCurve = useCallback(async () => {
    try {
      const data = await paperTradingApi.getEquityCurve();
      setEquityCurve(data.equity_curve);
    } catch (e) {
      console.error('fetchEquityCurve error:', e);
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchPortfolio(), fetchPositions(), fetchOrders(), fetchEquityCurve()]);
    setLoading(false);
  }, [fetchPortfolio, fetchPositions, fetchOrders, fetchEquityCurve]);

  // 초기 로드
  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // 5초 polling — positions + portfolio
  useEffect(() => {
    const interval = setInterval(() => {
      fetchPortfolio();
      fetchPositions();
    }, 5000);
    return () => clearInterval(interval);
  }, [fetchPortfolio, fetchPositions]);

  const submitOrder = useCallback(async (req: OrderRequest): Promise<string> => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await paperTradingApi.submitOrder(req);
      // 체결 후 전체 갱신
      await Promise.all([fetchPortfolio(), fetchPositions(), fetchOrders(), fetchEquityCurve()]);
      return `${result.symbol} ${result.qty}주 ${req.side === 'buy' ? '매수' : '매도'} 체결 ($${result.filled_price.toFixed(2)})`;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Order failed';
      setError(msg);
      throw new Error(msg);
    } finally {
      setSubmitting(false);
    }
  }, [fetchPortfolio, fetchPositions, fetchOrders, fetchEquityCurve]);

  const resetPortfolio = useCallback(async () => {
    try {
      await paperTradingApi.resetPortfolio();
      await fetchAll();
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Reset failed';
      setError(msg);
      throw new Error(msg);
    }
  }, [fetchAll]);

  const syncNow = useCallback(async () => {
    await fetchAll();
  }, [fetchAll]);

  return {
    portfolio,
    positions,
    totalMarketValue,
    orders,
    equityCurve,
    loading,
    submitting,
    error,
    submitOrder,
    resetPortfolio,
    syncNow,
  };
}
