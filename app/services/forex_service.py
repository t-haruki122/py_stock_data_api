"""為替レートサービス"""

from datetime import datetime
from typing import Dict, Any
from app.clients.yfinance_client import YFinanceClient

_client = YFinanceClient()

# 簡易的なインメモリキャッシュ (TTL: 1時間)
_forex_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600 

async def get_exchange_rate(pair: str) -> dict[str, Any]:
    """
    指定された為替ペア（例: USDJPY=X）の現在のレートを取得
    """
    pair = pair.upper()
    now = datetime.utcnow()

    # キャッシュをチェック
    if pair in _forex_cache:
        cached_data = _forex_cache[pair]
        cached_time = cached_data.get("cached_at")
        if cached_time and (now - cached_time).total_seconds() < CACHE_TTL_SECONDS:
            return {
                "pair": pair,
                "rate": cached_data["rate"],
                "timestamp": cached_data["timestamp"],
            }

    # APIから取得
    data = _client.get_exchange_rate(pair)
    
    # キャッシュに保存
    _forex_cache[pair] = {
        "rate": data["rate"],
        "timestamp": data["timestamp"],
        "cached_at": now
    }
    
    return data
