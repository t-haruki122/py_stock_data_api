# Backtest CLI Guide

プロジェクト全体説明へ戻る: [README.md](../README.md)

## 概要

Pythonだけで完結するバックテストCLIです。
ローカルで稼働中の `py_stock_data_api`（既定: `http://localhost:8000`）から株価や財務データを取得し、戦略検証をターミナルで実行します。

## 実行前提

- Python 3.x
- FastAPIサーバー起動済み
- 依存パッケージ導入済み（`pip install -r requirements.txt`）

## デスクトップGUI（実装中）

CLIロジックを利用するデスクトップGUIを追加しました。

```bash
python scripts/backtest_gui.py
```

現時点の対応範囲:

- 単一銘柄のバックテスト実行
- 非同期実行（UIをブロックしない）
- 実進捗バー（0-100%）表示
- キャンセル要求
- メトリクス表示
- チャート表示
- 取引詳細テーブル表示（日時/売買/価格/株数/手数料/損益/取引後現金/取引後総資産）
- 取引履歴CSV保存
- チャートPNG保存

## 実行例

```bash
# 単一銘柄で実行
python scripts/backtest_cli.py \
  --symbol AAPL \
  --start-date 2023-01-01 \
  --end-date 2024-12-31 \
  --interval 1d \
  --initial-capital 1000000 \
  --short-window 20 \
  --long-window 60 \
  --fee-rate 0.001

# ウォッチリスト（user_id + list_id）で実行
python scripts/backtest_cli.py \
  --user-id 1 \
  --watchlist-id 2 \
  --start-date 2023-01-01 \
  --end-date 2024-12-31 \
  --interval 1d \
  --initial-capital 1000000
```

## 主なオプション

- `--symbol`: 単一銘柄シンボル（例: `AAPL`）
- `--watchlist-id`: ウォッチリストID（`--user-id`必須）
- `--user-id`: ウォッチリスト取得用ユーザーID
- `--start-date`, `--end-date`: 検証期間（`YYYY-MM-DD`）
- `--interval`: データ間隔（`1d`, `1wk`, `1mo`）
- `--initial-capital`: 初期資金
- `--fee-rate`: 手数料率（例: `0.001` = `0.1%`）
- `--short-window`, `--long-window`: SMA期間
- `--max-per`: PER上限フィルター
- `--fetch-financial-history`: 財務履歴も取得
- `--trade-csv`: 取引履歴CSVの保存先（既定: `trade_history.csv`）
- `--save-chart`: 売買ポイントと資産推移チャートを保存
- `--chart-file`: チャート画像ファイル名（既定: `result_chart.png`）
- `--show-chart`: チャートを画面表示
- `--base-url`: APIベースURL（既定: `http://localhost:8000`）
- `--timeout`: APIタイムアウト秒
- `--max-retries`: API再試行回数

## 出力

- コンソール: 最終資産額、リターン率、勝率、最大ドローダウン等
- CSV: 取引履歴（`date`, `side`, `price`, `shares`, `pnl` など）
- 画像（任意）: 売買ポイント付き価格チャートと資産推移
