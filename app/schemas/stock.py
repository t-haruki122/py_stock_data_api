"""Pydantic レスポンススキーマ"""

from pydantic import BaseModel
from datetime import datetime


# --- 株価 ---

class StockPriceResponse(BaseModel):
    """現在株価レスポンス"""
    symbol: str
    price: float
    timestamp: str


# --- 過去株価 ---

class HistoryEntry(BaseModel):
    """過去株価の1レコード"""
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: int | None = None
    sma_25: float | None = None
    sma_50: float | None = None
    sma_75: float | None = None
    sma_200: float | None = None
    rsi_14: float | None = None


class StockHistoryResponse(BaseModel):
    """過去株価レスポンス"""
    symbol: str
    history: list[HistoryEntry]


# --- 財務情報 ---

class FinancialResponse(BaseModel):
    """財務情報レスポンス"""
    symbol: str
    revenue: int | None = None
    net_income: int | None = None
    eps: float | None = None
    pe_ratio: float | None = None


class FinancialHistoryEntry(BaseModel):
    """過去財務情報の1レコード"""
    period: str
    revenue: int | None = None
    net_income: int | None = None


class FinancialHistoryResponse(BaseModel):
    """過去財務情報レスポンス"""
    symbol: str
    history: list[FinancialHistoryEntry]


class DividendHistoryEntry(BaseModel):
    """過去配当情報の1レコード"""
    date: str
    dividend_per_share: float | None = None
    dividend_yield: float | None = None
    year_end_close: float | None = None


class DividendHistoryResponse(BaseModel):
    """過去配当情報レスポンス"""
    symbol: str
    history: list[DividendHistoryEntry]


# --- ニュース ---

class NewsEntry(BaseModel):
    """ニュースの1記事"""
    title: str
    url: str
    published_at: str | None = None


class NewsResponse(BaseModel):
    """ニュースレスポンス"""
    symbol: str
    news: list[NewsEntry]


# --- 会社プロフィール ---

class CompanyProfileResponse(BaseModel):
    """会社プロフィールレスポンス"""
    symbol: str
    name: str
    sector: str | None = None
    industry: str | None = None
    employees: int | None = None
    summary: str | None = None
    market_cap: int | None = None
    currency: str | None = None
    website: str | None = None
    country: str | None = None


# --- 投資指数 ---

class IndicatorsResponse(BaseModel):
    """投資指数レスポンス"""
    symbol: str
    roe: float | None = None
    roa: float | None = None
    pbr: float | None = None
    per: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    mix_index: float | None = None
    profit_margin: float | None = None
    debt_to_equity: float | None = None


# --- エラー ---

class ErrorResponse(BaseModel):
    """エラーレスポンス"""
    detail: str
    status_code: int
