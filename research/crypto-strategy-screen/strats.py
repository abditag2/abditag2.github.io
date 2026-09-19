"""Round 4: holding-period sweep of the trend family, stability grid of dip-in-trend, multi-timeframe exits."""
import numpy as np, pandas as pd, bt, round2
from bt import COINS, load_coin, build_panel, rowmask
panel = None; av = close = idx = hour = None
def set_panel(p):
    global panel, av, close, idx, hour
    panel = p; bt.AVAIL = p["avail"]; av = p["avail"].astype(float); close = p["close"]; idx = close.index; hour = idx.hour

def trend_ens(lbs=(7,14,30,60), target_vol=0.40, rebalance_every=24):
    r = close.pct_change()
    sig = sum(np.sign(close / close.shift(lb * 24) - 1) for lb in lbs) / len(lbs)
    rv = r.rolling(720).std() * np.sqrt(8760)
    pos = sig * (target_vol / rv).clip(upper=1.0)
    decide = (hour % rebalance_every) == (rebalance_every - 1) if rebalance_every < 24 else (hour == 23)
    return rowmask(pos, decide).ffill().fillna(0.0)

def dip_in_trend(k=1.5, hold=24, window=24, trend="30d"):
    rw = np.log(close).diff(window); sigw = rw.rolling(720).std(); z = rw / sigw
    if trend == "30d": tr = np.sign(close / close.shift(720) - 1)
    else: tr = np.sign(sum(np.sign(close / close.shift(lb * 24) - 1) for lb in (7,14,30,60)))
    pos = pd.DataFrame(0.0, index=idx, columns=close.columns)
    for c in close.columns:
        zz, t = z[c].values, tr[c].values; p = np.zeros(len(zz)); i = 0
        while i < len(zz):
            if not np.isnan(zz[i]) and not np.isnan(t[i]) and t[i] != 0 and ((t[i] > 0 and zz[i] <= -k) or (t[i] < 0 and zz[i] >= k)):
                p[i:i+hold] = t[i]; i += hold
            else: i += 1
        pos[c] = p
    return pos

def mtf(short_days=3):
    base = trend_ens(); s3 = np.sign(close / close.shift(short_days * 24) - 1)
    agree = (np.sign(base) == s3).astype(float)
    return base * rowmask(agree, hour == 23).ffill().fillna(0.0)

def portfolio(pos, cost, delay=1):
    ret = close.pct_change().fillna(0.0); pos = pos.reindex(idx).fillna(0.0) * av
    turnover = (pos - pos.shift(1)).abs().fillna(0.0)
    pnl = pos.shift(delay).fillna(0.0) * ret - turnover.shift(delay - 1).fillna(0.0) * (cost / 2)
    port = ((pnl * av).sum(axis=1) / av.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    return port, pnl, pos

def summarize(name, pos):
    port, pnl, p = portfolio(pos, 0.0015); d = port.resample("1D").sum(); d = d[d.index >= "2018"]
    yr = (1 + d).resample("1YE").prod() - 1
    years_pos = int((yr > 0).sum())
    sr = d.mean() / d.std() * np.sqrt(365.25); eq = (1 + d).cumprod(); mdd = (eq / eq.cummax() - 1).min(); cagr = eq.iloc[-1] ** (365.25 / len(d)) - 1
    port_m, _, _ = portfolio(pos, 0.0006); dm = port_m.resample("1D").sum(); dm = dm[dm.index >= "2018"]; sr_m = dm.mean() / dm.std() * np.sqrt(365.25)
    port_d, _, _ = portfolio(pos, 0.0015, delay=2); dd = port_d.resample("1D").sum(); dd = dd[dd.index >= "2018"]; sr_d = dd.mean() / dd.std() * np.sqrt(365.25)
    sq = np.sign(p); m = p.index >= "2018"
    flips = ((sq != 0) & (sq != sq.shift(1).fillna(0)))[m].sum(); inpos = (p != 0)[m].sum()
    hold = np.nanmedian((inpos / flips.replace(0, np.nan)).values)
    coins_tot = (pnl * av)[m].sum(); coins_pos = int((coins_tot > 0).sum())
    print(f"{name:<46} hold {hold:>5.0f}h | yrs+ {years_pos}/9 | CAGR {cagr*100:+5.1f}% | maxDD {mdd*100:4.0f}% | Sharpe taker {sr:+.2f} maker {sr_m:+.2f} 1h-delay {sr_d:+.2f} | coins+ {coins_pos}/10 | "
          + " ".join(f"{t.year%100:02d}:{v*100:+.0f}" for t, v in yr.items()))

