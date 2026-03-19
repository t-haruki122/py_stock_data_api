"""yfinance ラッパークライアント"""

import logging
import yfinance as yf
from datetime import datetime, date, timedelta
import math
from typing import Any

from app.exceptions import SymbolNotFoundError, ExternalAPIError


logger = logging.getLogger("app.external.yfinance")


class YFinanceClient:
    """yfinanceライブラリを使用した株価・財務データ取得クライアント"""

    def get_current_price(self, symbol: str) -> dict[str, Any]:
        """
        現在の株価を取得

        Returns:
            {"symbol": str, "price": float, "timestamp": str}
        """
        try:
            logger.info("External API call: yfinance get_current_price symbol=%s", symbol.upper())
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # 価格を取得（複数のフィールドをフォールバック）
            price = (
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )

            if price is None:
                raise SymbolNotFoundError(symbol)

            timestamp = datetime.utcnow().isoformat() + "Z"

            return {
                "symbol": symbol.upper(),
                "price": float(price),
                "timestamp": timestamp,
            }
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(f"Failed to fetch price for {symbol}: {str(e)}")

    def get_exchange_rate(self, pair: str) -> dict[str, Any]:
        """
        為替レートを取得
        Args:
            pair: 為替ペア (例: "USDJPY=X")
        Returns:
            {"pair": str, "rate": float, "timestamp": str}
        """
        try:
            logger.info("External API call: yfinance get_exchange_rate pair=%s", pair.upper())
            ticker = yf.Ticker(pair)
            info = ticker.info

            # ask, bid, regularMarketPrice などから価格を取得
            rate = (
                info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            
            # yfinanceの仕様変更でinfoから取れない場合
            if rate is None:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])

            if rate is None:
                raise ExternalAPIError(f"Failed to fetch rate for {pair}")

            timestamp = datetime.utcnow().isoformat() + "Z"

            return {
                "pair": pair.upper(),
                "rate": float(rate),
                "timestamp": timestamp,
            }
        except Exception as e:
            raise ExternalAPIError(f"Failed to fetch exchange rate for {pair}: {str(e)}")

    def get_history(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        interval: str = "1d",
    ) -> list[dict[str, Any]]:
        """
        過去の株価データを取得

        Args:
            symbol: ティッカーシンボル
            start_date: 開始日 (YYYY-MM-DD)
            end_date: 終了日 (YYYY-MM-DD)
            interval: データ間隔 (1d, 1wk, 1mo等)

        Returns:
            [{"date": str, "open": float, "high": float, "low": float,
              "close": float, "volume": int}, ...]
        """
        try:
            logger.info(
                "External API call: yfinance get_history symbol=%s interval=%s start=%s end=%s",
                symbol.upper(),
                interval,
                start_date,
                end_date,
            )
            ticker = yf.Ticker(symbol)

            # デフォルトは直近1ヶ月
            kwargs: dict[str, Any] = {"interval": interval}
            if start_date:
                kwargs["start"] = start_date
            if end_date:
                kwargs["end"] = end_date
            if not start_date and not end_date:
                kwargs["period"] = "1mo"

            hist = ticker.history(**kwargs)

            if hist.empty:
                raise SymbolNotFoundError(symbol)

            records = []
            for idx, row in hist.iterrows():
                record = {
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2) if row["Open"] else None,
                    "high": round(float(row["High"]), 2) if row["High"] else None,
                    "low": round(float(row["Low"]), 2) if row["Low"] else None,
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]) if row["Volume"] else None,
                }
                records.append(record)

            return records
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch history for {symbol}: {str(e)}"
            )

    def get_financials(self, symbol: str) -> dict[str, Any]:
        """
        財務情報を取得

        Returns:
            {"symbol": str, "revenue": int, "net_income": int,
             "eps": float, "pe_ratio": float}
        """
        try:
            logger.info("External API call: yfinance get_financials symbol=%s", symbol.upper())
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("quoteType") is None:
                raise SymbolNotFoundError(symbol)

            return {
                "symbol": symbol.upper(),
                "revenue": info.get("totalRevenue"),
                "net_income": info.get("netIncomeToCommon"),
                "eps": info.get("trailingEps"),
                "pe_ratio": info.get("trailingPE"),
            }
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch financials for {symbol}: {str(e)}"
            )

    def get_financial_history(self, symbol: str, limit: int = 6) -> dict[str, Any]:
        """
        年次の財務履歴（売上高・純利益）を取得

        Returns:
            {"symbol": str, "history": [{"period": str, "revenue": int, "net_income": int}, ...]}
        """
        try:
            logger.info(
                "External API call: yfinance get_financial_history symbol=%s limit=%s",
                symbol.upper(),
                limit,
            )
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("quoteType") is None:
                raise SymbolNotFoundError(symbol)

            financials = ticker.financials
            if financials is None or financials.empty:
                return {"symbol": symbol.upper(), "history": []}

            entries: list[dict[str, Any]] = []
            columns = list(financials.columns)

            for col in columns:
                period_label = col.strftime("%Y") if isinstance(col, (datetime, date)) else str(col)

                revenue = None
                net_income = None
                if "Total Revenue" in financials.index:
                    raw_revenue = financials.at["Total Revenue", col]
                    if raw_revenue is not None and not (isinstance(raw_revenue, float) and math.isnan(raw_revenue)):
                        revenue = int(raw_revenue)
                if "Net Income" in financials.index:
                    raw_net_income = financials.at["Net Income", col]
                    if raw_net_income is not None and not (isinstance(raw_net_income, float) and math.isnan(raw_net_income)):
                        net_income = int(raw_net_income)

                entries.append(
                    {
                        "period": period_label,
                        "revenue": revenue,
                        "net_income": net_income,
                    }
                )

            # yfinanceは新しい期間が先頭になりやすいので、古い順に整列
            entries.sort(key=lambda x: x["period"])
            if limit > 0:
                entries = entries[-limit:]

            return {"symbol": symbol.upper(), "history": entries}
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch financial history for {symbol}: {str(e)}"
            )

    def get_dividend_history(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        """
        配当履歴（年間1株配当 + 年利換算の配当利回り）を年次で取得

        Returns:
            {"symbol": str, "history": [{"date": str, "dividend_per_share": float, "dividend_yield": float | None, "year_end_close": float | None}, ...]}
        """
        try:
            logger.info(
                "External API call: yfinance get_dividend_history symbol=%s limit=%s",
                symbol.upper(),
                limit,
            )
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("quoteType") is None:
                raise SymbolNotFoundError(symbol)

            all_dividends = ticker.dividends
            if all_dividends is None or all_dividends.empty:
                return {"symbol": symbol.upper(), "history": []}

            all_dividends = all_dividends.sort_index()
            years = sorted({int(idx.year) for idx in all_dividends.index})
            if limit > 0:
                years = years[-limit:]

            first_year = years[0]
            last_year = years[-1]
            history_start = f"{first_year}-01-01"
            history_end = f"{last_year + 1}-01-10"
            price_hist = ticker.history(
                start=history_start,
                end=history_end,
                interval="1d",
                auto_adjust=False,
                actions=False,
            )

            year_end_close_by_year: dict[int, float] = {}
            if price_hist is not None and not price_hist.empty:
                try:
                    closes = price_hist["Close"].dropna()
                    for year in years:
                        year_closes = closes[closes.index.year == year]
                        if not year_closes.empty:
                            year_end_close_by_year[year] = float(year_closes.iloc[-1])
                except Exception:
                    year_end_close_by_year = {}

            entries: list[dict[str, Any]] = []
            for year in years:
                year_dividends = all_dividends[all_dividends.index.year == year]
                if year_dividends is None or year_dividends.empty:
                    continue

                annual_dividend_per_share = float(year_dividends.sum())
                if math.isnan(annual_dividend_per_share):
                    continue

                close_price = year_end_close_by_year.get(year)

                annual_dividend_yield = None
                if close_price is not None and close_price > 0:
                    annual_dividend_yield = round((annual_dividend_per_share / close_price) * 100, 2)

                entries.append(
                    {
                        "date": str(year),
                        "dividend_per_share": round(annual_dividend_per_share, 4),
                        "dividend_yield": annual_dividend_yield,
                        "year_end_close": round(close_price, 4) if close_price is not None else None,
                    }
                )

            return {"symbol": symbol.upper(), "history": entries}
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch dividend history for {symbol}: {str(e)}"
            )

    def get_company_profile(self, symbol: str) -> dict[str, Any]:
        """
        会社プロフィールを取得

        Returns:
            {"symbol": str, "name": str, "sector": str, "industry": str,
             "employees": int, "summary": str, "market_cap": int, "currency": str,
             "website": str, "country": str}
        """
        try:
            logger.info("External API call: yfinance get_company_profile symbol=%s", symbol.upper())
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("quoteType") is None:
                raise SymbolNotFoundError(symbol)

            return {
                "symbol": symbol.upper(),
                "name": info.get("shortName") or info.get("longName") or symbol.upper(),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "employees": info.get("fullTimeEmployees"),
                "summary": info.get("longBusinessSummary"),
                "market_cap": info.get("marketCap"),
                "currency": info.get("currency", "USD"),
                "website": info.get("website"),
                "country": info.get("country"),
            }
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch profile for {symbol}: {str(e)}"
            )

    def get_indicators(self, symbol: str) -> dict[str, Any]:
        """
        投資指数を取得

        Returns:
            {"symbol": str, "roe": float, "roa": float, "pbr": float,
             "per": float, "eps": float, "dividend_yield": float,
             "mix_index": float, "profit_margin": float, "debt_to_equity": float}
        """
        try:
            logger.info("External API call: yfinance get_indicators symbol=%s", symbol.upper())
            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or info.get("quoteType") is None:
                raise SymbolNotFoundError(symbol)

            roe = info.get("returnOnEquity")
            roa = info.get("returnOnAssets")
            pbr = info.get("priceToBook")
            per = info.get("trailingPE")
            eps = info.get("trailingEps")
            dividend_yield = info.get("dividendYield")
            profit_margin = info.get("profitMargins")
            debt_to_equity = info.get("debtToEquity")

            # ミックス指数 = PER × PBR（低いほど割安）
            mix_index = None
            if per is not None and pbr is not None:
                mix_index = round(per * pbr, 2)

            return {
                "symbol": symbol.upper(),
                "roe": round(roe * 100, 2) if roe is not None else None,
                "roa": round(roa * 100, 2) if roa is not None else None,
                "pbr": round(pbr, 2) if pbr is not None else None,
                "per": round(per, 2) if per is not None else None,
                "eps": round(eps, 2) if eps is not None else None,
                "dividend_yield": round(dividend_yield, 2) if dividend_yield is not None else None,
                "mix_index": mix_index,
                "profit_margin": round(profit_margin * 100, 2) if profit_margin is not None else None,
                "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity is not None else None,
            }
        except SymbolNotFoundError:
            raise
        except Exception as e:
            raise ExternalAPIError(
                f"Failed to fetch indicators for {symbol}: {str(e)}"
            )
