"""Replay a strategy over history through the paper executor. Example:
python scripts/backtest.py --strategy p1 --universe research22 --start 2022-01-01 --end 2026-09-19 --run-id p1_2022_2026"""
import argparse, json
from common import *

ap = argparse.ArgumentParser()
ap.add_argument("--strategy", default="p1"); ap.add_argument("--universe", default="research22"); ap.add_argument("--symbols", default=None)
ap.add_argument("--start", required=True); ap.add_argument("--end", required=True); ap.add_argument("--run-id", default=None)
ap.add_argument("--cash", type=float, default=100_000); ap.add_argument("--fee", type=float, default=0.0005); ap.add_argument("--slippage", type=float, default=0.00025)
ap.add_argument("--no-short", action="store_true", help="executor cannot short (spot venue): base is long/flat, overlay long-only")
ap.add_argument("--cash-yield", type=float, default=None); ap.add_argument("--ledger", default="backtests.db")
a = ap.parse_args()
cfg = config.strategy_config(a.strategy); symbols = a.symbols.split(",") if a.symbols else config.universe(a.universe)
cash_yield = a.cash_yield if a.cash_yield is not None else cfg.get("cash_yield", 0.0)
run_id = a.run_id or f"{a.strategy}_{a.universe}_{a.start}_{a.end}" + ("_noshort" if a.no_short else "")
store = BarStore(state_dir() / "bars.db"); ledger = Ledger(state_dir() / a.ledger)
ledger.con.execute("DELETE FROM equity WHERE run_id=?", (run_id,)); ledger.con.execute("DELETE FROM fills WHERE run_id=?", (run_id,))
ledger.con.execute("DELETE FROM lots WHERE run_id=?", (run_id,)); ledger.con.execute("DELETE FROM base WHERE run_id=?", (run_id,)); ledger.commit()
ledger.new_run(run_id, "backtest", a.strategy, {**cfg, "fee": a.fee, "slippage": a.slippage, "cash_yield": cash_yield, "no_short": a.no_short}, symbols)
ex = PaperExecutor(cash=a.cash, fee_rate=a.fee, slippage=a.slippage, can_short=not a.no_short)
eng = Engine(load_strategy(cfg), ex, ledger, run_id, symbols, cash_yield=cash_yield)
eq = eng.backtest(store, a.start, a.end)
m = metrics.summarize(eq["equity"], ledger.lots(run_id), eq["exposure"])
print(f"run {run_id}:"); print_metrics(m)
