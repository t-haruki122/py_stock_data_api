"""ユーザー・リスト・タグ APIルーター"""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    ListCreateRequest,
    ListUpdateRequest,
    ListItemAddRequest,
    TagUpdateRequest,
    ListResponse,
    ListDetailResponse,
    ListsResponse,
    ListItemResponse,
    MessageResponse,
)
from app.services import user_service

router = APIRouter(prefix="/user", tags=["user"])


# ========== ユーザー認証 ==========

@router.post(
    "/register",
    response_model=UserResponse,
    summary="ユーザー登録",
    description="新しいユーザーアカウントを作成します。",
)
async def register(req: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """ユーザー登録"""
    if not req.username or len(req.username) < 2:
        raise HTTPException(status_code=400, detail="ユーザー名は2文字以上にしてください")
    if not req.password or len(req.password) < 4:
        raise HTTPException(status_code=400, detail="パスワードは4文字以上にしてください")

    try:
        user = await user_service.register_user(req.username, req.password, db)
        return UserResponse(id=user.id, username=user.username)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post(
    "/login",
    response_model=UserResponse,
    summary="ログイン",
    description="ユーザー名とパスワードで認証し、ユーザー情報を返します。",
)
async def login(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """ログイン"""
    try:
        user = await user_service.login_user(req.username, req.password, db)
        return UserResponse(id=user.id, username=user.username)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get(
    "/{user_id}/default-list",
    response_model=ListDetailResponse,
    summary="デフォルトリストを取得",
    description="ユーザーのデフォルト銘柄リストを取得します（なければ自動作成）。",
)
async def get_default_list(user_id: int, db: AsyncSession = Depends(get_db)):
    """デフォルトリストを取得"""
    default_list = await user_service.get_or_create_default_list(user_id, db)
    try:
        return await user_service.get_list_detail(user_id, default_list.id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== リスト ==========

@router.get(
    "/{user_id}/lists",
    response_model=ListsResponse,
    summary="リスト一覧を取得",
)
async def get_lists(user_id: int, db: AsyncSession = Depends(get_db)):
    """ユーザーのリスト一覧"""
    lists = await user_service.get_user_lists(user_id, db)
    return ListsResponse(
        lists=[
            ListResponse(
                id=lst.id,
                name=lst.name,
                created_at=lst.created_at.isoformat(),
                updated_at=lst.updated_at.isoformat(),
            )
            for lst in lists
        ]
    )


@router.post(
    "/{user_id}/lists",
    response_model=ListResponse,
    summary="リスト作成",
)
async def create_list(user_id: int, req: ListCreateRequest, db: AsyncSession = Depends(get_db)):
    """新しいリストを作成"""
    if not req.name:
        raise HTTPException(status_code=400, detail="リスト名を入力してください")

    lst = await user_service.create_list(user_id, req.name, db)
    return ListResponse(
        id=lst.id,
        name=lst.name,
        created_at=lst.created_at.isoformat(),
        updated_at=lst.updated_at.isoformat(),
    )


@router.get(
    "/{user_id}/lists/{list_id}",
    response_model=ListDetailResponse,
    summary="リスト詳細を取得",
)
async def get_list_detail(user_id: int, list_id: int, db: AsyncSession = Depends(get_db)):
    """リスト詳細（アイテム含む）"""
    try:
        return await user_service.get_list_detail(user_id, list_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/{user_id}/lists/{list_id}",
    response_model=ListResponse,
    summary="リスト名を更新",
)
async def update_list(
    user_id: int, list_id: int, req: ListUpdateRequest, db: AsyncSession = Depends(get_db)
):
    """リスト名を変更"""
    try:
        lst = await user_service.update_list(user_id, list_id, req.name, db)
        return ListResponse(
            id=lst.id,
            name=lst.name,
            created_at=lst.created_at.isoformat(),
            updated_at=lst.updated_at.isoformat(),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/{user_id}/lists/{list_id}",
    response_model=MessageResponse,
    summary="リストを削除",
)
async def delete_list(user_id: int, list_id: int, db: AsyncSession = Depends(get_db)):
    """リストを削除"""
    try:
        await user_service.delete_list(user_id, list_id, db)
        return MessageResponse(message="リストを削除しました")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ========== リストアイテム ==========

@router.post(
    "/{user_id}/lists/{list_id}/items",
    response_model=ListItemResponse,
    summary="リストにアイテムを追加",
)
async def add_item(
    user_id: int, list_id: int, req: ListItemAddRequest, db: AsyncSession = Depends(get_db)
):
    """リストに銘柄を追加"""
    try:
        item = await user_service.add_list_item(user_id, list_id, req.symbol, req.tags, db)
        return ListItemResponse(
            symbol=item.symbol,
            tags=json.loads(item.tags) if item.tags else [],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/{user_id}/lists/{list_id}/items/{symbol}",
    response_model=MessageResponse,
    summary="リストからアイテムを削除",
)
async def remove_item(
    user_id: int, list_id: int, symbol: str, db: AsyncSession = Depends(get_db)
):
    """リストから銘柄を削除"""
    try:
        await user_service.remove_list_item(user_id, list_id, symbol, db)
        return MessageResponse(message=f"{symbol} をリストから削除しました")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put(
    "/{user_id}/lists/{list_id}/items/{symbol}/tags",
    response_model=ListItemResponse,
    summary="アイテムのタグを更新",
)
async def update_tags(
    user_id: int, list_id: int, symbol: str,
    req: TagUpdateRequest, db: AsyncSession = Depends(get_db),
):
    """銘柄のタグを更新"""
    try:
        item = await user_service.update_item_tags(user_id, list_id, symbol, req.tags, db)
        return ListItemResponse(
            symbol=item.symbol,
            tags=json.loads(item.tags) if item.tags else [],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
