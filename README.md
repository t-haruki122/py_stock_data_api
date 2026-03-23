# Stock Data Platform

株式分析・為替確認・ウォッチリスト管理をまとめて扱える、FastAPI + シンプルなフロントエンドで構成された投資支援アプリです。

## このプロジェクトの目的

このアプリは、以下の目的で作成しています。

- ポートフォリオ管理＆ダッシュボード
- 投資戦略のバックテスト用ソフトの土台

## できること（概要）

- 株価・企業情報・財務情報・投資指標・ニュースの取得
- 為替レートの取得
- ユーザー登録/ログインとウォッチリスト管理
- API利用統計の確認

## ドキュメント構成

- フロントエンド詳細: [docs/FRONTEND.md](docs/FRONTEND.md)
- バックエンドAPI詳細: [docs/API.md](docs/API.md)

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# サーバー起動
python -m uvicorn app.main:app --reload
```

## アクセス先

- アプリ: `http://localhost:8000/`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 画面イメージ

### 銘柄リスト比較
![銘柄リスト比較](docs/images/ScreenShots_2.png)

### 詳細ビュー
![詳細ビュー](docs/images/ScreenShots_1.png)

### システム統計
![システム統計](docs/images/ScreenShots_3.png)
