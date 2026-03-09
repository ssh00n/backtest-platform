from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import backtest, strategy, market, history
from api.routers import auth
from api.db import init_db

app = FastAPI(title="WFS Backtest API", version="0.1.0")

@app.on_event("startup")
def on_startup():
    init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest.router, prefix="/api/backtest", tags=["backtest"])
app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
app.include_router(market.router, prefix="/api/market", tags=["market"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(auth.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
