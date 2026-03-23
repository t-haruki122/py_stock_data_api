# FRONTEND Guide

プロジェクト全体説明へ戻る: [README.md](../README.md)

## 概要

フロントエンドはビルドステップなしの ES Modules 構成です。`index.html` では `type="module"` で `frontend/app.js` を読み込み、各機能モジュールを `import` して構成しています。

## 主要ファイル

- エントリポイント: `frontend/app.js`
- APIヘルパー: `frontend/js/api.js`
- 共有状態: `frontend/js/state.js`
- 詳細表示: `frontend/js/detail.js`
- 価格チャート: `frontend/js/chart.js`
- 財務チャート: `frontend/js/financial-chart.js`
- リスト管理: `frontend/js/list.js`
- 認証UI: `frontend/js/auth.js`
- 統計表示: `frontend/js/stats.js`
- ユーティリティ: `frontend/js/utils.js`

## 実行方法

バックエンドを起動すると、ルート (`/`) で `frontend/index.html` が配信されます。

```bash
python -m uvicorn app.main:app --reload
```

ブラウザ: `http://localhost:8000/`

## メモ

- HTML の inline handler (`onclick` / `onchange`) ではなく、JSモジュール側のイベント登録に統一しています。
