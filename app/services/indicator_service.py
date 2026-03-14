"""指数サービス - キャッシュ付き投資指数取得"""

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yfinance_client import YFinanceClient
from app.models.db_models import Indicator
from app.config import get_settings
from app.stats import stats

settings = get_settings()
_client = YFinanceClient()


async def get_indicators(symbol: str, db: AsyncSession) -> dict:
    """
    投資指数を取得（キャッシュ優先）

    キャッシュTTL: 1日
    """
    # キャッシュ確認
    cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_history)
    stmt = (
        select(Indicator)
        .where(Indicator.symbol == symbol.upper())
        .where(Indicator.cached_at >= cutoff)
        .order_by(Indicator.cached_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()

    if cached:
        stats.log_cache_hit()
        return {
            "symbol": cached.symbol,
            "roe": cached.roe,
            "roa": cached.roa,
            "pbr": cached.pbr,
            "per": cached.per,
            "eps": cached.eps,
            "dividend_yield": cached.dividend_yield,
            "mix_index": cached.mix_index,
            "profit_margin": cached.profit_margin,
            "debt_to_equity": cached.debt_to_equity,
        }

    # 外部APIから取得
    stats.log_api_call()
    data = _client.get_indicators(symbol)

    # キャッシュに保存
    record = Indicator(
        symbol=data["symbol"],
        roe=data.get("roe"),
        roa=data.get("roa"),
        pbr=data.get("pbr"),
        per=data.get("per"),
        eps=data.get("eps"),
        dividend_yield=data.get("dividend_yield"),
        mix_index=data.get("mix_index"),
        profit_margin=data.get("profit_margin"),
        debt_to_equity=data.get("debt_to_equity"),
        cached_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()

    return data
