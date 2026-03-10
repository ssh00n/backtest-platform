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
                # users 테이블
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id            TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                        email         VARCHAR(255) UNIQUE NOT NULL,
                        username      VARCHAR(100) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        is_active     BOOLEAN DEFAULT TRUE,
                        created_at    TIMESTAMPTZ DEFAULT NOW(),
                        updated_at    TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                # refresh_tokens 테이블
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS refresh_tokens (
                        id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                        user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        token      TEXT UNIQUE NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                # backtest_runs 테이블
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
                # 마이그레이션: 기존 테이블에 컬럼 추가
                cur.execute("""
                    ALTER TABLE backtest_runs
                    ADD COLUMN IF NOT EXISTS spy_equity_curve JSONB
                """)
                cur.execute("""
                    ALTER TABLE backtest_runs
                    ADD COLUMN IF NOT EXISTS user_id TEXT REFERENCES users(id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS ix_backtest_runs_user_id
                    ON backtest_runs(user_id)
                """)
                # strategy_configs 테이블 (HOO-8)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS strategy_configs (
                        id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
                        user_id     TEXT REFERENCES users(id) ON DELETE SET NULL,
                        name        VARCHAR(255) NOT NULL,
                        strategy    VARCHAR(100) NOT NULL,
                        params      JSONB NOT NULL DEFAULT '{}',
                        is_public   BOOLEAN DEFAULT FALSE,
                        view_count  INTEGER DEFAULT 0,
                        created_at  TIMESTAMPTZ DEFAULT NOW(),
                        updated_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS ix_strategy_configs_user_id
                    ON strategy_configs(user_id)
                """)

                # ── Paper Trading 테이블 (HOO-9) ─────────────────────────────
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS paper_portfolios (
                        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        initial_capital NUMERIC NOT NULL DEFAULT 100000,
                        cash_balance    NUMERIC NOT NULL DEFAULT 100000,
                        created_at      TIMESTAMPTZ DEFAULT NOW(),
                        updated_at      TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(user_id)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS paper_positions (
                        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        portfolio_id UUID NOT NULL REFERENCES paper_portfolios(id) ON DELETE CASCADE,
                        symbol       TEXT NOT NULL,
                        shares       NUMERIC NOT NULL DEFAULT 0,
                        avg_cost     NUMERIC NOT NULL DEFAULT 0,
                        updated_at   TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(portfolio_id, symbol)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS paper_orders (
                        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        portfolio_id UUID NOT NULL REFERENCES paper_portfolios(id) ON DELETE CASCADE,
                        symbol       TEXT NOT NULL,
                        side         TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                        qty          NUMERIC NOT NULL,
                        order_type   TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
                        limit_price  NUMERIC,
                        filled_price NUMERIC,
                        status       TEXT NOT NULL DEFAULT 'pending'
                                         CHECK (status IN ('pending', 'filled', 'cancelled', 'rejected')),
                        created_at   TIMESTAMPTZ DEFAULT NOW(),
                        filled_at    TIMESTAMPTZ
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS paper_equity_curve (
                        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        portfolio_id UUID NOT NULL REFERENCES paper_portfolios(id) ON DELETE CASCADE,
                        date         DATE NOT NULL,
                        value        NUMERIC NOT NULL,
                        UNIQUE(portfolio_id, date)
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paper_positions_portfolio
                    ON paper_positions(portfolio_id)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paper_orders_portfolio
                    ON paper_orders(portfolio_id, created_at DESC)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paper_equity_portfolio
                    ON paper_equity_curve(portfolio_id, date)
                """)
        print("[DB] init_db OK")
    except Exception as e:
        print(f"[DB] init_db error: {e}")


def save_result(backtest_id: str, request_params: dict, result: dict, user_id: str | None = None):
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
                         win_rate_pct, sharpe_ratio, max_drawdown_pct, equity_curve, trades, metrics, spy_equity_curve, user_id)
                    VALUES (%s,%s,%s,%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                        spy_equity_curve = EXCLUDED.spy_equity_curve,
                        user_id = EXCLUDED.user_id
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
                    user_id,
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


# ── Auth DB helpers ──────────────────────────────────────────────────────────

def create_user(email: str, username: str, password_hash: str) -> dict | None:
    """유저 생성"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (email, username, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, username, is_active, created_at
                """, (email, username, password_hash))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as e:
        print(f"[DB] create_user error: {e}")
        return None


