"""データベース接続・セッション管理"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ベースモデル"""
    pass


async def init_db():
    """データベース初期化（テーブル作成）"""
    import app.models.db_models  # モデルをインポートしないとテーブルが作成されない
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """DBセッションの依存性注入用ジェネレータ"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
