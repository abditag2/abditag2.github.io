"""Paper or live trading loop. One step per completed hour. Examples:
  python scripts/run.py --mode paper --strategy p1 --universe research22 --run-id p1_paper
  python scripts/run.py --mode live  --strategy p1_longflat --universe evm_arbitrum --run-id p1_live --dry-run
Set --once to run a single step (for cron / systemd timers)."""
import argparse, time, json, datetime as dt, traceback
from common import *

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["paper", "live"], required=True); ap.add_argument("--strategy", default="p1"); ap.add_argument("--universe", default="research22")
ap.add_argument("--run-id", required=True); ap.add_argument("--cash", type=float, default=10_000); ap.add_argument("--once", action="store_true")
ap.add_argument("--dry-run", action="store_true", help="live: quote, check and sign nothing; report what would be sent"); ap.add_argument("--chain", default="arbitrum")
ap.add_argument("--ledger", default=None)
a = ap.parse_args()
cfg = config.strategy_config(a.strategy); symbols = config.universe(a.universe)
store = BarStore(state_dir() / "bars.db"); feed = CoinbaseFeed(); ledger = Ledger(state_dir() / (a.ledger or f"{a.mode}.db"))
if a.mode == "paper":
    ex = PaperExecutor(cash=a.cash, can_short=True)
    row = ledger.con.execute("SELECT value FROM kv WHERE run_id=? AND key='paper_balances'", (a.run_id,)).fetchone() if ledger.con.execute("SELECT name FROM sqlite_master WHERE name='kv'").fetchone() else None
    if row: ex.restore(json.loads(row[0])); print("resumed paper balances")
    cash_yield = cfg.get("cash_yield", 0.0)
else:
    from trader.execution.sushi import SushiExecutor
    chain = config.chain_config(a.chain); tokens = {s: chain["tokens"][s] for s in symbols if s in chain["tokens"]}
    missing = [s for s in symbols if s not in tokens]
    if missing: print("WARNING: no on-chain token for", missing, "-> skipped"); symbols = [s for s in symbols if s in tokens]
    ex = SushiExecutor(chain, tokens, dry_run=a.dry_run); cash_yield = 0.0
    if not a.dry_run:
        ex.verify_tokens(); print(f"wallet {ex.address}: native {ex.native_balance():.4f}, balances {ex.balances()}")
if not ledger.con.execute("SELECT 1 FROM runs WHERE run_id=?", (a.run_id,)).fetchone():
    ledger.new_run(a.run_id, a.mode + ("-dry" if a.dry_run else ""), a.strategy, cfg, symbols)
eng = Engine(PortfolioStrategy(cfg), ex, ledger, a.run_id, symbols, cash_yield=cash_yield); eng.load_state()
print(f"{a.mode} run {a.run_id}: {len(symbols)} symbols, strategy {a.strategy}, resumed {len(eng.state.lots)} lots")

def one_step():
    try:
        r = eng.live_step(store, feed)
        if r: print(f"[{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}] equity {r[0]:.2f}, orders {[(o.symbol, o.side, round(o.notional, 2), o.book) for o in r[1]]}")
    except Exception as e:
        ledger.event(a.run_id, int(time.time()), "error", f"{type(e).__name__}: {e}"); traceback.print_exc()

one_step()
while not a.once:
    from trader.engine import next_hour_boundary
    nxt = next_hour_boundary(); time.sleep(max(1, (nxt - dt.datetime.now(dt.timezone.utc)).total_seconds())); one_step()
