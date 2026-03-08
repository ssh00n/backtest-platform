"""
매크로 이벤트 파이프라인 (feat/macro-pipeline)

시장 전체에 영향을 주는 거시 이벤트를 감지해서
전략의 진입 여부를 결정하는 매크로 레짐 레이어.

이벤트 유형:
    TARIFF_SHOCK    - 관세/무역 정책 충격 (2025-04 트럼프 관세 등)
    FED_DECISION    - FOMC 금리 결정 + 서프라이즈
    MARKET_STRESS   - VIX 급등 / SPY 연속 하락 (기술적 감지)
    MACRO_DATA      - CPI/NFP 등 주요 경제지표 서프라이즈
    GEOPOLITICAL    - 지정학적 리스크

리스크 레벨:
    HIGH   - 신규 진입 차단
    MEDIUM - 포지션 크기 50% 축소 + R:R 요건 상향
    LOW    - 모니터링만

모듈 구조:
    macro_detector.py  - VIX/SPY 기반 자동 감지 (API 키 불필요)
    macro_calendar.py  - FRED + FMP 경제 캘린더 조회
    macro_filter.py    - 백테스트/스크리너 통합 인터페이스
"""
from src.macro.macro_detector import MacroEvent, MacroRiskLevel, detect_market_stress
from src.macro.macro_filter import MacroFilter

__all__ = ["MacroEvent", "MacroRiskLevel", "detect_market_stress", "MacroFilter"]
