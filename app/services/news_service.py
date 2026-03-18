"""ニュースサービス - キャッシュ付きニュース取得"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.news_client import NewsClient
from app.clients.yfinance_client import YFinanceClient
from app.models.db_models import News
from app.config import get_settings
from app.stats import stats

settings = get_settings()
_news_client = NewsClient()
_yf_client = YFinanceClient()
logger = logging.getLogger("app.services.news")


async def get_news(symbol: str, db: AsyncSession) -> dict:
    """
    ニュースを取得（キャッシュ優先）

    キャッシュTTL: 10分
    """
    # キャッシュ確認
    cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_news)
    stmt = (
        select(News)
        .where(News.symbol == symbol.upper())
        .where(News.cached_at >= cutoff)
        .order_by(News.cached_at.desc())
    )
    result = await db.execute(stmt)
    cached_records = result.scalars().all()

    if cached_records:
        stats.log_cache_hit()
        news_list = [
            {
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at,
            }
            for r in cached_records
        ]
        return {"symbol": symbol.upper(), "news": news_list}

    # 会社名を取得して検索精度を向上
    company_name = None
    try:
        import yfinance as yf
        logger.info(
            "External API call: yfinance company_name_lookup symbol=%s",
            symbol.upper(),
        )
        ticker = yf.Ticker(symbol)
        company_name = ticker.info.get("shortName") or ticker.info.get("longName")
    except Exception:
        pass

    # 外部APIから取得
    stats.log_api_call()
    articles = _news_client.get_news(symbol, company_name)

    # キャッシュに保存
    for article in articles:
        record = News(
            symbol=symbol.upper(),
            title=article["title"],
            url=article["url"],
            published_at=article.get("published_at", ""),
            source=article.get("source", ""),
            cached_at=datetime.utcnow(),
        )
        db.add(record)
    if articles:
        await db.commit()

    news_list = [
        {
            "title": a["title"],
            "url": a["url"],
            "published_at": a.get("published_at"),
        }
        for a in articles
    ]
    return {"symbol": symbol.upper(), "news": news_list}
