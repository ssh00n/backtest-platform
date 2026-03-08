from fastapi import APIRouter

router = APIRouter()


@router.get("/universe")
async def get_universe():
    return {
        "sp500_count": 503,
        "sp400_count": 400,
        "total": 903,
        "excluded": ["BRK/B", "BF/B"],
    }
