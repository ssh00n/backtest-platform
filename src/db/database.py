"""
PostgreSQL 데이터베이스 연결 및 세션 관리.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://localhost:5432/hts",
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_session():
    """세션을 생성하고 반환한다. with 문으로 사용."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """테이블이 없으면 생성한다."""
    Base.metadata.create_all(bind=engine)
