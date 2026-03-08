"""
Neon PostgreSQL 연결 + 백테스트 결과 저장/조회
psycopg3 (psycopg) 사용
"""
import json
import os
from datetime import datetime

import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg.connect(DATABASE_URL)


def init_db():
    """테이블 초기화 (idempotent)"""
    if not DATABASE_URL:
        print("[DB] DATABASE_URL not set, skipping init")
        return
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS backtest_runs (
                        id          TEXT PRIMARY KEY,
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        start_date  TEXT NOT NULL,
                        end_date    TEXT NOT NULL,
                        initial_capital NUMERIC NOT NULL,
                        max_positions   INTEGER,
                        position_size_pct NUMERIC,
                        status      TEXT NOT NULL DEFAULT 'running',
                        total_return_pct NUMERIC,
                        total_trades     INTEGER,
                        win_rate_pct     NUMERIC,
                        sharpe_ratio     NUMERIC,
                        max_drawdown_pct NUMERIC,
                        equity_curve     JSONB,
                        trades           JSONB,
                        metrics          JSONB,
                        spy_equity_curve JSONB
                    )
                """)
                # 기존 DB에 spy_equity_curve 컬럼 없을 경우 마이그레이션
                cur.execute("""
                    ALTER TABLE backtest_runs
                    ADD COLUMN IF NOT EXISTS spy_equity_curve JSONB
                """)
        print("[DB] init_db OK")
    except Exception as e:
        print(f"[DB] init_db error: {e}")


def save_result(backtest_id: str, request_params: dict, result: dict):
    """백테스트 결과 저장"""
    if not DATABASE_URL:
        return
    try:
        m = result.get("metrics", {}).get("basic", {})
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO backtest_runs
                        (id, start_date, end_date, initial_capital, max_positions,
                         position_size_pct, status, total_return_pct, total_trades,
                         win_rate_pct, sharpe_ratio, max_drawdown_pct, equity_curve, trades, metrics, spy_equity_curve)
                    VALUES (%s,%s,%s,%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                        status = 'completed',
                        total_return_pct = EXCLUDED.total_return_pct,
                        total_trades = EXCLUDED.total_trades,
                        win_rate_pct = EXCLUDED.win_rate_pct,
                        sharpe_ratio = EXCLUDED.sharpe_ratio,
                        max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                        equity_curve = EXCLUDED.equity_curve,
                        trades = EXCLUDED.trades,
                        metrics = EXCLUDED.metrics,
                        spy_equity_curve = EXCLUDED.spy_equity_curve
                """, (
                    backtest_id,
                    request_params.get("start_date"),
                    request_params.get("end_date"),
                    request_params.get("initial_capital", 100000),
                    request_params.get("max_positions", 5),
                    request_params.get("position_size_pct", 0.2),
                    m.get("total_return_pct"),
                    m.get("total_trades"),
                    m.get("win_rate_pct"),
                    m.get("sharpe_ratio"),
                    m.get("max_drawdown_pct"),
                    json.dumps(result.get("equity_curve", [])),
                    json.dumps(result.get("trades", [])),
                    json.dumps(result.get("metrics", {})),
                    json.dumps(result.get("spy_equity_curve", [])),
                ))
        print(f"[DB] save_result OK: {backtest_id}")
    except Exception as e:
        print(f"[DB] save_result error: {e}")


def list_runs(limit: int = 20) -> list[dict]:
    """백테스트 실행 히스토리 조회"""
    if not DATABASE_URL:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, created_at, start_date, end_date, initial_capital,
                           max_positions, position_size_pct, status,
                           total_return_pct, total_trades, win_rate_pct,
                           sharpe_ratio, max_drawdown_pct
                    FROM backtest_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        print(f"[DB] list_runs error: {e}")
        return []


def get_run(backtest_id: str) -> dict | None:
    """단일 백테스트 결과 조회 (equity_curve, trades 포함)"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM backtest_runs WHERE id = %s", (backtest_id,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as e:
        print(f"[DB] get_run error: {e}")
        return None
