"""Two small strategies that show the plugin interface. Copy one as a template for your own."""
import numpy as np, pandas as pd
from . import register
from .base import Strategy

@register("sma_cross")
class SmaCross(Strategy):
    """Long/flat: hold a coin while its close is above its N-hour moving average; equal capital per listed coin; rebalance daily."""
    warmup_hours = 24 * 40

    def signals(self, panel):
        n = int(self.param("sma_hours", 24 * 30))
        return {"sma": panel["close"].rolling(n).mean(), "close": panel["close"]}

    def decide(self, ctx):
        if ctx.hour != int(self.param("rebalance_hour", 23)): return
        above = [s for s in ctx.symbols() if ctx.value("close", s) > ctx.value("sma", s)]
        for s in ctx.prices:
            ctx.target_base(s, ctx.equity / max(len(ctx.symbols()), 1) if s in above else 0.0, "sma cross")

@register("xs_momentum")
class CrossSectionalMomentum(Strategy):
    """Weekly: long the top `n` coins by trailing `lookback_days` return, short the bottom `n` when the venue allows it."""
    warmup_hours = 24 * 60

    def signals(self, panel):
        lb = int(self.param("lookback_days", 28))
        return {"mom": panel["close"] / panel["close"].shift(lb * 24) - 1}

    def decide(self, ctx):
        if not (ctx.hour == 23 and pd.Timestamp(ctx.ts, unit="s", tz="UTC").weekday() == 6): return   # Sunday 23:00 -> Monday 00:00
        n = int(self.param("n", 3)); gross = float(self.param("gross_exposure", 0.6))
        mom = {s: ctx.value("mom", s) for s in ctx.symbols()}; mom = {s: v for s, v in mom.items() if v == v}
        if len(mom) < 2 * n: return
        ranked = sorted(mom, key=mom.get); shorts, longs = ranked[:n], ranked[-n:]
        per = ctx.equity * gross / (2 * n)
        for s in ctx.prices:
            ctx.target_base(s, per if s in longs else (-per if (s in shorts and ctx.can_short) else 0.0), "weekly momentum")
