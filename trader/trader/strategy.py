"""Portfolio strategy P1 = trend-ensemble base (daily) + 24h dip overlay (hourly) + idle cash.
The strategy is pure: it receives signals, prices, its own state and the account, and returns orders."""
from dataclasses import dataclass, field
import numpy as np, pandas as pd
from . import signals as S

@dataclass
class Order:
    symbol: str
    side: str            # "buy" | "sell"
    notional: float      # quote-currency amount, > 0
    book: str            # "base" | "overlay"
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
    lots: dict = field(default_factory=dict)     # symbol -> Lot (one open lot per symbol)
    base_qty: dict = field(default_factory=dict) # symbol -> signed quantity held by the base book

class PortfolioStrategy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.K = int(cfg.get("overlay_slots", 20)); self.k = float(cfg.get("dip_sigma", 1.5)); self.hold = int(cfg.get("hold_hours", 24))
        self.vt = float(cfg.get("base_vol_target", 0.30)); self.cap = float(cfg.get("exposure_cap", 1.0))
        self.min_notional = float(cfg.get("min_trade_notional", 10.0)); self.rebalance_hour = int(cfg.get("base_rebalance_hour", 23))
        self.overlay_long_only = bool(cfg.get("overlay_long_only", True))
        self.base_enabled = bool(cfg.get("base_enabled", True)); self.overlay_enabled = bool(cfg.get("overlay_enabled", True))

    def decide(self, t, i, sig, prices, avail, state: State, equity, cash, can_short, hour):
        """t: bar timestamp; i: row index into signal frames; prices: {symbol: close at t}."""
        orders = []
        base_notional = {s: state.base_qty.get(s, 0.0) * prices[s] for s in prices}
        lot_notional = {s: l.qty * prices[s] for s, l in state.lots.items()}
        deployed = sum(abs(v) for v in base_notional.values()) + sum(abs(v) for v in lot_notional.values())

        # 1. overlay time exits
        for s, lot in list(state.lots.items()):
            if t - lot.entry_ts >= self.hold * 3600:
                orders.append(Order(s, "sell" if lot.side > 0 else "buy", abs(lot.qty) * prices[s], "overlay", "time exit"))
                deployed -= abs(lot_notional.get(s, 0.0))

        # 2. base rebalance once a day
        if self.base_enabled and hour == self.rebalance_hour:
            w = S.base_weight(sig, self.vt)
            row = w.iloc[i]; ok = row.notna() & pd.Series(avail).reindex(row.index).fillna(False).astype(bool)
            n_listed = int(ok.sum())
            if n_listed:
                for s in prices:
                    tgt = 0.0 if not ok.get(s, False) else equity * float(row[s]) / n_listed
                    if tgt < 0 and not can_short: tgt = 0.0
                    delta = tgt - base_notional.get(s, 0.0)
                    if abs(delta) >= self.min_notional:
                        orders.append(Order(s, "buy" if delta > 0 else "sell", abs(delta), "base", "daily rebalance"))
                        deployed += abs(tgt) - abs(base_notional.get(s, 0.0))

        # 3. overlay entries
        if self.overlay_enabled:
            open_slots = self.K - len(state.lots)
            zrow = sig["z"].iloc[i]; trow = sig["trend"].iloc[i]
            cands = []
            for s in prices:
                if s in state.lots or not avail.get(s, False): continue
                zz, tr = zrow[s], trow[s]
                if np.isnan(zz) or np.isnan(tr) or tr == 0: continue
                if tr > 0 and zz <= -self.k: cands.append((abs(zz), s, 1))
                elif tr < 0 and zz >= self.k and not self.overlay_long_only and can_short: cands.append((abs(zz), s, -1))
            cands.sort(reverse=True)
            size = equity / self.K
            for _, s, side in cands:
                if open_slots <= 0: break
                if deployed + size > self.cap * equity + 1e-9: break
                if side > 0 and cash - size < -1e-9: break
                if size < self.min_notional: break
                orders.append(Order(s, "buy" if side > 0 else "sell", size, "overlay", f"dip z={zrow[s]:.2f}"))
                deployed += size; open_slots -= 1
                if side > 0: cash -= size
        return orders
