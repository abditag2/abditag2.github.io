"""Reusable building blocks. A sleeve is a plain object with methods that take a Context; strategies compose them."""
import numpy as np, pandas as pd
from .. import signals as S

class TrendBase:
    """Daily vol-targeted trend positions: weight = (score/4) * min(1, vol_target / realized vol), equal capital per listed coin."""
    def __init__(self, vol_target=0.30, rebalance_hour=23, enabled=True):
        self.vt, self.hour, self.enabled = float(vol_target), int(rebalance_hour), bool(enabled)

    def rebalance(self, ctx):
        if not self.enabled or ctx.hour != self.hour: return
        w = S.base_weight(ctx.sig, self.vt).iloc[ctx.i]
        listed = [s for s in ctx.symbols() if w.get(s, np.nan) == w.get(s, np.nan)]
        if not listed: return
        for s in ctx.prices:
            ctx.target_base(s, ctx.equity * float(w[s]) / len(listed) if s in listed else 0.0, "daily rebalance")

class DipOverlay:
    """Discrete trades: enter on a `sigma` move over the dip window against the trend direction, exit after `hold_hours`."""
    def __init__(self, slots=20, sigma=1.5, hold_hours=24, long_only=True, cap=1.0, enabled=True):
        self.K, self.k, self.hold, self.long_only, self.cap, self.enabled = int(slots), float(sigma), int(hold_hours), bool(long_only), float(cap), bool(enabled)

    def exits(self, ctx):
        for s in list(ctx.state.lots):
            if ctx.lot_age_hours(s) >= self.hold: ctx.close_lot(s, "time exit")

    def entries(self, ctx):
        if not self.enabled: return
        z, tr = ctx.row("z"), ctx.row("trend"); cands = []
        for s in ctx.symbols():
            if ctx.has_lot(s): continue
            zz, t = z.get(s, np.nan), tr.get(s, np.nan)
            if zz != zz or t != t or t == 0: continue
            if t > 0 and zz <= -self.k: cands.append((abs(zz), s, 1))
            elif t < 0 and zz >= self.k and not self.long_only: cands.append((abs(zz), s, -1))
        cands.sort(reverse=True); open_slots = self.K - len(ctx.state.lots); size = ctx.equity / self.K
        for _, s, side in cands:
            if open_slots <= 0: break
            if ctx.open_lot(s, size, side, f"dip z={z[s]:.2f}", cap=self.cap): open_slots -= 1
