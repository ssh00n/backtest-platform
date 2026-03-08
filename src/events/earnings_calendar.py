"""
실적 발표 캘린더 (Earnings Calendar)

데이터 소스:
  1. Financial Modeling Prep (FMP) API — 실적 발표 캘린더 (무료 250req/day)
  2. SEC EDGAR API — 8-K/10-Q/10-K 공시 (무료, 키 불필요)

목적:
  돌파일 기준 ±N일 이내에 실적 발표 / 중대 공시가 있었는지 확인하여
  "이벤트 기반 돌파"와 "순수 기술적 돌파"를 구분한다.

환경변수:
  FMP_API_KEY — Financial Modeling Prep API 키 (무료: financialmodelingprep.com)
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from src.utils.logger import get_logger

# .env 자동 로드
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

log = get_logger(__name__)

# ── API 엔드포인트 ───────────────────────────────────────
FMP_EARNINGS_URL = "https://financialmodelingprep.com/api/v3/earning_calendar"
FMP_EARNINGS_SYMBOL_URL = "https://financialmodelingprep.com/api/v3/historical/earning_calendar/{symbol}"
SEC_EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"


@dataclass
class EarningsEvent:
    """실적 관련 이벤트 하나."""
    symbol: str
    event_date: pd.Timestamp
    event_type: str          # "EARNINGS" | "8-K" | "10-Q" | "10-K"
    source: str              # "FMP" | "SEC_EDGAR"
    headline: str | None = None
    eps_actual: float | None = None    # FMP: 실제 EPS
    eps_estimate: float | None = None  # FMP: 예상 EPS
    beat: bool | None = None           # EPS 어닝 서프라이즈 여부
    days_from_breakout: int = 0        # 돌파일 기준 상대 일수 (음수=이전)


def fetch_earnings_from_fmp(
    ticker: str,
    start_date: datetime,
    end_date: datetime,
    api_key: str | None = None,
) -> list[EarningsEvent]:
    """
    Financial Modeling Prep API로 실적 발표 캘린더를 가져온다.

    - 무료 티어: 250 requests/day
    - 어닝 서프라이즈(Beat/Miss) 포함
    - 환경변수: FMP_API_KEY

    Args:
        ticker: 종목 심볼 (e.g., "AAPL")
        start_date: 조회 시작일
        end_date: 조회 종료일
        api_key: FMP API Key (없으면 환경변수 FMP_API_KEY 사용)

    Returns:
        EarningsEvent 리스트
    """
    key = api_key or os.getenv("FMP_API_KEY", "")
    if not key:
        log.debug("FMP_API_KEY not set, skipping FMP earnings fetch")
        return []

    # 신규 stable API 엔드포인트 (2025-08 이후, v3 레거시 deprecated)
    import requests as _req
    urls_to_try = [
        f"https://financialmodelingprep.com/stable/earnings?symbol={ticker}&apikey={key}",
    ]

    raw_data = None
    for url in urls_to_try:
        try:
            resp = _req.get(url, timeout=15)
            if resp.ok and resp.json():
                raw_data = resp.json()
                log.debug("FMP 응답 성공: %d건", len(raw_data))
                break
        except Exception as e:
            log.debug("FMP 요청 실패: %s", e)
            continue

    if raw_data is None:
        return []

    # 문자열 비교 (tz 문제 방지)
    start_str = pd.Timestamp(start_date).strftime("%Y-%m-%d")
    end_str = pd.Timestamp(end_date).strftime("%Y-%m-%d")

    results: list[EarningsEvent] = []
    for item in raw_data:
        try:
            date_str = item.get("date", "")
            if not date_str or not (start_str <= date_str <= end_str):
                continue
            date = pd.Timestamp(date_str)
            eps_a = item.get("epsActual")
            eps_e = item.get("epsEstimated")
            rev_a = item.get("revenueActual")
            rev_e = item.get("revenueEstimated")

            if eps_a is not None and eps_e is not None:
                beat_miss = "beat" if float(eps_a) > float(eps_e) else "miss"
            else:
                beat_miss = "unknown"

            beat = (float(eps_a) > float(eps_e)) if (eps_a is not None and eps_e is not None) else None
            results.append(EarningsEvent(
                symbol=ticker,
                event_date=date,
                event_type="EARNINGS",
                source="FMP",
                eps_actual=float(eps_a) if eps_a is not None else None,
                eps_estimate=float(eps_e) if eps_e is not None else None,
                beat=beat,
            ))
        except Exception:
            continue
    log.debug("FMP [%s] %d 어닝 이벤트 (범위 내)", ticker, len(results))
    return results

def _fetch_fmp_legacy(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    api_key: str,
) -> list["EarningsEvent"]:
    """레거시 FMP v3 코드 — 현재 미사용"""
    if not api_key:
        log.debug("FMP_API_KEY not set, skipping FMP earnings fetch")
        return []

    try:
        # 종목별 히스토리컬 실적 캘린더
        url = FMP_EARNINGS_SYMBOL_URL.format(symbol=ticker)
        resp = requests.get(
            url,
            params={"apikey": key, "limit": 20},
            timeout=10,
        )
        if resp.status_code != 200:
            log.debug("FMP earnings returned %d for %s", resp.status_code, ticker)
            return []

        data = resp.json()
        if not isinstance(data, list):
            return []

        events = []
        for item in data:
            date_str = item.get("date")
            if not date_str:
                continue
            try:
                event_date = pd.Timestamp(date_str)
            except Exception:
                continue

            # 날짜 범위 필터
            if not (start_date.date() <= event_date.date() <= end_date.date()):
                continue

            eps_actual = item.get("eps")
            eps_estimate = item.get("epsEstimated")
            beat = None
            if eps_actual is not None and eps_estimate is not None:
                try:
                    beat = float(eps_actual) > float(eps_estimate)
                except (TypeError, ValueError):
                    pass

            events.append(EarningsEvent(
                symbol=ticker,
                event_date=event_date,
                event_type="EARNINGS",
                source="FMP",
                headline=f"{ticker} Earnings: EPS {eps_actual} vs Est {eps_estimate}",
                eps_actual=float(eps_actual) if eps_actual is not None else None,
                eps_estimate=float(eps_estimate) if eps_estimate is not None else None,
                beat=beat,
            ))

        return events

    except Exception as e:
        log.debug("FMP earnings fetch failed for %s: %s", ticker, e)
        return []


def fetch_earnings_from_yfinance(
    ticker: str,
    start_date: datetime,
    end_date: datetime,
) -> list[EarningsEvent]:
    """
    yfinance로 EPS 실적 + 컨센서스(estimate) 데이터를 가져온다.

    API KEY 불필요. FMP 무료 플랜 대안으로 사용.
    EPS Estimate + Reported EPS + Surprise% 포함.

    Args:
        ticker: 종목 심볼 (e.g., "AAPL")
        start_date: 조회 시작일
        end_date: 조회 종료일

    Returns:
        EarningsEvent 리스트 (source="YFINANCE")
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance 미설치 — 'uv add yfinance'로 설치 필요")
        return []

    try:
        t = yf.Ticker(ticker)
        ed = t.get_earnings_dates(limit=20)  # 최근 5년치 충분
        if ed is None or ed.empty:
            log.debug("yfinance: %s 어닝 데이터 없음", ticker)
            return []

        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        # tz-naive 비교를 위해 정규화
        start_naive = start_ts.tz_localize(None) if start_ts.tzinfo is None else start_ts.tz_convert(None)
        end_naive = end_ts.tz_localize(None) if end_ts.tzinfo is None else end_ts.tz_convert(None)

        results: list[EarningsEvent] = []
        for idx, row in ed.iterrows():
            # 인덱스 tz 통일
            date_naive = idx.tz_convert(None) if idx.tzinfo else idx
            if not (start_naive <= date_naive <= end_naive):
                continue

            eps_a = row.get("Reported EPS")
            eps_e = row.get("EPS Estimate")
            surprise = row.get("Surprise(%)")

            # NaN 처리
            import math
            eps_a = None if (eps_a is None or (isinstance(eps_a, float) and math.isnan(eps_a))) else float(eps_a)
            eps_e = None if (eps_e is None or (isinstance(eps_e, float) and math.isnan(eps_e))) else float(eps_e)

            beat = None
            if eps_a is not None and eps_e is not None:
                beat = eps_a > eps_e

            results.append(EarningsEvent(
                symbol=ticker,
                event_date=pd.Timestamp(date_naive),
                event_type="EARNINGS",
                source="YFINANCE",
                eps_actual=eps_a,
                eps_estimate=eps_e,
                beat=beat,
            ))

        log.debug("yfinance [%s] %d 어닝 이벤트 (범위 내)", ticker, len(results))
        return results

    except Exception as e:
        log.debug("yfinance earnings fetch failed for %s: %s", ticker, e)
        return []


