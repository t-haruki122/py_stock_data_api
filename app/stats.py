"""アプリケーションのシステム統計情報管理"""

from datetime import datetime

class AppStats:
    def __init__(self):
        self.api_calls = 0
        self.cache_hits = 0
        self.started_at = datetime.utcnow()

    def log_api_call(self):
        """外部APIへのアクセスを記録"""
        self.api_calls += 1

    def log_cache_hit(self):
        """キャッシュからのデータ取得を記録"""
        self.cache_hits += 1

    def get_stats(self) -> dict:
        """現在の統計情報を取得"""
        total = self.api_calls + self.cache_hits
        hit_rate = 0.0
        if total > 0:
            hit_rate = round((self.cache_hits / total) * 100, 1)

        return {
            "api_calls": self.api_calls,
            "cache_hits": self.cache_hits,
            "total_requests": total,
            "hit_rate_percent": hit_rate,
            "uptime_seconds": int((datetime.utcnow() - self.started_at).total_seconds())
        }

# グローバルな統計インスタンス
stats = AppStats()
