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


def _calculate_sma(closes: list[float], period: int) -> list[float | None]:
    """単純移動平均 (SMA) を計算"""
    sma = []
    for i in range(len(closes)):
        if i < period - 1:
            sma.append(None)
            continue
        window = closes[i - period + 1 : i + 1]
        sma.append(sum(window) / period)
    return sma


def _calculate_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """相対力指数 (RSI) を計算"""
    rsi = []
    gains = 0.0
    losses = 0.0

    for i in range(len(closes)):
        if i == 0:
            rsi.append(None)
            continue
        
        diff = closes[i] - closes[i - 1]
        if i <= period:
            if diff >= 0:
                gains += diff
            else:
                losses -= diff
            
            if i == period:
                if losses == 0:
                    rsi.append(100.0)
                else:
                    rs = (gains / period) / (losses / period)
                    rsi.append(100.0 - (100.0 / (1.0 + rs)))
            else:
                rsi.append(None)
        else:
            current_gain = diff if diff >= 0 else 0.0
            current_loss = -diff if diff < 0 else 0.0
            gains = (gains * (period - 1) + current_gain) / period
            losses = (losses * (period - 1) + current_loss) / period
            
            if losses == 0:
                rsi.append(100.0)
            else:
                rs = (gains / period) / (losses / period)
                rsi.append(100.0 - (100.0 / (1.0 + rs)))
                
    return rsi


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
    過去の株価データを取得（キャッシュ優先・指標計算付き）
    """
    # 指標計算用に取得期間を過去へ拡張する
    fetch_start_date = start_date
    if start_date:
        start_dt_req = datetime.strptime(start_date, "%Y-%m-%d")
        if interval == "1d":
            fetch_start_dt = start_dt_req - timedelta(days=365)
        else:
            fetch_start_dt = start_dt_req - timedelta(days=365 * 3)
        fetch_start_date = fetch_start_dt.strftime("%Y-%m-%d")

    records = []

    # 日次データ(1d)のみDBキャッシュを利用する
    if interval == "1d":
        cutoff = datetime.utcnow() - timedelta(seconds=settings.cache_ttl_history)
        stmt = (
            select(StockPrice)
            .where(StockPrice.symbol == symbol.upper())
            .where(StockPrice.cached_at >= cutoff)
            .where(StockPrice.open.isnot(None))
            .order_by(StockPrice.timestamp.asc())
        )

        if fetch_start_date:
            stmt = stmt.where(StockPrice.timestamp >= datetime.strptime(fetch_start_date, "%Y-%m-%d"))
        if end_date:
            stmt = stmt.where(StockPrice.timestamp <= datetime.strptime(end_date, "%Y-%m-%d"))

        result = await db.execute(stmt)
        cached_records = result.scalars().all()

        if cached_records:
            # キャッシュが要求された開始日を十分にカバーしているかチェックする（土日祝日を考慮して7日間の猶予）
            first_record_date = cached_records[0].timestamp
            fetch_start_dt_obj = datetime.strptime(fetch_start_date, "%Y-%m-%d") if fetch_start_date else None
            
            is_cache_valid = True
            if fetch_start_dt_obj and (first_record_date - fetch_start_dt_obj).days > 7:
                is_cache_valid = False

            if is_cache_valid:
                stats.log_cache_hit()
                records = [
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

    # キャッシュがない場合は外部APIから取得
    if not records:
        stats.log_api_call()
        records = _client.get_history(symbol, fetch_start_date, end_date, interval)

        # 取得したデータをDBにキャッシュする（日次データのみ）
        if interval == "1d":
            # 重複挿入を防ぐため、既存の該当シンボルのキャッシュを削除
            await db.execute(delete(StockPrice).where(StockPrice.symbol == symbol.upper()))
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

    # 指標の計算
    if records:
        closes = [r["close"] for r in records]
        sma_25 = _calculate_sma(closes, 25)
        sma_50 = _calculate_sma(closes, 50)
        sma_75 = _calculate_sma(closes, 75)
        sma_200 = _calculate_sma(closes, 200)
        rsi_14 = _calculate_rsi(closes, 14)

        for i, rec in enumerate(records):
            rec["sma_25"] = round(sma_25[i], 2) if sma_25[i] is not None else None
            rec["sma_50"] = round(sma_50[i], 2) if sma_50[i] is not None else None
            rec["sma_75"] = round(sma_75[i], 2) if sma_75[i] is not None else None
            rec["sma_200"] = round(sma_200[i], 2) if sma_200[i] is not None else None
            rec["rsi_14"] = round(rsi_14[i], 2) if rsi_14[i] is not None else None

    # 要求されたオリジナル期間でフィルタリング
    if start_date:
        records = [r for r in records if r["date"] >= start_date]
    if end_date:
        records = [r for r in records if r["date"] <= end_date]

    return {"symbol": symbol.upper(), "history": records}
