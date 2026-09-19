"""Signals, identical to research/crypto-strategy-screen (strats.py, portfolio.py)."""
import numpy as np, pandas as pd

def compute(panel, lookbacks=(7, 14, 30, 60), vol_window=720, dip_window=24):
    close = panel["close"]
    r = close.pct_change()
    rv = r.rolling(vol_window).std() * np.sqrt(8760)                       # annualized realized vol
    score = sum(np.sign(close / close.shift(lb * 24) - 1) for lb in lookbacks)  # -4 .. +4
    rw = np.log(close).diff(dip_window)
    z = rw / rw.rolling(vol_window).std()                                  # dip z-score
    return dict(score=score, trend=np.sign(score), rv=rv, z=z, s_norm=score / len(lookbacks))

def base_weight(sig, vt):
    """Vol-targeted trend weight per coin in [-1, 1]: (score/4) * min(1, vt / realized vol)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        lev = (vt / sig["rv"]).clip(upper=1.0)
    return sig["s_norm"] * lev
