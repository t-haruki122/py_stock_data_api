"""株価データ APIルーター"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.stock import (
    StockPriceResponse,
    StockHistoryResponse,
    FinancialResponse,
    FinancialHistoryResponse,
    NewsResponse,
    CompanyProfileResponse,
    IndicatorsResponse,
)
from app.services import stock_service, finance_service, news_service
from app.services import profile_service, indicator_service

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get(
    "/{symbol}",
    response_model=StockPriceResponse,
    summary="現在の株価を取得",
    description="指定されたシンボルの現在の株価を返します。",
)
async def get_stock_price(symbol: str, db: AsyncSession = Depends(get_db)):
    """現在の株価を取得"""
    return await stock_service.get_current_price(symbol, db)


@router.get(
    "/{symbol}/history",
    response_model=StockHistoryResponse,
    summary="過去の株価データを取得",
    description="指定された期間の過去株価データを返します。",
)
async def get_stock_history(
    symbol: str,
    start_date: str | None = Query(None, description="開始日 (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="終了日 (YYYY-MM-DD)"),
    interval: str = Query("1d", description="データ間隔 (1d, 1wk, 1mo)"),
    db: AsyncSession = Depends(get_db),
):
    """過去の株価データを取得"""
    return await stock_service.get_history(symbol, db, start_date, end_date, interval)


@router.get(
    "/{symbol}/financials",
    response_model=FinancialResponse,
    summary="財務情報を取得",
    description="指定されたシンボルの財務情報（売上、純利益、EPS、PE比率）を返します。",
)
async def get_financials(symbol: str, db: AsyncSession = Depends(get_db)):
    """財務情報を取得"""
    return await finance_service.get_financials(symbol, db)


@router.get(
    "/{symbol}/financials/history",
    response_model=FinancialHistoryResponse,
    summary="過去の財務情報を取得",
    description="指定されたシンボルの年次財務履歴（売上高・純利益）を返します。",
)
async def get_financial_history(
    symbol: str,
    limit: int = Query(6, ge=1, le=10, description="取得する年次データ件数"),
    db: AsyncSession = Depends(get_db),
):
    """過去の財務情報を取得"""
    return await finance_service.get_financial_history(symbol, db, limit=limit)


@router.get(
    "/{symbol}/news",
    response_model=NewsResponse,
    summary="関連ニュースを取得",
    description="指定されたシンボルに関連するニュースを返します。",
)
async def get_news(symbol: str, db: AsyncSession = Depends(get_db)):
    """関連ニュースを取得"""
    return await news_service.get_news(symbol, db)


@router.get(
    "/{symbol}/profile",
    response_model=CompanyProfileResponse,
    summary="会社プロフィールを取得",
    description="指定されたシンボルの会社情報（セクター、業種、時価総額等）を返します。",
)
async def get_profile(symbol: str, db: AsyncSession = Depends(get_db)):
    """会社プロフィールを取得"""
    return await profile_service.get_profile(symbol, db)


@router.get(
    "/{symbol}/indicators",
    response_model=IndicatorsResponse,
    summary="投資指数を取得",
    description="指定されたシンボルの投資指数（ROE、ROA、PBR、PER、ミックス指数等）を返します。",
)
async def get_indicators(symbol: str, db: AsyncSession = Depends(get_db)):
    """投資指数を取得"""
    return await indicator_service.get_indicators(symbol, db)
