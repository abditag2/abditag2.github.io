"""Strategy plugin interface.

A strategy is a class with two methods:
  signals(panel) -> dict of DataFrames   precomputed once per backtest or per live step (vectorized over the whole panel)
  decide(ctx)                            called at every completed hour; expresses intent through the Context helpers

Register it with @register("my_name") and reference it from config/strategies.yaml with `class: my_name`.
The engine never looks inside a strategy: it executes the orders the Context collected, books fills, marks equity."""
from dataclasses import dataclass, field
import numpy as np, pandas as pd
from .. import signals as S

@dataclass
class Order:
    symbol: str
    side: str            # "buy" | "sell"
    notional: float      # quote-currency amount, > 0
    book: str            # "base" (target holdings) | "overlay" (discrete trades with an exit)
    reason: str = ""

@dataclass
class Lot:
    symbol: str
    side: int            # +1 long, -1 short
    qty: float
    entry_ts: int
    entry_price: float
    notional: float

@dataclass
class State:
    lots: dict = field(default_factory=dict)      # symbol -> open Lot (one per symbol)
    base_qty: dict = field(default_factory=dict)  # symbol -> signed quantity in the base book
    memo: dict = field(default_factory=dict)      # free-form strategy memory (persisted between live steps)

class Context:
    """Everything a strategy may look at this hour, plus helpers that turn intent into orders."""
    def __init__(self, ts, i, sig, prices, avail, state, equity, cash, can_short, hour, min_notional):
        self.ts, self.i, self.sig, self.prices, self.avail, self.state = ts, i, sig, prices, avail, state
        self.equity, self.cash, self.can_short, self.hour, self.min_notional = equity, cash, can_short, hour, min_notional
        self.orders = []
        self._deployed = sum(abs(q * prices[s]) for s, q in state.base_qty.items() if s in prices) + \
                         sum(abs(l.qty * prices[s]) for s, l in state.lots.items() if s in prices)
    # ---- reads ----
    def symbols(self):                      # symbols with a price and listed
        return [s for s in self.prices if self.avail.get(s, False)]
    def row(self, name):                    # this hour's row of a signal frame
        return self.sig[name].iloc[self.i]
    def value(self, name, symbol):
        v = self.sig[name].iloc[self.i].get(symbol, np.nan); return float(v) if v == v else np.nan
    def base_notional(self, symbol):
        return self.state.base_qty.get(symbol, 0.0) * self.prices.get(symbol, 0.0)
    def deployed(self):
        return self._deployed
    def has_lot(self, symbol):
        return symbol in self.state.lots
    def lot_age_hours(self, symbol):
        return (self.ts - self.state.lots[symbol].entry_ts) / 3600 if symbol in self.state.lots else None
    # ---- intents ----
    def target_base(self, symbol, notional, reason="rebalance"):
        """Move the base book of `symbol` to a signed notional (negative = short; clipped to 0 when the venue cannot short)."""
        if symbol not in self.prices: return
        if notional < 0 and not self.can_short: notional = 0.0
        delta = notional - self.base_notional(symbol)
        if abs(delta) >= self.min_notional:
            self.orders.append(Order(symbol, "buy" if delta > 0 else "sell", abs(delta), "base", reason))
            self._deployed += abs(notional) - abs(self.base_notional(symbol))
            if delta > 0: self.cash -= delta
            else: self.cash += abs(delta)
    def open_lot(self, symbol, notional, side=1, reason="entry", cap=1.0):
        """Open a discrete trade of `notional` (one open lot per symbol). Returns True if the order was placed."""
        if symbol not in self.prices or symbol in self.state.lots or notional < self.min_notional: return False
        if side < 0 and not self.can_short: return False
        if self._deployed + notional > cap * self.equity + 1e-9: return False
        if side > 0 and self.cash - notional < -1e-9: return False
        self.orders.append(Order(symbol, "buy" if side > 0 else "sell", notional, "overlay", reason))
        self._deployed += notional
        if side > 0: self.cash -= notional
        return True
    def close_lot(self, symbol, reason="exit"):
        lot = self.state.lots.get(symbol)
        if lot is None or symbol not in self.prices: return False
        self.orders.append(Order(symbol, "sell" if lot.side > 0 else "buy", abs(lot.qty) * self.prices[symbol], "overlay", reason))
        self._deployed -= abs(lot.qty * self.prices[symbol]); return True

class Strategy:
    """Base class. Subclass, implement decide(ctx), optionally signals(panel) and warmup_hours."""
    warmup_hours = 24 * 100            # history the strategy needs before its first decision

    def __init__(self, cfg):
        self.cfg = dict(cfg); self.name = cfg.get("name", type(self).__name__)
        self.min_notional = float(cfg.get("min_trade_notional", 10.0))

    def signals(self, panel):
        """Default: the research signal set (trend score, realized vol, dip z-score)."""
        return S.compute(panel)

    def decide(self, ctx: Context):
        raise NotImplementedError

    def param(self, key, default=None):
        return self.cfg.get(key, default)