def fetch_8k_from_sec(
    ticker: str,
    start_date: datetime,
    end_date: datetime,
) -> list[EarningsEvent]:
    """
    SEC EDGAR에서 8-K 공시를 가져온다. (중대 기업 이벤트: 실적, 가이던스, M&A 등)
    공개 API, 키 불필요.

    Args:
        ticker: 종목 심볼
        start_date: 조회 시작일
        end_date: 조회 종료일

    Returns:
        EarningsEvent 리스트
    """
    try:
        headers = {"User-Agent": "beta-agent beta@pi-agent.local"}
        resp = requests.get(
            SEC_EDGAR_SEARCH,
            params={
                "q": f'"{ticker}"',
                "dateRange": "custom",
                "startdt": start_date.strftime("%Y-%m-%d"),
                "enddt": end_date.strftime("%Y-%m-%d"),
                "forms": "8-K",
            },
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            log.debug("SEC EDGAR 8-K returned %d for %s", resp.status_code, ticker)
            return []

        hits = resp.json().get("hits", {}).get("hits", [])
        events = []

        for hit in hits:
            src = hit.get("_source", {})
            filed = src.get("file_date") or src.get("period_of_report")
            if not filed:
                continue
            try:
                event_date = pd.Timestamp(filed)
            except Exception:
                continue

            raw_items = src.get("items", [])
            # items는 리스트 또는 문자열 모두 대응
            if isinstance(raw_items, list):
                item_set = {str(i).strip() for i in raw_items}
                items = ", ".join(raw_items)
            else:
                items = str(raw_items)
                item_set = {i.strip() for i in items.split(",")} if raw_items else set()

            # 8-K Item 분류:
            # 핵심 촉매 (실적/가이던스): 2.02, 7.01, 8.01
            # 노이즈 (무관): 5.02(임원변경), 1.01(계약), 9.01(첨부서류)
            EARNINGS_ITEMS = {"2.02", "7.01", "8.01"}
            NOISE_ITEMS = {"5.02", "1.01", "1.02", "9.01"}

            has_earnings_item = bool(item_set & EARNINGS_ITEMS)
            is_all_noise = item_set and item_set.issubset(NOISE_ITEMS)

            # 노이즈만 있는 8-K는 스킵
            if is_all_noise:
                continue

            event_type = "8-K-EARNINGS" if has_earnings_item else "8-K"

            events.append(EarningsEvent(
                symbol=ticker,
                event_date=event_date,
                event_type=event_type,
                source="SEC_EDGAR",
                headline=f"8-K({items[:40]})" if items else "8-K filed",
            ))

        return events

    except Exception as e:
        log.debug("SEC EDGAR 8-K fetch failed for %s: %s", ticker, e)
        return []


def find_events_near_breakout(
    symbol: str,
    breakout_date: pd.Timestamp,
    window_before: int = 5,
    window_after: int = 2,
    fmp_api_key: str | None = None,
) -> list[EarningsEvent]:
    """
    돌파일 기준 ±N일 이내의 실적 이벤트를 조회한다.

    데이터 소스 우선순위:
      1. FMP — 정확한 실적 발표일 + EPS Beat/Miss 여부
      2. SEC EDGAR 8-K — 가이던스, M&A 등 중대 공시 (키 불필요)

    Args:
        symbol: 종목 심볼
        breakout_date: 돌파일
        window_before: 돌파 이전 탐색 일수 (기본 5일)
        window_after: 돌파 이후 탐색 일수 (기본 2일)
        fmp_api_key: FMP API Key (없으면 환경변수 FMP_API_KEY 사용)

    Returns:
        돌파일 기준 상대 일수가 계산된 EarningsEvent 리스트
    """
    start = breakout_date - timedelta(days=window_before + 5)  # 여유 포함
    end = breakout_date + timedelta(days=window_after + 2)

    # FMP 실적 캘린더 + SEC 8-K 병합
    events = []
    # 우선순위: yfinance (primary, 98% 커버) → FMP 보완 → SEC EDGAR 8-K
    yf_events = fetch_earnings_from_yfinance(symbol, start, end)
    events.extend(yf_events)

    # FMP: yfinance에 없는 종목 보완 (mega-cap 일부 정확도 향상)
    if not yf_events and fmp_api_key:
        events.extend(fetch_earnings_from_fmp(symbol, start, end, fmp_api_key))

    events.extend(fetch_8k_from_sec(symbol, start, end))

    # 윈도우 필터링 + 상대 일수 계산
    # tz 통일 (naive 기준)
    bd_naive = breakout_date.tz_localize(None) if breakout_date.tzinfo else breakout_date
    filtered = []
    for ev in events:
        ed_naive = ev.event_date.tz_localize(None) if ev.event_date.tzinfo else ev.event_date
        delta = (ed_naive - bd_naive).days
        if -window_before <= delta <= window_after:
            ev.days_from_breakout = delta
            filtered.append(ev)

    # 중복 제거 (같은 날짜, 같은 타입)
    seen = set()
    unique = []
    for ev in filtered:
        key = (ev.event_date.date(), ev.event_type)
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    return sorted(unique, key=lambda e: e.event_date)


def classify_event_quality(events: list[EarningsEvent]) -> str:
    """
    이벤트 품질을 분류한다.

    Returns:
        "EARNINGS_BEAT" — FMP 실적 발표 + EPS Beat (가장 강한 촉매)
        "EARNINGS_MISS" — FMP 실적 발표 + EPS Miss (부정적)
        "CATALYST"      — 8-K 공시 (가이던스, M&A 등)
        "EARNINGS"      — 실적 발표 (Beat/Miss 불명확)
        "NO_EVENT"      — 이벤트 없음 (순수 기술적 돌파)
    """
    if not events:
        return "NO_EVENT"

    # 실적 이벤트 우선 처리 (FMP 또는 yfinance)
    earnings_events = [ev for ev in events if ev.source in ("FMP", "YFINANCE") and ev.event_type == "EARNINGS"]
    if earnings_events:
        ev = earnings_events[0]
        if ev.beat is True:
            return "EARNINGS_BEAT"
        if ev.beat is False:
            return "EARNINGS_MISS"
        return "EARNINGS"

    # SEC 8-K 실적 관련 (Item 2.02/7.01) → 가장 강한 SEC 촉매
    has_8k_earnings = any(ev.event_type == "8-K-EARNINGS" for ev in events)
    if has_8k_earnings:
        return "CATALYST_EARNINGS"

    # 기타 8-K
    has_8k = any(ev.event_type == "8-K" for ev in events)
    if has_8k:
        return "CATALYST"

    return "NO_EVENT"
