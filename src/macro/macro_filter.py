"""
매크로 필터 — 백테스트/스크리너 통합 인터페이스

백테스트 엔진과 실시간 스크리너에서 매크로 위험도를 체크해서
진입 여부와 포지션 크기를 조정한다.

사용 예:
    filter = MacroFilter()
    decision = filter.check(date=today, rr_ratio=4.5, vol_ratio=2.0)
    if decision.allow_entry:
        # 진입 허용
        size_pct = decision.position_size_pct  # 1.0 or 0.5
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd

from src.macro.macro_detector import (
    MacroRiskLevel,
    detect_market_stress,
    detect_market_stress_from_cache,
)
from src.macro.macro_calendar import get_macro_risk_for_date

log = logging.getLogger(__name__)


@dataclass
class MacroDecision:
    """매크로 필터 결과."""
    date: pd.Timestamp
    allow_entry: bool
    risk_level: MacroRiskLevel
    position_size_pct: float      # 1.0 = 전량, 0.5 = 절반
    min_rr_override: float | None  # None = 기본값 유지
    reasons: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "✅ 진입허용" if self.allow_entry else "🚫 진입차단"
        size = f"({self.position_size_pct:.0%} 크기)" if self.position_size_pct < 1.0 else ""
        rr = f" RR≥{self.min_rr_override}" if self.min_rr_override else ""
        reasons = " | " + ", ".join(self.reasons) if self.reasons else ""
        return f"{status}{size}{rr}{reasons}"


class MacroFilter:
    """
    매크로 위험도 기반 진입 필터.

    데이터 소스 우선순위:
      1. VIX + SPY (yfinance, 무료) — 기술적 스트레스
      2. FMP 경제 캘린더 (선택, FMP_API_KEY 필요) — FOMC/NFP 등
      3. FRED API (선택, FRED_API_KEY 필요) — 공식 경제지표

    캐시: 동일 날짜 재조회 방지 (백테스트 속도 개선)
    """

    def __init__(
        self,
        use_vix_spy: bool = True,
        use_fmp_calendar: bool = True,
        use_fred: bool = False,          # FRED는 후처리 분석용
        fmp_api_key: str | None = None,
        fred_api_key: str | None = None,
        # HIGH 리스크 정책
        high_risk_block: bool = True,    # True: 진입 차단 / False: 크기 50%로만
        # MEDIUM 리스크 정책
        medium_size_pct: float = 0.5,    # 포지션 크기 배율
        medium_rr_boost: float = 0.5,    # R:R 최소 요건 상향 (+)
    ):
        self.use_vix_spy = use_vix_spy
        self.use_fmp_calendar = use_fmp_calendar
        self.use_fred = use_fred
        self.fmp_api_key = fmp_api_key
        self.fred_api_key = fred_api_key
        self.high_risk_block = high_risk_block
        self.medium_size_pct = medium_size_pct
        self.medium_rr_boost = medium_rr_boost

        # 날짜별 결과 캐시
        self._cache: dict[str, MacroDecision] = {}

        # 사전 로드된 가격 데이터 (백테스트 모드)
        self._spy_cache: pd.DataFrame = pd.DataFrame()
        self._vix_cache: pd.DataFrame = pd.DataFrame()
        self._preloaded: bool = False

    def preload(
        self,
        spy_df: pd.DataFrame,
        vix_df: pd.DataFrame,
    ) -> None:
        """
        SPY/VIX 데이터를 사전 로드한다 (백테스트 전 1회 호출).

        백테스트 엔진에서 이미 가진 OHLCV 데이터를 주입하면
        날짜마다 API 호출 없이 메모리에서 즉시 조회.

        Args:
            spy_df: SPY 가격 DataFrame (index=datetime, 'close' 또는 'SPY' 컬럼)
            vix_df: VIX 가격 DataFrame (index=datetime, 'close' 또는 '^VIX' 컬럼)
        """
        # 컬럼명 표준화
        if "close" in spy_df.columns:
            self._spy_cache = spy_df[["close"]].rename(columns={"close": "SPY"})
        else:
            self._spy_cache = spy_df.copy()

        if "close" in vix_df.columns:
            self._vix_cache = vix_df[["close"]].rename(columns={"close": "^VIX"})
        else:
            self._vix_cache = vix_df.copy()

        self._preloaded = True
        self._cache.clear()  # 기존 캐시 초기화
        self._prebuild_risk_series()  # 전체 기간 벡터화 사전 계산
        log.info(
            "MacroFilter 사전 로드 완료: SPY %d일, VIX %d일",
            len(self._spy_cache), len(self._vix_cache),
        )

    def preload_from_alpaca(
        self,
        start: pd.Timestamp,
        end: pd.Timestamp,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        """
        Alpaca API로 SPY/VIX 데이터를 사전 로드한다.

        백테스트 엔진이 별도 데이터 제공 못할 때 직접 Alpaca에서 가져옴.

        Args:
            start: 백테스트 시작일
            end: 백테스트 종료일
        """
        import os
        key = api_key or os.getenv("ALPACA_API_KEY", "")
        secret = api_secret or os.getenv("ALPACA_API_SECRET", "")

        if not key or not secret:
            log.warning("Alpaca API key 없음 — yfinance fallback 사용")
            self._preload_from_yfinance(start, end)
            return

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            client = StockHistoricalDataClient(key, secret)
            symbols = ["SPY"]

            req = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Day,
                start=start.to_pydatetime(),
                end=end.to_pydatetime(),
            )
            bars = client.get_stock_bars(req).df

            spy_df = bars.xs("SPY", level=0)[["close"]]
            spy_df.index = spy_df.index.normalize()
            self._spy_cache = spy_df.rename(columns={"close": "SPY"})

            # VIX는 Alpaca에 없으므로 yfinance로
            self._preload_vix_from_yfinance(start, end)

            self._preloaded = True
            self._cache.clear()
            log.info("MacroFilter Alpaca 로드 완료: SPY %d일", len(self._spy_cache))

        except Exception as e:
            log.warning("Alpaca 로드 실패 (%s) — yfinance fallback", e)
            self._preload_from_yfinance(start, end)

    def _preload_from_yfinance(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        from src.macro.macro_detector import _fetch_price_data
        spy = _fetch_price_data("SPY", start.to_pydatetime(), end.to_pydatetime())
        if not spy.empty:
            self._spy_cache = spy
        self._preload_vix_from_yfinance(start, end)
        self._preloaded = True
        self._cache.clear()

    def _preload_vix_from_yfinance(self, start: pd.Timestamp, end: pd.Timestamp) -> None:
        from src.macro.macro_detector import _fetch_price_data
        vix = _fetch_price_data("^VIX", start.to_pydatetime(), end.to_pydatetime())
        if not vix.empty:
            self._vix_cache = vix

    def preload_vix(
        self,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> "MacroFilter":
        """
        VIX 데이터만 yfinance로 1회 로드 (퍼블릭 메서드).

        백테스트 엔진이 SPY 데이터는 이미 가지고 있을 때 사용:
            filter = MacroFilter()
            filter.preload_vix(start, end)          # VIX 1회 로드
            filter.preload(spy_df, filter._vix_cache) # SPY는 엔진 데이터

        Returns:
            self (메서드 체이닝 지원)
        """
        self._preload_vix_from_yfinance(start, end)
        return self

    def _prebuild_risk_series(self) -> None:
        """
        전체 기간 리스크 레벨을 벡터화로 사전 계산.
        preload() 호출 후 자동 실행 — check() 호출을 O(1)로 만듦.
        """
        if self._spy_cache.empty and self._vix_cache.empty:
            return

        spy_col = "SPY" if "SPY" in self._spy_cache.columns else (self._spy_cache.columns[0] if not self._spy_cache.empty else None)
        vix_col = "^VIX" if "^VIX" in self._vix_cache.columns else (self._vix_cache.columns[0] if not self._vix_cache.empty else None)

        # 날짜 인덱스 통합
        all_dates = pd.Series(dtype="object")
        if spy_col:
            from src.macro.macro_detector import _to_naive, _ts_to_naive
            spy_idx = _to_naive(self._spy_cache.index)
            spy_prices = pd.Series(self._spy_cache[spy_col].values, index=spy_idx)
            spy_ret5 = spy_prices.pct_change(5)
            spy_ret1 = spy_prices.pct_change(1)

        if vix_col:
            vix_idx = _to_naive(self._vix_cache.index)
            vix_prices = pd.Series(self._vix_cache[vix_col].values, index=vix_idx)

        # 전체 영업일 인덱스
        start = (self._spy_cache.index.min() if not self._spy_cache.empty else self._vix_cache.index.min())
        end   = (self._spy_cache.index.max() if not self._spy_cache.empty else self._vix_cache.index.max())
        bdays = pd.bdate_range(
            _ts_to_naive(start if hasattr(start, "tzinfo") else pd.Timestamp(start)),
            _ts_to_naive(end if hasattr(end, "tzinfo") else pd.Timestamp(end)),
        )

        risk_map: dict[str, str] = {}
        for date in bdays:
            key = date.strftime("%Y-%m-%d")
            risk = MacroRiskLevel.LOW
            reasons = []

            # VIX 체크
            if vix_col and date in vix_prices.index:
                vix = vix_prices[date]
                if vix >= 30:
                    risk = MacroRiskLevel.EXTREME
                    reasons.append(f"VIX {vix:.1f}≥30")
                elif vix >= 25 and risk == MacroRiskLevel.LOW:
                    risk = MacroRiskLevel.HIGH
                    reasons.append(f"VIX {vix:.1f}≥25")
                elif vix >= 20 and risk == MacroRiskLevel.LOW:
                    risk = MacroRiskLevel.MEDIUM
                    reasons.append(f"VIX {vix:.1f}≥20")

            # SPY 5일 수익률 체크
            if spy_col and date in spy_ret5.index:
                r5 = spy_ret5[date]
                if pd.notna(r5):
                    if r5 <= -0.05 and risk in (MacroRiskLevel.LOW, MacroRiskLevel.MEDIUM):
                        risk = MacroRiskLevel.HIGH
                        reasons.append(f"SPY5d {r5:.1%}")

            # 캐시에 MacroDecision 저장
            if risk != MacroRiskLevel.LOW:
                self._cache[key] = MacroDecision(
                    date=pd.Timestamp(key),
                    allow_entry=risk not in (MacroRiskLevel.EXTREME, MacroRiskLevel.HIGH) or not self.high_risk_block,
                    risk_level=risk,
                    position_size_pct=0.0 if risk == MacroRiskLevel.EXTREME else (
                        0.0 if risk == MacroRiskLevel.HIGH and self.high_risk_block else self.medium_size_pct
                    ),
                    min_rr_override=None,
                    reasons=reasons,
                )

        log.debug("매크로 리스크 사전 계산 완료: %d 고위험일", sum(1 for v in self._cache.values() if v.risk_level != MacroRiskLevel.LOW))

    def preload_with_spy(
        self,
        spy_df: pd.DataFrame,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> "MacroFilter":
        """
        SPY는 엔진 데이터로, VIX만 yfinance 1회 로드.

        백테스트 엔진 통합에 최적화된 메서드.

        Args:
            spy_df: 엔진에서 이미 로드된 SPY OHLCV DataFrame
            start: VIX 조회 시작일
            end: VIX 조회 종료일

        Usage (engine.py):
            macro_filter = MacroFilter()
            macro_filter.preload_with_spy(all_bars["SPY"], start, end)
        """
        self._preload_vix_from_yfinance(start, end)
        self.preload(spy_df, self._vix_cache)
        return self

    def check(
        self,
        date: pd.Timestamp,
        rr_ratio: float = 4.5,
    ) -> MacroDecision:
        """
        특정 날짜의 매크로 진입 허용 여부 판단.

        Args:
            date: 체크할 날짜
            rr_ratio: 현재 신호의 R:R 비율

        Returns:
            MacroDecision
        """
        cache_key = date.strftime("%Y-%m-%d")
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 사전 계산 완료 상태 — 캐시에 없으면 LOW (이미 사전 계산됨)
        if self._preloaded:
            decision = MacroDecision(
                date=date,
                allow_entry=True,
                risk_level=MacroRiskLevel.LOW,
                position_size_pct=1.0,
                min_rr_override=None,
                reasons=[],
            )
            self._cache[cache_key] = decision
            return decision

        risk = MacroRiskLevel.LOW
        reasons = []

        # 1. VIX/SPY 기술적 스트레스
        if self.use_vix_spy:
            if self._preloaded:
                # 백테스트 모드: 메모리 캐시에서 즉시 조회 (빠름)
                stress = detect_market_stress_from_cache(
                    date, self._spy_cache, self._vix_cache
                )
            else:
                # 실시간 모드: yfinance API 호출
                stress = detect_market_stress(date)

            if stress.risk_level != MacroRiskLevel.LOW:
                risk = stress.risk_level
                reasons.extend(stress.triggered_by)

        # 2. FMP 경제 캘린더
        if self.use_fmp_calendar:
            cal_risk, cal_reasons = get_macro_risk_for_date(
                date, fmp_api_key=self.fmp_api_key
            )
            if cal_risk == "HIGH":
                risk = MacroRiskLevel.HIGH
                reasons.extend(cal_reasons)
            elif cal_risk == "MEDIUM" and risk == MacroRiskLevel.LOW:
                risk = MacroRiskLevel.MEDIUM
                reasons.extend(cal_reasons)

        # 결정 로직
        if risk == MacroRiskLevel.EXTREME:
            # Level 3: 항상 차단 (VIX 급등 / 관세 충격 수준)
            decision = MacroDecision(
                date=date,
                allow_entry=False,
                risk_level=risk,
                position_size_pct=0.0,
                min_rr_override=None,
                reasons=reasons,
            )
        elif risk == MacroRiskLevel.HIGH:
            if self.high_risk_block:
                # Level 2 엄격 모드: 차단
                decision = MacroDecision(
                    date=date,
                    allow_entry=False,
                    risk_level=risk,
                    position_size_pct=0.0,
                    min_rr_override=None,
                    reasons=reasons,
                )
            else:
                # Level 2 완화 모드: 50% 축소
                decision = MacroDecision(
                    date=date,
                    allow_entry=True,
                    risk_level=risk,
                    position_size_pct=self.medium_size_pct,
                    min_rr_override=rr_ratio + self.medium_rr_boost * 2,
                    reasons=reasons,
                )
        elif risk == MacroRiskLevel.MEDIUM:
            decision = MacroDecision(
                date=date,
                allow_entry=True,
                risk_level=risk,
                position_size_pct=self.medium_size_pct,
                min_rr_override=rr_ratio + self.medium_rr_boost if rr_ratio > 0 else None,
                reasons=reasons,
            )
        else:
            decision = MacroDecision(
                date=date,
                allow_entry=True,
                risk_level=MacroRiskLevel.LOW,
                position_size_pct=1.0,
                min_rr_override=None,
                reasons=[],
            )

        self._cache[cache_key] = decision

        if risk != MacroRiskLevel.LOW:
            log.info("[MACRO] %s %s | %s", date.strftime("%Y-%m-%d"), decision, ", ".join(reasons))

        return decision

    def build_risk_calendar(
        self,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DataFrame:
        """
        기간 전체의 매크로 위험도 캘린더를 DataFrame으로 반환.
        백테스트 전에 미리 캐시하면 속도 향상.
        """
        dates = pd.date_range(start=start, end=end, freq="B")  # 영업일
        records = []

        log.info("매크로 캘린더 생성 중 (%d 영업일)...", len(dates))
        for i, date in enumerate(dates):
            if i % 20 == 0:
                log.info("  진행: %d/%d (%s)", i, len(dates), date.strftime("%Y-%m-%d"))
            decision = self.check(date)
            if decision.risk_level != MacroRiskLevel.LOW:
                records.append({
                    "date": date,
                    "risk_level": decision.risk_level.value,
                    "allow_entry": decision.allow_entry,
                    "reasons": " | ".join(decision.reasons),
                })

        if not records:
            return pd.DataFrame(columns=["date", "risk_level", "allow_entry", "reasons"])

        return pd.DataFrame(records).set_index("date")
