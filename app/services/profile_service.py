"""プロフィールサービス - キャッシュ付き会社情報取得"""

from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yfinance_client import YFinanceClient
from app.models.db_models import CompanyProfile
from app.config import get_settings
from app.stats import stats

settings = get_settings()
_client = YFinanceClient()


async def get_profile(symbol: str, db: AsyncSession) -> dict:
    """
    会社プロフィールを取得（キャッシュ優先）

    キャッシュTTL: 1日
    """
    # キャッシュ確認
    cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_history)
    stmt = (
        select(CompanyProfile)
        .where(CompanyProfile.symbol == symbol.upper())
        .where(CompanyProfile.cached_at >= cutoff)
        .order_by(CompanyProfile.cached_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()

    if cached:
        stats.log_cache_hit()
        return {
            "symbol": cached.symbol,
            "name": cached.name,
            "sector": cached.sector,
            "industry": cached.industry,
            "employees": cached.employees,
            "summary": cached.summary,
            "market_cap": cached.market_cap,
            "currency": cached.currency,
            "website": cached.website,
            "country": cached.country,
        }

    # 外部APIから取得
    stats.log_api_call()
    data = _client.get_company_profile(symbol)

    # キャッシュに保存
    record = CompanyProfile(
        symbol=data["symbol"],
        name=data["name"],
        sector=data.get("sector"),
        industry=data.get("industry"),
        employees=data.get("employees"),
        summary=data.get("summary"),
        market_cap=data.get("market_cap"),
        currency=data.get("currency"),
        website=data.get("website"),
        country=data.get("country"),
        cached_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()

    return data
