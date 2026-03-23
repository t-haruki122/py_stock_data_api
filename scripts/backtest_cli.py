"""py_stock_data_api を使ったバックテストCLI。

例:
python scripts/backtest_cli.py --symbol AAPL --start-date 2023-01-01 --end-date 2024-12-31
python scripts/backtest_cli.py --user-id 1 --watchlist-id 2 --start-date 2023-01-01 --end-date 2024-12-31 --save-chart
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests


@dataclasses.dataclass
class BacktestMetrics:
    symbol: str
    initial_capital: float
    final_asset: float
    return_pct: float
    total_trades: int
    win_rate: float
    max_drawdown: float


@dataclasses.dataclass
class BacktestResult:
    symbol: str
    equity_curve: pd.DataFrame
    trades: list[dict[str, Any]]
    metrics: BacktestMetrics


class APIClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        retry_wait: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_wait = retry_wait
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            if cancel_check is not None and cancel_check():
                raise RuntimeError("Cancelled")
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=self.timeout,
                )

                if response.status_code == 404:
                    raise RuntimeError(f"404 Not Found: {url}")
                if response.status_code >= 400:
                    raise RuntimeError(
                        f"HTTP {response.status_code}: {url} - {response.text[:200]}"
                    )

                return response.json()
            except (requests.Timeout, requests.ConnectionError, RuntimeError) as exc:
                last_error = exc
                if str(exc) == "Cancelled":
                    raise
                if attempt >= self.max_retries:
                    break
                sleep_sec = self.retry_wait * attempt
                # Sleep in short chunks so cancellation can interrupt retry waits.
                waited = 0.0
                while waited < sleep_sec:
                    if cancel_check is not None and cancel_check():
                        raise RuntimeError("Cancelled")
                    chunk = min(0.1, sleep_sec - waited)
                    time.sleep(chunk)
                    waited += chunk

        raise RuntimeError(f"API request failed after retries: {url} ({last_error})")

    def get_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/stock/{symbol}/history",
            params={
                "start_date": start_date,
                "end_date": end_date,
                "interval": interval,
            },
            cancel_check=cancel_check,
        )

    def get_financials(
        self,
        symbol: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return self._request("GET", f"/stock/{symbol}/financials", cancel_check=cancel_check)

    def get_financial_history(
        self,
        symbol: str,
        limit: int = 6,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/stock/{symbol}/financials/history",
            params={"limit": limit},
            cancel_check=cancel_check,
        )

    def get_watchlist_symbols(
        self,
        user_id: int,
        watchlist_id: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> list[str]:
        payload = self._request("GET", f"/user/{user_id}/lists/{watchlist_id}", cancel_check=cancel_check)
        items = payload.get("items", [])
        symbols = [str(item.get("symbol", "")).upper() for item in items if item.get("symbol")]
        return sorted(set(symbols))


class Strategy:
    name = "base"

    def prepare(self, price_df: pd.DataFrame, context: dict[str, Any]) -> pd.DataFrame:
        raise NotImplementedError


class SmaCrossPerStrategy(Strategy):
    name = "sma_cross_per"

    def __init__(self, short_window: int, long_window: int, max_per: float | None = None) -> None:
        if short_window <= 0 or long_window <= 0:
            raise ValueError("Window must be positive")
        if short_window >= long_window:
            raise ValueError("short_window must be smaller than long_window")
        self.short_window = short_window
        self.long_window = long_window
        self.max_per = max_per

    def prepare(self, price_df: pd.DataFrame, context: dict[str, Any]) -> pd.DataFrame:
        df = price_df.copy()
        df["sma_short"] = df["close"].rolling(self.short_window).mean()
        df["sma_long"] = df["close"].rolling(self.long_window).mean()
        df["signal"] = 0

        prev_short = df["sma_short"].shift(1)
        prev_long = df["sma_long"].shift(1)

        buy_cross = (df["sma_short"] > df["sma_long"]) & (prev_short <= prev_long)
        sell_cross = (df["sma_short"] < df["sma_long"]) & (prev_short >= prev_long)

        if self.max_per is not None:
            per_value = context.get("pe_ratio")
            per_ok = per_value is not None and per_value <= self.max_per
            if not per_ok:
                buy_cross = pd.Series([False] * len(df), index=df.index)

        df.loc[buy_cross, "signal"] = 1
        df.loc[sell_cross, "signal"] = -1
        return df


class Backtester:
    def __init__(
        self,
        strategy: Strategy,
        initial_capital: float,
        fee_rate: float = 0.0,
    ) -> None:
        self.strategy = strategy
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate

    def run(
        self,
        symbol: str,
        price_df: pd.DataFrame,
        context: dict[str, Any] | None = None,
        progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    ) -> BacktestResult:
        if context is None:
            context = {}

        if price_df.empty:
            raise ValueError(f"No price data for {symbol}")

        df = self.strategy.prepare(price_df, context)

        cash = float(self.initial_capital)
        shares = 0
        position_cost = 0.0

        trades: list[dict[str, Any]] = []
        equity_rows: list[dict[str, Any]] = []
        total_rows = len(df)
        progress_step = max(1, total_rows // 100)

        for idx, row in enumerate(df.itertuples(index=False), start=1):
            date = row.date
            price = float(row.close)
            signal = int(row.signal)
            trade_side: str | None = None

            if signal == 1 and shares == 0 and price > 0:
                max_shares = int(cash // (price * (1 + self.fee_rate)))
                if max_shares > 0:
                    gross = max_shares * price
                    fee = gross * self.fee_rate
                    cash -= gross + fee
                    shares = max_shares
                    position_cost = gross + fee
                    trades.append(
                        {
                            "symbol": symbol,
                            "date": date,
                            "side": "BUY",
                            "price": round(price, 4),
                            "shares": shares,
                            "fee": round(fee, 4),
                            "pnl": None,
                            "cash_after": round(cash, 4),
                        }
                    )
                    trade_side = "BUY"

            elif signal == -1 and shares > 0:
                gross = shares * price
                fee = gross * self.fee_rate
                proceeds = gross - fee
                trade_pnl = proceeds - position_cost
                cash += proceeds
                trades.append(
                    {
                        "symbol": symbol,
                        "date": date,
                        "side": "SELL",
                        "price": round(price, 4),
                        "shares": shares,
                        "fee": round(fee, 4),
                        "pnl": round(trade_pnl, 4),
                        "cash_after": round(cash, 4),
                    }
                )
                shares = 0
                position_cost = 0.0
                trade_side = "SELL"

            holding_value = shares * price
            equity = cash + holding_value
            equity_rows.append(
                {
                    "symbol": symbol,
                    "date": date,
                    "close": price,
                    "shares": shares,
                    "cash": cash,
                    "holding_value": holding_value,
                    "equity": equity,
                    "signal": signal,
                }
            )

            if progress_callback is not None:
                should_emit = (
                    idx == 1
                    or idx == total_rows
                    or idx % progress_step == 0
                    or trade_side is not None
                )
                if should_emit:
                    progress_callback(
                        idx,
                        total_rows,
                        {
                            "symbol": symbol,
                            "date": date,
                            "signal": signal,
                            "trade_side": trade_side,
                            "cash": cash,
                            "equity": equity,
                            "price": price,
                        },
                    )

        equity_df = pd.DataFrame(equity_rows)
        metrics = self._calculate_metrics(symbol, equity_df, trades)

        return BacktestResult(
            symbol=symbol,
            equity_curve=equity_df,
            trades=trades,
            metrics=metrics,
        )

    def _calculate_metrics(
        self,
        symbol: str,
        equity_df: pd.DataFrame,
        trades: list[dict[str, Any]],
    ) -> BacktestMetrics:
        final_asset = float(equity_df["equity"].iloc[-1])
        ret = ((final_asset - self.initial_capital) / self.initial_capital) * 100

        sell_trades = [t for t in trades if t["side"] == "SELL" and t["pnl"] is not None]
        total_trades = len(sell_trades)
        winning = [t for t in sell_trades if float(t["pnl"]) > 0]
        win_rate = (len(winning) / total_trades * 100) if total_trades > 0 else 0.0

        running_max = equity_df["equity"].cummax()
        drawdown = (equity_df["equity"] - running_max) / running_max
        max_drawdown = abs(float(drawdown.min())) * 100 if not drawdown.empty else 0.0

        return BacktestMetrics(
            symbol=symbol,
            initial_capital=self.initial_capital,
            final_asset=final_asset,
            return_pct=ret,
            total_trades=total_trades,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="py_stock_data_api バックテストCLI")

    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--symbol", type=str, help="単一銘柄シンボル (例: AAPL)")
    target_group.add_argument("--watchlist-id", type=int, help="ウォッチリストID")

    parser.add_argument("--user-id", type=int, help="ウォッチリスト取得用のユーザーID")

    parser.add_argument("--start-date", required=True, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="終了日 YYYY-MM-DD")
    parser.add_argument("--interval", default="1d", choices=["1d", "1wk", "1mo"], help="データ間隔")

    parser.add_argument("--initial-capital", type=float, default=1_000_000.0, help="初期資金")
    parser.add_argument("--fee-rate", type=float, default=0.0, help="手数料率（0.001 = 0.1%%）")

    parser.add_argument("--short-window", type=int, default=20, help="短期SMA期間")
    parser.add_argument("--long-window", type=int, default=60, help="長期SMA期間")
    parser.add_argument("--max-per", type=float, default=None, help="PER上限フィルター")

    parser.add_argument("--fetch-financial-history", action="store_true", help="財務履歴を取得して表示")

    parser.add_argument("--base-url", default="http://localhost:8000", help="APIベースURL")
    parser.add_argument("--timeout", type=float, default=10.0, help="APIタイムアウト秒")
    parser.add_argument("--max-retries", type=int, default=3, help="API再試行回数")

    parser.add_argument("--trade-csv", default="trade_history.csv", help="取引履歴CSV出力先")
    parser.add_argument("--save-chart", action="store_true", help="チャート画像を保存")
    parser.add_argument("--chart-file", default="result_chart.png", help="単一銘柄のチャート出力先")
    parser.add_argument("--show-chart", action="store_true", help="チャートを画面表示")

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    try:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        end = datetime.strptime(args.end_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("start-date/end-date は YYYY-MM-DD 形式で指定してください") from exc

    if start > end:
        raise ValueError("start-date は end-date 以前にしてください")

    if args.watchlist_id is not None and args.user_id is None:
        raise ValueError("watchlist-id 指定時は user-id が必要です")

    if args.initial_capital <= 0:
        raise ValueError("initial-capital は正の値を指定してください")

    if args.fee_rate < 0:
        raise ValueError("fee-rate は 0 以上を指定してください")


def history_to_df(payload: dict[str, Any]) -> pd.DataFrame:
    rows = payload.get("history", [])
    if not rows:
        return pd.DataFrame(columns=["date", "close"])

    df = pd.DataFrame(rows)
    if "date" not in df.columns or "close" not in df.columns:
        raise ValueError("history response format is invalid")

    df = df[["date", "open", "high", "low", "close", "volume"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def print_metrics(metrics: BacktestMetrics) -> None:
    print("=" * 70)
    print(f"Symbol          : {metrics.symbol}")
    print(f"Initial Capital : {metrics.initial_capital:,.2f}")
    print(f"Final Asset     : {metrics.final_asset:,.2f}")
    print(f"Return          : {metrics.return_pct:.2f}%")
    print(f"Total Trades    : {metrics.total_trades}")
    print(f"Win Rate        : {metrics.win_rate:.2f}%")
    print(f"Max Drawdown    : {metrics.max_drawdown:.2f}%")


def save_trades_csv(trades: list[dict[str, Any]], output_file: str) -> None:
    fields = ["symbol", "date", "side", "price", "shares", "fee", "pnl", "cash_after"]
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for trade in trades:
            writer.writerow(trade)

    print(f"Trade history saved: {out_path}")


def plot_result(
    result: BacktestResult,
    output_file: str,
    show_chart: bool,
) -> None:
    import matplotlib.pyplot as plt

    fig = create_result_figure(result)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Chart saved: {out_path}")

    if show_chart:
        plt.show()
    else:
        plt.close(fig)


def create_result_figure(result: BacktestResult):
    import matplotlib.pyplot as plt

    eq = result.equity_curve.copy()
    eq["date"] = pd.to_datetime(eq["date"])

    buy_points = eq[eq["signal"] == 1]
    sell_points = eq[eq["signal"] == -1]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    ax1.plot(eq["date"], eq["close"], label="Close", color="steelblue", linewidth=1.2)
    ax1.scatter(buy_points["date"], buy_points["close"], marker="^", color="green", label="Buy", s=50)
    ax1.scatter(sell_points["date"], sell_points["close"], marker="v", color="red", label="Sell", s=50)
    ax1.set_title(f"{result.symbol} Price + Signals")
    ax1.set_ylabel("Price")
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.plot(eq["date"], eq["equity"], label="Equity", color="darkorange", linewidth=1.2)
    ax2.set_title("Equity Curve")
    ax2.set_ylabel("Asset")
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    return fig


def run_single_symbol(
    client: APIClient,
    symbol: str,
    args: argparse.Namespace,
    initial_capital: float,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[float, str], None] | None = None,
) -> BacktestResult:
    cancel_check = cancel_event.is_set if cancel_event is not None else None

    def emit_progress(progress: float, message: str) -> None:
        if progress_callback is not None:
            progress_callback(progress, message)

    emit_progress(5.0, f"{symbol}: price data fetching")
    history_payload = client.get_history(
        symbol,
        args.start_date,
        args.end_date,
        args.interval,
        cancel_check=cancel_check,
    )
    history_df = history_to_df(history_payload)
    emit_progress(20.0, f"{symbol}: price data ready ({len(history_df)} rows)")

    context: dict[str, Any] = {}
    if args.max_per is not None:
        emit_progress(25.0, f"{symbol}: financials fetching")
        financials = client.get_financials(symbol, cancel_check=cancel_check)
        context["pe_ratio"] = financials.get("pe_ratio")
        emit_progress(30.0, f"{symbol}: financials ready")
    else:
        emit_progress(30.0, f"{symbol}: preparing strategy")

    if args.fetch_financial_history:
        fin_hist = client.get_financial_history(symbol, limit=6, cancel_check=cancel_check)
        print(f"Financial history fetched for {symbol}: {len(fin_hist.get('history', []))} rows")

    strategy = SmaCrossPerStrategy(
        short_window=args.short_window,
        long_window=args.long_window,
        max_per=args.max_per,
    )
    backtester = Backtester(strategy=strategy, initial_capital=initial_capital, fee_rate=args.fee_rate)

    def on_backtest_progress(done: int, total: int, state: dict[str, Any]) -> None:
        ratio = (done / total) if total > 0 else 1.0
        overall = 30.0 + ratio * 65.0
        message = f"{symbol}: {state['date']} processed ({done}/{total})"
        if state.get("trade_side") is not None:
            message += (
                f" | {state['trade_side']} @ {state['price']:.2f}"
                f" | cash {state['cash']:.2f}"
            )
        emit_progress(overall, message)

    result = backtester.run(
        symbol=symbol,
        price_df=history_df,
        context=context,
        progress_callback=on_backtest_progress,
    )
    emit_progress(100.0, f"{symbol}: backtest completed")
    return result


def resolve_symbols(client: APIClient, args: argparse.Namespace) -> list[str]:
    if args.symbol:
        return [args.symbol.upper()]

    symbols = client.get_watchlist_symbols(args.user_id, args.watchlist_id)
    if not symbols:
        raise ValueError("ウォッチリストに銘柄が存在しません")
    return symbols


def main() -> int:
    args = parse_args()

    try:
        validate_args(args)
    except ValueError as exc:
        print(f"Argument error: {exc}", file=sys.stderr)
        return 1

    client = APIClient(
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_wait=1.0,
    )

    try:
        symbols = resolve_symbols(client, args)
    except Exception as exc:
        print(f"Failed to resolve symbols: {exc}", file=sys.stderr)
        return 1

    capital_per_symbol = args.initial_capital / len(symbols)

    all_results: list[BacktestResult] = []
    all_trades: list[dict[str, Any]] = []

    for symbol in symbols:
        try:
            result = run_single_symbol(client, symbol, args, initial_capital=capital_per_symbol)
            all_results.append(result)
            all_trades.extend(result.trades)
            print_metrics(result.metrics)
        except Exception as exc:
            print(f"Backtest failed for {symbol}: {exc}", file=sys.stderr)

    if not all_results:
        print("No successful backtest results.", file=sys.stderr)
        return 1

    total_initial = sum(res.metrics.initial_capital for res in all_results)
    total_final = sum(res.metrics.final_asset for res in all_results)
    total_return = ((total_final - total_initial) / total_initial) * 100

    print("=" * 70)
    print("Portfolio Summary")
    print(f"Symbols         : {', '.join([r.symbol for r in all_results])}")
    print(f"Initial Capital : {total_initial:,.2f}")
    print(f"Final Asset     : {total_final:,.2f}")
    print(f"Return          : {total_return:.2f}%")

    save_trades_csv(all_trades, args.trade_csv)

    if args.save_chart:
        if len(all_results) == 1:
            plot_result(all_results[0], args.chart_file, args.show_chart)
        else:
            for res in all_results:
                symbol_chart = str(Path(args.chart_file).with_name(f"{res.symbol}_{Path(args.chart_file).name}"))
                plot_result(res, symbol_chart, show_chart=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
