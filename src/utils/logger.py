"""
로깅 설정

- 콘솔: INFO 이상
- 파일: 일별 로그 파일 (logs/screener_YYYY-MM-DD.log)
- 로테이팅 없음 — 일별로 새 파일 생성
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_INITIALIZED = False


def setup_logging(
    name: str = "hts",
    level: int = logging.DEBUG,
    console_level: int = logging.INFO,
) -> logging.Logger:
    """
    프로젝트 루트 로거를 설정하고 반환한다.

    - 콘솔 핸들러: console_level 이상 출력
    - 파일 핸들러: logs/{name}_YYYY-MM-DD.log 에 level 이상 기록

    여러 번 호출해도 핸들러가 중복 등록되지 않는다.
    """
    global _INITIALIZED

    logger = logging.getLogger(name)

    if _INITIALIZED:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 파일 핸들러 (일별)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = _LOG_DIR / f"{name}_{today}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    _INITIALIZED = True
    logger.debug("Logging initialized — file: %s", log_file)
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    모듈별 자식 로거를 반환한다.

    사용법:
        from src.utils.logger import get_logger
        log = get_logger(__name__)
        log.info("message")
    """
    parent = logging.getLogger("hts")
    if not parent.handlers:
        setup_logging()
    return parent.getChild(module_name)
