"""株価サービス - キャッシュ付き株価データ取得"""

from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.yfinance_client import YFinanceClient
from app.models.db_models import StockPrice
from app.config import get_settings
from app.stats import stats

settings = get_settings()
_client = YFinanceClient()


async def get_current_price(symbol: str, db: AsyncSession) -> dict:
    """
    現在の株価を取得（キャッシュ優先）

    キャッシュTTL: 1分
    """
    # キャッシュ確認
    cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_current_price)
    stmt = (
        select(StockPrice)
        .where(StockPrice.symbol == symbol.upper())
        .where(StockPrice.cached_at >= cutoff)
        .order_by(StockPrice.cached_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    cached = result.scalar_one_or_none()

    if cached:
        stats.log_cache_hit()
        return {
            "symbol": cached.symbol,
            "price": cached.close,
            "timestamp": cached.timestamp.isoformat() + "Z",
        }

    # 外部APIから取得
    stats.log_api_call()
    data = _client.get_current_price(symbol)

    # キャッシュに保存
    record = StockPrice(
        symbol=data["symbol"],
        timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
        close=data["price"],
        cached_at=datetime.utcnow(),
    )
    db.add(record)
    await db.commit()

    return data


async def get_history(
    symbol: str,
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
) -> dict:
    """
    過去の株価データを取得（キャッシュ優先）

    キャッシュTTL: 1日
    """
    # 日次データ(1d)のみDBキャッシュを利用する
    if interval == "1d":
        # キャッシュキーとして日付範囲を使用
        cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_history)

        # キャッシュされたデータがあるか確認
        stmt = (
            select(StockPrice)
            .where(StockPrice.symbol == symbol.upper())
            .where(StockPrice.cached_at >= cutoff)
            .where(StockPrice.open.isnot(None))  # historyデータはopenがある
            .order_by(StockPrice.timestamp.asc())
        )

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            stmt = stmt.where(StockPrice.timestamp >= start_dt)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            stmt = stmt.where(StockPrice.timestamp <= end_dt)

        result = await db.execute(stmt)
        cached_records = result.scalars().all()

        if cached_records:
            stats.log_cache_hit()
            history = [
                {
                    "date": r.timestamp.strftime("%Y-%m-%d"),
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in cached_records
            ]
            return {"symbol": symbol.upper(), "history": history}

    # 外部APIから取得
    stats.log_api_call()
    records = _client.get_history(symbol, start_date, end_date, interval)

    # 取得したデータをDBにキャッシュする（日次データのみ）
    if interval == "1d":
        for rec in records:
            db_record = StockPrice(
                symbol=symbol.upper(),
                timestamp=datetime.strptime(rec["date"], "%Y-%m-%d"),
                open=rec.get("open"),
                high=rec.get("high"),
                low=rec.get("low"),
                close=rec["close"],
                volume=rec.get("volume"),
                cached_at=datetime.utcnow(),
            )
            db.add(db_record)
        await db.commit()

    return {"symbol": symbol.upper(), "history": records}
