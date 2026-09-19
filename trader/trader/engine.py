"""The engine runs one strategy against one executor. Backtest = replay history hour by hour through the paper executor;
paper/live = one step per completed hour with fresh candles. Same decide -> net -> execute -> book -> mark path everywhere."""
import time, datetime as dt, json
import numpy as np, pandas as pd
from . import signals as S
from .strategies.base import Strategy, State, Lot, Order, Context
from .execution.base import ExecutionError
from . import risk

class Engine:
    def __init__(self, strategy: Strategy, executor, ledger, run_id, symbols, cash_yield=0.0, log=print):
        self.strategy, self.ex, self.ledger, self.run_id, self.symbols = strategy, executor, ledger, run_id, list(symbols)
        self.cash_yield = cash_yield; self.log = log; self.state = State(); self.halted = None

    # ---- state ----
    def load_state(self):
        lots, base = self.ledger.state(self.run_id)
        self.state = State(lots={r.symbol: Lot(r.symbol, int(r.side), float(r.qty), int(r.entry_ts), float(r.entry_price), float(r.notional)) for r in lots.itertuples()},
                           base_qty={r.symbol: float(r.qty) for r in base.itertuples()})
        return self.state

    def equity(self, prices):
        prices = {s: p for s, p in prices.items() if p == p}      # drop symbols without a price (not yet listed)
        bal = self.ex.balances(); cash = bal.get(self.ex.quote, 0.0)
        value = sum(bal.get(s, 0.0) * prices.get(s, 0.0) for s in self.symbols)
        exposure = sum(abs(bal.get(s, 0.0) * prices.get(s, 0.0)) for s in self.symbols)
        return cash + value, cash, exposure

    # ---- one step ----
    def step(self, t, i, sig, prices, avail, hour):
        ts = int(t.timestamp())
        prices = {s: p for s, p in prices.items() if p == p and p > 0}
        avail = {s: bool(avail.get(s, False)) and s in prices for s in avail}
        equity, cash, exposure = self.equity(prices)
        ctx = Context(ts, i, sig, prices, avail, self.state, equity, cash, self.ex.can_short, hour, self.strategy.min_notional)
        self.strategy.decide(ctx)
        orders = ctx.orders if self.halted is None else [o for o in ctx.orders if o.book == "overlay" and o.symbol in self.state.lots]   # halted: exits only
        self._execute(ts, orders, prices)
        equity, cash, exposure = self.equity(prices)
        self.ledger.record_equity(self.run_id, ts, equity, cash, exposure / equity if equity > 0 else 0.0)
        self.ledger.commit()
        return equity, orders

    def _execute(self, ts, orders, prices):
        by_symbol = {}
        for o in orders: by_symbol.setdefault(o.symbol, []).append(o)
        for s, os_ in by_symbol.items():
            net = sum(o.notional if o.side == "buy" else -o.notional for o in os_)
            before = self.ex.balances().get(s, 0.0); price, fee_total, ref = prices[s], 0.0, "netted"
            if abs(net) >= self.strategy.min_notional:
                try:
                    f = self.ex.market_order(s, "buy" if net > 0 else "sell", abs(net), prices[s], ts)
                    price, fee_total, ref = f.price, f.fee, f.ref
                except ExecutionError as e:
                    self.ledger.event(self.run_id, ts, "error", f"{s}: {e}"); self.log(f"[{dt.datetime.fromtimestamp(ts, dt.timezone.utc):%Y-%m-%d %H:%M}] {s}: {e}")
                    continue
            gross = sum(o.notional for o in os_); logical = 0.0
            for o in os_:
                fee = fee_total * o.notional / gross if gross else 0.0
                lot = self.state.lots.get(s)
                if o.book == "overlay" and lot is not None:          # exit: the whole lot, in coins
                    qty = lot.qty
                    pnl = lot.side * (price - lot.entry_price) * lot.qty - fee
                    self.ledger.close_lot(self.run_id, s, ts, price, pnl); del self.state.lots[s]
                else:
                    qty = o.notional / price
                    if o.book == "overlay":
                        side = 1 if o.side == "buy" else -1
                        self.state.lots[s] = Lot(s, side, qty, ts, price, o.notional)
                        self.ledger.open_lot(self.run_id, s, side, qty, ts, price, o.notional + fee)
                    else:
                        self.state.base_qty[s] = self.state.base_qty.get(s, 0.0) + (qty if o.side == "buy" else -qty)
                self.ledger.record_fill(self.run_id, ts, s, o.side, qty, price, o.notional, fee, o.book, o.reason, ref)
                logical += qty if o.side == "buy" else -qty
            actual = self.ex.balances().get(s, 0.0) - before          # reconcile: dust between books and holdings goes to the base book
            if abs(actual - logical) > 1e-12:
                self.state.base_qty[s] = self.state.base_qty.get(s, 0.0) + (actual - logical)
            self.ledger.set_base(self.run_id, s, self.state.base_qty.get(s, 0.0))

    # ---- backtest ----
    def backtest(self, store, start, end, warmup_days=None):
        start = pd.Timestamp(start, tz="UTC"); end = pd.Timestamp(end, tz="UTC")
        warm = pd.Timedelta(hours=self.strategy.warmup_hours) if warmup_days is None else pd.Timedelta(days=warmup_days)
        panel = store.panel(self.symbols, (start - warm).timestamp(), end.timestamp())
        sig = self.strategy.signals(panel); close = panel["close"]; avail = panel["avail"]; idx = close.index
        i0 = int(idx.searchsorted(start)); n = len(idx); t0 = time.time()
        for i in range(i0, n):
            t = idx[i]; prices = {s: float(close.iat[i, j]) for j, s in enumerate(close.columns)}
            if self.cash_yield: self.ex.accrue_yield(self.cash_yield, 1.0)
            av = {s: bool(avail.iat[i, j]) for j, s in enumerate(close.columns)}
            self.step(t, i, sig, prices, av, t.hour)
        self.log(f"backtest {self.run_id}: {n - i0} hours in {time.time() - t0:.0f}s")
        return self.ledger.equity_series(self.run_id)

    # ---- paper / live ----
    def live_step(self, store, feed, now=None, history_days=None, max_lag_hours=2, daily_loss_limit=0.05, drawdown_limit=0.30):
        now = now or dt.datetime.now(dt.timezone.utc)
        feed.update(store, self.symbols, now=now)
        hist = dt.timedelta(hours=self.strategy.warmup_hours + 48) if history_days is None else dt.timedelta(days=history_days)
        panel = store.panel(self.symbols, (now - hist).timestamp(), now.timestamp())
        risk.check_data_fresh(panel, now, max_lag_hours)
        sig = self.strategy.signals(panel); close = panel["close"]; i = len(close) - 1; t = close.index[i]
        done = self.ledger.con.execute("SELECT 1 FROM equity WHERE run_id=? AND ts=?", (self.run_id, int(t.timestamp()))).fetchone()
        if done:
            self.log(f"bar {t} already processed"); return None
        eq = self.ledger.equity_series(self.run_id)["equity"]
        try:
            risk.check_daily_loss(eq, daily_loss_limit); risk.check_drawdown(eq, drawdown_limit); self.halted = None
        except risk.RiskError as e:
            self.halted = str(e); self.ledger.event(self.run_id, int(t.timestamp()), "halt", str(e)); self.log(str(e))
        prices = {s: float(close.iat[i, j]) for j, s in enumerate(close.columns)}
        av = {s: bool(panel["avail"].iat[i, j]) for j, s in enumerate(close.columns)}
        if self.cash_yield and hasattr(self.ex, "accrue_yield"): self.ex.accrue_yield(self.cash_yield, 1.0)
        equity, orders = self.step(t, i, sig, prices, av, t.hour)
        self.ledger.event(self.run_id, int(t.timestamp()), "step", f"bar {t}: equity {equity:.2f}, {len(orders)} orders, lots {len(self.state.lots)}")
        if hasattr(self.ex, "_bal"):   # persist paper balances so a restart resumes exactly
            self.ledger.con.execute("INSERT OR REPLACE INTO base VALUES (?,?,?)", (self.run_id, "__paper_balances__", 0.0))
            self.ledger.con.execute("CREATE TABLE IF NOT EXISTS kv (run_id TEXT, key TEXT, value TEXT, PRIMARY KEY (run_id, key))")
            self.ledger.con.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (self.run_id, "paper_balances", json.dumps(self.ex.balances()))); self.ledger.commit()
        return equity, orders

def next_hour_boundary(now=None, grace_seconds=90):
    now = now or dt.datetime.now(dt.timezone.utc)
    nxt = (now.replace(minute=0, second=0, microsecond=0) + dt.timedelta(hours=1)) + dt.timedelta(seconds=grace_seconds)
    return nxt
