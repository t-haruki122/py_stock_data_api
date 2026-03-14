"""システム統計データのAPIルーター"""

from fastapi import APIRouter
from app.stats import stats

router = APIRouter(prefix="/stats", tags=["System Stats"])

@router.get("")
async def get_system_stats():
    """現在のAPI呼び出し回数とキャッシュヒット数を取得"""
    return stats.get_stats()
