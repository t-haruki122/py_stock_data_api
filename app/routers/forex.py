"""為替データ APIルーター"""

from fastapi import APIRouter
from pydantic import BaseModel
from app.services import forex_service

router = APIRouter(prefix="/forex", tags=["forex"])

class ExchangeRateResponse(BaseModel):
    pair: str
    rate: float
    timestamp: str

@router.get(
    "/{pair}",
    response_model=ExchangeRateResponse,
    summary="為替レートを取得",
    description="指定された為替ペア（例: USDJPY=X）の現在のレートを返します。",
)
async def get_exchange_rate(pair: str):
    """現在の為替レートを取得"""
    # フロントエンドから 'USDJPY' と送られてきた場合などに '=X' を補完
    if not pair.endswith("=X"):
        pair = f"{pair}=X"
    return await forex_service.get_exchange_rate(pair)
