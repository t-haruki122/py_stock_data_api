"""財務サービス - キャッシュ付き財務データ取得"""

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yfinance_client import YFinanceClient
from app.models.db_models import Financial
from app.config import get_settings
from app.stats import stats

settings = get_settings()
_client = YFinanceClient()


async def get_financials(symbol: str, db: AsyncSession) -> dict:
    """
    財務情報を取得（キャッシュ優先）

    キャッシュTTL: 四半期（約90日）
    """
    # キャッシュ確認
    cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_financials)
    stmt = (
        select(Financial)
        .where(Financial.symbol == symbol.upper())
        .where(Financial.cached_at >= cutoff)
        .order_by(Financial.cached_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()

    if cached:
        stats.log_cache_hit()
        return {
            "symbol": cached.symbol,
            "revenue": cached.revenue,
            "net_income": cached.net_income,
            "eps": cached.eps,
            "pe_ratio": cached.pe_ratio,
        }

    # 外部APIから取得
    stats.log_api_call()
    data = _client.get_financials(symbol)

    # キャッシュに保存
    record = Financial(
        symbol=data["symbol"],
        revenue=data.get("revenue"),
        net_income=data.get("net_income"),
        eps=data.get("eps"),
        pe_ratio=data.get("pe_ratio"),
        cached_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()

    return data
