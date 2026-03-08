# Backtest Platform

주식 투자 전략 구현 및 모의투자 백테스트 플랫폼

## 스택

- **Frontend**: Next.js 15 + Tailwind CSS + Recharts
- **Backend**: FastAPI + WebSocket + BackgroundTasks
- **Strategy Engine**: Darvas Box (Python)
- **Data**: Alpaca API (US Stocks)

## 빠른 시작

### 환경 변수 설정

```bash
# 루트에 .env 파일 생성
cp .env.example .env
# .env에 실제 Alpaca API 키 입력
```

```bash
# 프론트엔드 환경 변수
cp .env.example web/.env.local
# web/.env.local 수정 (NEXT_PUBLIC_* 변수만 사용)
```

### 백엔드 실행

```bash
pip install -e .
uvicorn api.main:app --reload --port 8000
```

### 프론트엔드 실행

```bash
cd web
npm install
npm run dev
```

→ `http://localhost:3000/strategy` 접속

## 프로젝트 구조

```
backtest-platform/
├── api/                  # FastAPI 백엔드
│   ├── main.py
│   ├── models/
│   ├── routes/
│   └── services/
├── web/                  # Next.js 프론트엔드
│   ├── app/
│   │   ├── strategy/     # 전략 설정 화면
│   │   ├── backtest/     # 백테스트 진행 화면
│   │   └── results/      # 결과 대시보드
│   └── components/
│       └── results/      # KPICard, EquityCurve, TradeTable
└── src/                  # 백테스트 엔진
    ├── backtest/
    └── data/
```
