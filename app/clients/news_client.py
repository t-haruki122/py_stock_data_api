"""ニュース取得クライアント"""

import logging
from gnews import GNews
from typing import Any

from app.exceptions import ExternalAPIError


logger = logging.getLogger("app.external.gnews")


class NewsClient:
    """GNewsライブラリを使用したニュース取得クライアント"""

    def __init__(self):
        self._gnews = GNews(
            language="en",
            country="US",
            max_results=10,
        )

    def get_news(self, symbol: str, company_name: str | None = None) -> list[dict[str, Any]]:
        """
        指定シンボルに関連するニュースを取得

        Args:
            symbol: ティッカーシンボル
            company_name: 会社名（検索精度向上のため）

        Returns:
            [{"title": str, "url": str, "published_at": str}, ...]
        """
        try:
            # 会社名があればそれを使い、なければシンボル + "stock" で検索
            query = f"{company_name} stock" if company_name else f"{symbol} stock"
            logger.info("External API call: gnews get_news query=%s", query)
            articles = self._gnews.get_news(query)

            if not articles:
                return []

            results = []
            for article in articles:
                results.append({
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "published_at": article.get("published date", ""),
                    "source": article.get("publisher", {}).get("title", "")
                    if isinstance(article.get("publisher"), dict)
                    else str(article.get("publisher", "")),
                })

            return results
        except Exception as e:
            raise ExternalAPIError(f"Failed to fetch news for {symbol}: {str(e)}")
