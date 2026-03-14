"""ユーザー・リスト・タグ管理のサービスレイヤー"""

import hashlib
import json
from datetime import datetime

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import User, UserList, UserListItem


def _hash_password(password: str) -> str:
    """パスワードをSHA-256でハッシュ化"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ========== ユーザー ==========

async def register_user(username: str, password: str, db: AsyncSession) -> User:
    """ユーザー登録"""
    # 重複チェック
    result = await db.execute(select(User).where(User.username == username))
    existing = result.scalar_one_or_none()
    if existing:
        raise ValueError("このユーザー名は既に使用されています")

    user = User(
        username=username,
        password_hash=_hash_password(password),
        created_at=datetime.utcnow(),
    )
    db.add(user)
    await db.flush()  # IDを取得するためflush

    # デフォルトリストを自動作成
    now = datetime.utcnow()
    default_list = UserList(
        user_id=user.id,
        name="マイリスト",
        created_at=now,
        updated_at=now,
    )
    db.add(default_list)

    await db.commit()
    await db.refresh(user)
    return user


async def login_user(username: str, password: str, db: AsyncSession) -> User:
    """ログイン（ユーザー認証）"""
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or user.password_hash != _hash_password(password):
        raise ValueError("ユーザー名またはパスワードが正しくありません")
    return user


async def get_or_create_default_list(user_id: int, db: AsyncSession) -> UserList:
    """ユーザーのデフォルトリストを取得（なければ作成）"""
    result = await db.execute(
        select(UserList).where(UserList.user_id == user_id).order_by(UserList.created_at.asc())
    )
    user_list = result.scalars().first()
    if user_list:
        return user_list

    # リストがなければ作成
    now = datetime.utcnow()
    user_list = UserList(
        user_id=user_id,
        name="マイリスト",
        created_at=now,
        updated_at=now,
    )
    db.add(user_list)
    await db.commit()
    await db.refresh(user_list)
    return user_list


# ========== リスト ==========

async def get_user_lists(user_id: int, db: AsyncSession) -> list[UserList]:
    """ユーザーのリスト一覧を取得"""
    result = await db.execute(
        select(UserList).where(UserList.user_id == user_id).order_by(UserList.updated_at.desc())
    )
    return list(result.scalars().all())


async def create_list(user_id: int, name: str, db: AsyncSession) -> UserList:
    """リストを作成"""
    now = datetime.utcnow()
    user_list = UserList(
        user_id=user_id,
        name=name,
        created_at=now,
        updated_at=now,
    )
    db.add(user_list)
    await db.commit()
    await db.refresh(user_list)
    return user_list


async def get_list_detail(user_id: int, list_id: int, db: AsyncSession) -> dict:
    """リスト詳細（アイテム含む）を取得"""
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    user_list = result.scalar_one_or_none()
    if not user_list:
        raise ValueError("リストが見つかりません")

    items_result = await db.execute(
        select(UserListItem).where(UserListItem.list_id == list_id)
    )
    items = list(items_result.scalars().all())

    return {
        "id": user_list.id,
        "name": user_list.name,
        "items": [
            {
                "symbol": item.symbol,
                "tags": json.loads(item.tags) if item.tags else [],
            }
            for item in items
        ],
        "created_at": user_list.created_at.isoformat(),
        "updated_at": user_list.updated_at.isoformat(),
    }


async def update_list(user_id: int, list_id: int, name: str, db: AsyncSession) -> UserList:
    """リスト名を更新"""
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    user_list = result.scalar_one_or_none()
    if not user_list:
        raise ValueError("リストが見つかりません")

    user_list.name = name
    user_list.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user_list)
    return user_list


async def delete_list(user_id: int, list_id: int, db: AsyncSession) -> None:
    """リストを削除（アイテムもCASCADE削除）"""
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    user_list = result.scalar_one_or_none()
    if not user_list:
        raise ValueError("リストが見つかりません")

    # アイテムを先に削除（CASCADEが効かないDB向け対応）
    await db.execute(
        delete(UserListItem).where(UserListItem.list_id == list_id)
    )
    await db.delete(user_list)
    await db.commit()


# ========== リストアイテム ==========

async def add_list_item(
    user_id: int, list_id: int, symbol: str, tags: list[str], db: AsyncSession
) -> UserListItem:
    """リストにアイテムを追加"""
    # リスト所有権チェック
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise ValueError("リストが見つかりません")

    # 重複チェック
    result = await db.execute(
        select(UserListItem).where(
            UserListItem.list_id == list_id, UserListItem.symbol == symbol
        )
    )
    if result.scalar_one_or_none():
        raise ValueError(f"{symbol} は既にリストに存在します")

    item = UserListItem(
        list_id=list_id,
        symbol=symbol.upper(),
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
    )
    db.add(item)

    # リストの updated_at を更新
    list_result = await db.execute(
        select(UserList).where(UserList.id == list_id)
    )
    user_list = list_result.scalar_one()
    user_list.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(item)
    return item


async def remove_list_item(
    user_id: int, list_id: int, symbol: str, db: AsyncSession
) -> None:
    """リストからアイテムを削除"""
    # リスト所有権チェック
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise ValueError("リストが見つかりません")

    result = await db.execute(
        select(UserListItem).where(
            UserListItem.list_id == list_id, UserListItem.symbol == symbol.upper()
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ValueError(f"{symbol} はリストに存在しません")

    await db.delete(item)
    await db.commit()


async def update_item_tags(
    user_id: int, list_id: int, symbol: str, tags: list[str], db: AsyncSession
) -> UserListItem:
    """アイテムのタグを更新"""
    # リスト所有権チェック
    result = await db.execute(
        select(UserList).where(UserList.id == list_id, UserList.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise ValueError("リストが見つかりません")

    result = await db.execute(
        select(UserListItem).where(
            UserListItem.list_id == list_id, UserListItem.symbol == symbol.upper()
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise ValueError(f"{symbol} はリストに存在しません")

    item.tags = json.dumps(tags, ensure_ascii=False) if tags else None
    await db.commit()
    await db.refresh(item)
    return item
