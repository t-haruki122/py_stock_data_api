"""ユーザー・リスト・タグ関連のPydanticスキーマ"""

from pydantic import BaseModel


# --- ユーザー ---

class UserRegisterRequest(BaseModel):
    """ユーザー登録リクエスト"""
    username: str
    password: str


class UserLoginRequest(BaseModel):
    """ログインリクエスト"""
    username: str
    password: str


class UserResponse(BaseModel):
    """ユーザーレスポンス"""
    id: int
    username: str


# --- リスト ---

class ListCreateRequest(BaseModel):
    """リスト作成リクエスト"""
    name: str


class ListUpdateRequest(BaseModel):
    """リスト更新リクエスト"""
    name: str


class ListItemAddRequest(BaseModel):
    """リストアイテム追加リクエスト"""
    symbol: str
    tags: list[str] = []


class TagUpdateRequest(BaseModel):
    """タグ更新リクエスト"""
    tags: list[str]


class ListItemResponse(BaseModel):
    """リストアイテムレスポンス"""
    symbol: str
    tags: list[str]


class ListResponse(BaseModel):
    """リストレスポンス"""
    id: int
    name: str
    created_at: str
    updated_at: str


class ListDetailResponse(BaseModel):
    """リスト詳細レスポンス（アイテム含む）"""
    id: int
    name: str
    items: list[ListItemResponse]
    created_at: str
    updated_at: str


class ListsResponse(BaseModel):
    """リスト一覧レスポンス"""
    lists: list[ListResponse]


class MessageResponse(BaseModel):
    """汎用メッセージレスポンス"""
    message: str


class StockMemoRequest(BaseModel):
    """銘柄メモ保存リクエスト"""
    memo: str | None = None


class StockMemoResponse(BaseModel):
    """銘柄メモレスポンス"""
    symbol: str
    memo: str | None = None
    updated_at: str | None = None
