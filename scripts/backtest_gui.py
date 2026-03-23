"""Desktop GUI for scripts/backtest_cli.py.

Run:
    python scripts/backtest_gui.py
"""

from __future__ import annotations

import threading
import tkinter as tk
from argparse import Namespace
from datetime import datetime
from pathlib import Path
import sys
from tkinter import filedialog, messagebox, ttk
from typing import Any

import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Allow running as: python scripts/backtest_gui.py
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.backtest_cli import APIClient, create_result_figure, run_single_symbol


class BacktestGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Backtest GUI")
        self.root.geometry("1180x780")

        self.worker: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.result = None
        self.trades: list[dict] = []
        self.chart_canvas: FigureCanvasTkAgg | None = None
        self.trade_table: ttk.Treeview | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"))

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(outer, text="Parameters", padding=10)
        form.pack(fill=tk.X)

        self.symbol_var = tk.StringVar(value="AAPL")
        self.start_var = tk.StringVar(value="2023-01-01")
        self.end_var = tk.StringVar(value="2024-12-31")
        self.interval_var = tk.StringVar(value="1d")
        self.capital_var = tk.StringVar(value="1000000")
        self.fee_var = tk.StringVar(value="0.0")
        self.short_var = tk.StringVar(value="20")
        self.long_var = tk.StringVar(value="60")
        self.max_per_var = tk.StringVar(value="")
        self.base_url_var = tk.StringVar(value="http://localhost:8000")
        self.timeout_var = tk.StringVar(value="10")
        self.retries_var = tk.StringVar(value="3")

        row1 = ttk.Frame(form)
        row1.pack(fill=tk.X, pady=2)
        row2 = ttk.Frame(form)
        row2.pack(fill=tk.X, pady=2)
        row3 = ttk.Frame(form)
        row3.pack(fill=tk.X, pady=2)

        self._labeled_entry(row1, "Symbol", self.symbol_var, width=12)
        self._labeled_entry(row1, "Start", self.start_var, width=12)
        self._labeled_entry(row1, "End", self.end_var, width=12)
        self._labeled_combo(row1, "Interval", self.interval_var, ["1d", "1wk", "1mo"], width=8)

        self._labeled_entry(row2, "Initial Capital", self.capital_var, width=14)
        self._labeled_entry(row2, "Fee Rate", self.fee_var, width=10)
        self._labeled_entry(row2, "SMA Short", self.short_var, width=8)
        self._labeled_entry(row2, "SMA Long", self.long_var, width=8)
        self._labeled_entry(row2, "Max PER", self.max_per_var, width=10)

        self._labeled_entry(row3, "Base URL", self.base_url_var, width=28)
        self._labeled_entry(row3, "Timeout", self.timeout_var, width=8)
        self._labeled_entry(row3, "Retries", self.retries_var, width=8)

        action_row = ttk.Frame(outer)
        action_row.pack(fill=tk.X, pady=(10, 6))

        self.run_button = ttk.Button(action_row, text="Run Backtest", command=self.on_run)
        self.run_button.pack(side=tk.LEFT)

        self.cancel_button = ttk.Button(action_row, text="Cancel", command=self.on_cancel, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=(8, 0))

        self.save_csv_button = ttk.Button(action_row, text="Save Trades CSV", command=self.save_trades_csv, state=tk.DISABLED)
        self.save_csv_button.pack(side=tk.LEFT, padx=(16, 0))

        self.save_png_button = ttk.Button(action_row, text="Save Chart PNG", command=self.save_chart_png, state=tk.DISABLED)
        self.save_png_button.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(action_row, textvariable=self.status_var).pack(side=tk.RIGHT)

        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X)

        body = ttk.Panedwindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        left = ttk.Frame(body, padding=6)
        right = ttk.Frame(body, padding=6)
        body.add(left, weight=1)
        body.add(right, weight=3)

        ttk.Label(left, text="Metrics", style="Header.TLabel").pack(anchor=tk.W)
        self.metrics_text = tk.Text(left, width=38, height=12, state=tk.DISABLED)
        self.metrics_text.pack(fill=tk.BOTH, expand=False, pady=(6, 12))

        ttk.Label(left, text="Run Log", style="Header.TLabel").pack(anchor=tk.W)
        self.log_text = tk.Text(left, width=38, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=False, pady=(6, 10))

        ttk.Label(left, text="Trade Details", style="Header.TLabel").pack(anchor=tk.W)
        table_wrap = ttk.Frame(left)
        table_wrap.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        columns = (
            "date",
            "side",
            "price",
            "shares",
            "fee",
            "pnl",
            "cash_after",
            "equity_after",
        )
        self.trade_table = ttk.Treeview(
            table_wrap,
            columns=columns,
            show="headings",
            height=12,
        )

        headings = {
            "date": "Date",
            "side": "Side",
            "price": "Price",
            "shares": "Shares",
            "fee": "Fee",
            "pnl": "PnL",
            "cash_after": "Cash After",
            "equity_after": "Asset After",
        }
        widths = {
            "date": 95,
            "side": 52,
            "price": 70,
            "shares": 70,
            "fee": 70,
            "pnl": 82,
            "cash_after": 108,
            "equity_after": 108,
        }
        for col in columns:
            self.trade_table.heading(col, text=headings[col])
            anchor = tk.E if col not in {"date", "side"} else tk.W
            self.trade_table.column(col, width=widths[col], anchor=anchor, stretch=False)

        ybar = ttk.Scrollbar(table_wrap, orient=tk.VERTICAL, command=self.trade_table.yview)
        xbar = ttk.Scrollbar(table_wrap, orient=tk.HORIZONTAL, command=self.trade_table.xview)
        self.trade_table.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        self.trade_table.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table_wrap.rowconfigure(0, weight=1)
        table_wrap.columnconfigure(0, weight=1)

        ttk.Label(right, text="Chart", style="Header.TLabel").pack(anchor=tk.W)
        self.chart_frame = ttk.Frame(right)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

    def _labeled_entry(self, parent: ttk.Frame, label: str, var: tk.StringVar, width: int = 12) -> None:
        cell = ttk.Frame(parent)
        cell.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(cell, text=label).pack(anchor=tk.W)
        ttk.Entry(cell, textvariable=var, width=width).pack(anchor=tk.W)

    def _labeled_combo(
        self,
        parent: ttk.Frame,
        label: str,
        var: tk.StringVar,
        values: list[str],
        width: int = 10,
    ) -> None:
        cell = ttk.Frame(parent)
        cell.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(cell, text=label).pack(anchor=tk.W)
        ttk.Combobox(cell, textvariable=var, values=values, width=width, state="readonly").pack(anchor=tk.W)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_metrics(self, text: str) -> None:
        self.metrics_text.configure(state=tk.NORMAL)
        self.metrics_text.delete("1.0", tk.END)
        self.metrics_text.insert("1.0", text)
        self.metrics_text.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self.run_button.configure(state=tk.DISABLED)
            self.cancel_button.configure(state=tk.NORMAL)
            self.save_csv_button.configure(state=tk.DISABLED)
            self.save_png_button.configure(state=tk.DISABLED)
            self.progress.configure(value=0)
        else:
            self.run_button.configure(state=tk.NORMAL)
            self.cancel_button.configure(state=tk.DISABLED)
            can_save = self.result is not None
            self.save_csv_button.configure(state=tk.NORMAL if can_save else tk.DISABLED)
            self.save_png_button.configure(state=tk.NORMAL if can_save else tk.DISABLED)
            if self.result is None:
                self.progress.configure(value=0)

    def _clear_trade_table(self) -> None:
        if self.trade_table is None:
            return
        for row_id in self.trade_table.get_children():
            self.trade_table.delete(row_id)

    def _populate_trade_table(self, result: Any) -> None:
        self._clear_trade_table()
        if self.trade_table is None:
            return

        if result is None or not result.trades:
            return

        equity_map: dict[str, float] = {}
        if result.equity_curve is not None and not result.equity_curve.empty:
            grouped = result.equity_curve.groupby("date", sort=False).tail(1)
            for row in grouped.itertuples(index=False):
                equity_map[str(row.date)] = float(row.equity)

        for trade in result.trades:
            trade_date = str(trade.get("date", ""))
            price = trade.get("price")
            shares = trade.get("shares")
            fee = trade.get("fee")
            pnl = trade.get("pnl")
            cash_after = trade.get("cash_after")
            equity_after = equity_map.get(trade_date)

            self.trade_table.insert(
                "",
                tk.END,
                values=(
                    trade_date,
                    trade.get("side", ""),
                    "" if price is None else f"{float(price):,.2f}",
                    "" if shares is None else f"{int(shares):,}",
                    "" if fee is None else f"{float(fee):,.2f}",
                    "" if pnl is None else f"{float(pnl):,.2f}",
                    "" if cash_after is None else f"{float(cash_after):,.2f}",
                    "" if equity_after is None else f"{float(equity_after):,.2f}",
                ),
            )

    def _report_progress(self, progress: float, message: str) -> None:
        bounded = max(0.0, min(100.0, float(progress)))
        self.progress.configure(value=bounded)
        self.status_var.set(f"Running... {bounded:.1f}%")
        self._append_log(message)

    def _validate_inputs(self) -> tuple[Namespace, APIClient]:
        symbol = self.symbol_var.get().strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")

        start = self.start_var.get().strip()
        end = self.end_var.get().strip()
        datetime.strptime(start, "%Y-%m-%d")
        datetime.strptime(end, "%Y-%m-%d")
        if start > end:
            raise ValueError("Start date must be <= End date")

        initial_capital = float(self.capital_var.get().strip())
        if initial_capital <= 0:
            raise ValueError("Initial capital must be positive")

        fee_rate = float(self.fee_var.get().strip())
        if fee_rate < 0:
            raise ValueError("Fee rate must be >= 0")

        short_window = int(self.short_var.get().strip())
        long_window = int(self.long_var.get().strip())
        if short_window >= long_window:
            raise ValueError("SMA short must be < SMA long")

        max_per_raw = self.max_per_var.get().strip()
        max_per = float(max_per_raw) if max_per_raw else None

        args = Namespace(
            symbol=symbol,
            start_date=start,
            end_date=end,
            interval=self.interval_var.get().strip(),
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            short_window=short_window,
            long_window=long_window,
            max_per=max_per,
            fetch_financial_history=False,
        )

        client = APIClient(
            base_url=self.base_url_var.get().strip(),
            timeout=float(self.timeout_var.get().strip()),
            max_retries=int(self.retries_var.get().strip()),
            retry_wait=1.0,
        )
        return args, client

    def on_run(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        try:
            args, client = self._validate_inputs()
        except Exception as exc:
            messagebox.showerror("Invalid Input", str(exc))
            return

        self.result = None
        self.trades = []
        self.cancel_event.clear()
        self._set_metrics("")
        self._clear_trade_table()
        self.status_var.set("Running...")
        self._append_log("Backtest started")
        self._set_busy(True)

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(client, args),
            daemon=True,
        )
        self.worker.start()

    def on_cancel(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Cancelling...")
        self._append_log("Cancellation requested")

    def _run_worker(self, client: APIClient, args: Namespace) -> None:
        def progress_from_worker(progress: float, message: str) -> None:
            self.root.after(0, self._report_progress, progress, message)

        try:
            result = run_single_symbol(
                client=client,
                symbol=args.symbol,
                args=args,
                initial_capital=args.initial_capital,
                cancel_event=self.cancel_event,
                progress_callback=progress_from_worker,
            )
            if self.cancel_event.is_set():
                self.root.after(0, self._on_cancelled)
                return
            self.root.after(0, self._on_success, result)
        except Exception as exc:
            if str(exc) == "Cancelled":
                self.root.after(0, self._on_cancelled)
            else:
                self.root.after(0, self._on_error, str(exc))

    def _on_success(self, result) -> None:
        self.result = result
        self.trades = list(result.trades)

        m = result.metrics
        metrics_text = (
            f"Symbol: {m.symbol}\n"
            f"Initial Capital: {m.initial_capital:,.2f}\n"
            f"Final Asset: {m.final_asset:,.2f}\n"
            f"Return: {m.return_pct:.2f}%\n"
            f"Total Trades: {m.total_trades}\n"
            f"Win Rate: {m.win_rate:.2f}%\n"
            f"Max Drawdown: {m.max_drawdown:.2f}%"
        )
        self._set_metrics(metrics_text)
        self._populate_trade_table(result)
        self._render_chart(result)

        self.progress.configure(value=100)
        self.status_var.set("Completed 100.0%")
        self._append_log("Backtest completed")
        self._set_busy(False)

    def _on_cancelled(self) -> None:
        self.status_var.set("Cancelled")
        self._append_log("Backtest cancelled")
        self.result = None
        self._set_busy(False)

    def _on_error(self, message: str) -> None:
        self.status_var.set("Failed")
        self._append_log(f"Error: {message}")
        messagebox.showerror("Backtest Error", message)
        self.result = None
        self._set_busy(False)

    def _render_chart(self, result) -> None:
        figure = create_result_figure(result)

        if self.chart_canvas is not None:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None

        canvas = FigureCanvasTkAgg(figure, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.chart_canvas = canvas

    def save_trades_csv(self) -> None:
        if not self.trades:
            messagebox.showinfo("No Trades", "No trade rows to save")
            return

        path = filedialog.asksaveasfilename(
            title="Save Trade CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="trade_history.csv",
        )
        if not path:
            return

        pd.DataFrame(self.trades).to_csv(path, index=False)
        self._append_log(f"Saved trades CSV: {Path(path)}")

    def save_chart_png(self) -> None:
        if self.result is None:
            messagebox.showinfo("No Chart", "Run a backtest first")
            return

        path = filedialog.asksaveasfilename(
            title="Save Chart PNG",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=f"{self.result.symbol}_result_chart.png",
        )
        if not path:
            return

        figure = create_result_figure(self.result)
        figure.savefig(path, dpi=150)
        self._append_log(f"Saved chart PNG: {Path(path)}")


def main() -> int:
    root = tk.Tk()
    BacktestGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