def get_user_by_email(email: str) -> dict | None:
    """이메일로 유저 조회"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, email, username, password_hash, is_active, created_at
                    FROM users WHERE email = %s
                """, (email,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as e:
        print(f"[DB] get_user_by_email error: {e}")
        return None


def get_user_by_id(user_id: str) -> dict | None:
    """ID로 유저 조회"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, email, username, is_active, created_at
                    FROM users WHERE id = %s
                """, (user_id,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as e:
        print(f"[DB] get_user_by_id error: {e}")
        return None


def save_refresh_token(user_id: str, token: str, expires_at: datetime) -> bool:
    """Refresh token 저장"""
    if not DATABASE_URL:
        return False
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO refresh_tokens (user_id, token, expires_at)
                    VALUES (%s, %s, %s)
                """, (user_id, token, expires_at))
        return True
    except Exception as e:
        print(f"[DB] save_refresh_token error: {e}")
        return False


def get_refresh_token(token: str) -> dict | None:
    """Refresh token 조회"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, token, expires_at
                    FROM refresh_tokens WHERE token = %s
                """, (token,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        return dict(zip(cols, row))
    except Exception as e:
        print(f"[DB] get_refresh_token error: {e}")
        return None


def delete_refresh_token(token: str) -> bool:
    """Refresh token 삭제 (로그아웃)"""
    if not DATABASE_URL:
        return False
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM refresh_tokens WHERE token = %s", (token,))
        return True
    except Exception as e:
        print(f"[DB] delete_refresh_token error: {e}")
        return False


def list_runs_by_user(user_id: str, limit: int = 20) -> list[dict]:
    """특정 유저의 백테스트 히스토리 조회"""
    if not DATABASE_URL:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, created_at, start_date, end_date, initial_capital,
                           max_positions, position_size_pct, status,
                           total_return_pct, total_trades, win_rate_pct,
                           sharpe_ratio, max_drawdown_pct, user_id
                    FROM backtest_runs
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        print(f"[DB] list_runs_by_user error: {e}")
        return []


# ── Paper Trading DB helpers (HOO-9) ─────────────────────────────────────────

def get_or_create_portfolio(user_id: str) -> dict | None:
    """유저 포트폴리오 조회 또는 생성"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO paper_portfolios (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
                    RETURNING id::text, user_id, initial_capital, cash_balance,
                              created_at, updated_at
                """, (user_id,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        return d
    except Exception as e:
        print(f"[DB] get_or_create_portfolio error: {e}")
        return None


def get_portfolio(user_id: str) -> dict | None:
    """유저 포트폴리오 조회"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id::text, user_id, initial_capital, cash_balance,
                           created_at, updated_at
                    FROM paper_portfolios WHERE user_id = %s
                """, (user_id,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        for k in ("created_at", "updated_at"):
            if isinstance(d.get(k), datetime):
                d[k] = d[k].isoformat()
        return d
    except Exception as e:
        print(f"[DB] get_portfolio error: {e}")
        return None


def get_positions(portfolio_id: str) -> list[dict]:
    """포지션 목록 조회"""
    if not DATABASE_URL:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id::text, portfolio_id::text, symbol, shares, avg_cost, updated_at
                    FROM paper_positions
                    WHERE portfolio_id = %s AND shares > 0
                    ORDER BY symbol
                """, (portfolio_id,))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if isinstance(d.get("updated_at"), datetime):
                d["updated_at"] = d["updated_at"].isoformat()
            result.append(d)
        return result
    except Exception as e:
        print(f"[DB] get_positions error: {e}")
        return []


def get_orders(portfolio_id: str, limit: int = 50) -> list[dict]:
    """주문 기록 조회"""
    if not DATABASE_URL:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id::text, portfolio_id::text, symbol, side, qty,
                           order_type, limit_price, filled_price, status,
                           created_at, filled_at
                    FROM paper_orders
                    WHERE portfolio_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (portfolio_id, limit))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            for k in ("created_at", "filled_at"):
                if isinstance(d.get(k), datetime):
                    d[k] = d[k].isoformat()
            result.append(d)
        return result
    except Exception as e:
        print(f"[DB] get_orders error: {e}")
        return []


def get_equity_curve(portfolio_id: str) -> list[dict]:
    """Equity curve 조회"""
    if not DATABASE_URL:
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT date::text, value
                    FROM paper_equity_curve
                    WHERE portfolio_id = %s
                    ORDER BY date ASC
                """, (portfolio_id,))
                cols = [d.name for d in cur.description]
                rows = cur.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    except Exception as e:
        print(f"[DB] get_equity_curve error: {e}")
        return []


def execute_paper_order(
    portfolio_id: str,
    symbol: str,
    side: str,
    qty: float,
    order_type: str,
    filled_price: float,
    limit_price: float | None = None,
) -> dict | None:
    """주문 체결 처리 (트랜잭션)"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 1. 주문 INSERT
                cur.execute("""
                    INSERT INTO paper_orders
                        (portfolio_id, symbol, side, qty, order_type, limit_price,
                         filled_price, status, filled_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'filled', NOW())
                    RETURNING id::text, symbol, side, qty, filled_price, status, filled_at
                """, (portfolio_id, symbol, side, qty, order_type, limit_price, filled_price))
                cols = [d.name for d in cur.description]
                order_row = cur.fetchone()
                order = dict(zip(cols, order_row))
                if isinstance(order.get("filled_at"), datetime):
                    order["filled_at"] = order["filled_at"].isoformat()

                trade_value = qty * filled_price

                # 2. 포트폴리오 잔고 업데이트
                if side == "buy":
                    cur.execute("""
                        UPDATE paper_portfolios
                        SET cash_balance = cash_balance - %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING cash_balance
                    """, (trade_value, portfolio_id))
                else:
                    cur.execute("""
                        UPDATE paper_portfolios
                        SET cash_balance = cash_balance + %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING cash_balance
                    """, (trade_value, portfolio_id))
                cash_row = cur.fetchone()
                cash_remaining = float(cash_row[0]) if cash_row else 0.0

                # 3. 포지션 UPSERT
                if side == "buy":
                    cur.execute("""
                        INSERT INTO paper_positions (portfolio_id, symbol, shares, avg_cost)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (portfolio_id, symbol) DO UPDATE SET
                            avg_cost = (paper_positions.shares * paper_positions.avg_cost
                                       + EXCLUDED.shares * EXCLUDED.avg_cost)
                                       / (paper_positions.shares + EXCLUDED.shares),
                            shares = paper_positions.shares + EXCLUDED.shares,
                            updated_at = NOW()
                    """, (portfolio_id, symbol, qty, filled_price))
                else:
                    cur.execute("""
                        UPDATE paper_positions
                        SET shares = shares - %s,
                            updated_at = NOW()
                        WHERE portfolio_id = %s AND symbol = %s
                    """, (qty, portfolio_id, symbol))

                # 4. Equity curve snapshot
                from datetime import date as date_type
                today = date_type.today().isoformat()
                cur.execute("""
                    SELECT COALESCE(SUM(shares * avg_cost), 0)
                    FROM paper_positions
                    WHERE portfolio_id = %s AND shares > 0
                """, (portfolio_id,))
                pos_value = float(cur.fetchone()[0])
                total_value = cash_remaining + pos_value
                cur.execute("""
                    INSERT INTO paper_equity_curve (portfolio_id, date, value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (portfolio_id, date) DO UPDATE SET value = EXCLUDED.value
                """, (portfolio_id, today, total_value))

        order["cash_remaining"] = cash_remaining
        return order
    except Exception as e:
        print(f"[DB] execute_paper_order error: {e}")
        return None


def reset_portfolio(user_id: str) -> dict | None:
    """포트폴리오 초기화"""
    if not DATABASE_URL:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                # 기존 포트폴리오 삭제 (CASCADE로 positions, orders, equity_curve 삭제)
                cur.execute("""
                    DELETE FROM paper_portfolios WHERE user_id = %s
                """, (user_id,))
                # 새로 생성
                cur.execute("""
                    INSERT INTO paper_portfolios (user_id)
                    VALUES (%s)
                    RETURNING id::text, user_id, initial_capital, cash_balance, created_at
                """, (user_id,))
                cols = [d.name for d in cur.description]
                row = cur.fetchone()
        if not row:
            return None
        d = dict(zip(cols, row))
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        return d
    except Exception as e:
        print(f"[DB] reset_portfolio error: {e}")
        return None
