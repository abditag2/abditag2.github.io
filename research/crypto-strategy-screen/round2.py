import json, numpy as np, pandas as pd
import bt
from bt import COINS, COSTS, WINDOWS, load_hourly, build_panel, run, print_report, rowmask

ALTS = [c for c in COINS if c != "BTC-USD"]

def residual_returns(panel, formation, beta_lb=720):
    close = panel["close"]; r = np.log(close).diff(); rf = np.log(close).diff(formation); btc = r["BTC-USD"]
    res = pd.DataFrame(index=close.index, columns=ALTS, dtype=float)
    for c in ALTS:
        beta = r[c].rolling(beta_lb).cov(btc) / btc.rolling(beta_lb).var()
        res[c] = rf[c] - beta * rf["BTC-USD"]
    return res

def r1_residual_xs_mom(panel, formation=24, n=3):
    """Daily at 00:00 UTC: long top-n / short bottom-n alts by residual return over `formation` hours; hold 24h."""
    res = residual_returns(panel, formation); idx = res.index; hour = idx.hour
    pos = pd.DataFrame(np.nan, index=idx, columns=panel["close"].columns)
    for t in idx[hour == 23]:
        row = res.loc[t].dropna()
        if len(row) < 2 * n: continue
        s = row.sort_values(); p = pd.Series(0.0, index=panel["close"].columns)
        p[s.index[:n]] = -1.0; p[s.index[-n:]] = 1.0; pos.loc[t] = p
    return pos.ffill().fillna(0.0)

def r1c_residual_ts_mom_4h(panel, k=2.5, hold=4):
    """Post-hoc flip of round-1 reversal: follow 4h residual spikes. Reported for information only."""
    return -bt.c_residual_reversal(panel, k, hold, 720, False)

def r2_dip_in_trend(panel, k=1.5, hold=24, trend_days=30):
    close = panel["close"]; idx = close.index
    r24 = np.log(close).diff(24); sig24 = r24.rolling(720).std(); trend = np.sign(close / close.shift(trend_days * 24) - 1)
    z = r24 / sig24
    pos = pd.DataFrame(0.0, index=idx, columns=close.columns)
    for c in close.columns:
        zz, tr = z[c].values, trend[c].values; p = np.zeros(len(zz)); i = 0
        while i < len(zz):
            if not np.isnan(zz[i]) and not np.isnan(tr[i]) and ((tr[i] > 0 and zz[i] <= -k) or (tr[i] < 0 and zz[i] >= k)):
                p[i:i+hold] = tr[i]; i += hold
            else: i += 1
        pos[c] = p
    return pos

def r3_trend_ensemble_voltarget(panel, lbs=(7, 14, 30, 60), target_vol=0.40):
    close = panel["close"]; hour = close.index.hour; r = close.pct_change()
    sig = sum(np.sign(close / close.shift(lb * 24) - 1) for lb in lbs) / len(lbs)
    rv = r.rolling(720).std() * np.sqrt(8760)
    lev = (target_vol / rv).clip(upper=1.0)
    pos = (sig * lev)
    return rowmask(pos, hour == 23).ffill().fillna(0.0)

def r4_weekend_reversal(panel):
    close = panel["close"]; idx = close.index
    pos = pd.DataFrame(0.0, index=idx, columns=close.columns)
    # decision at Sunday 23:00 bar close (= Monday 00:00): weekend return from Friday 00:00 (Thu 23:00 bar close)
    dec = (idx.weekday == 6) & (idx.hour == 23)
    wk = np.sign(close / close.shift(72) - 1)     # 72h = Fri 00:00 -> Mon 00:00
    p = rowmask(-wk, dec)
    # hold 24h: bars Sun 23:00 .. Mon 22:00
    hold = ((idx.weekday == 6) & (idx.hour == 23)) | ((idx.weekday == 0) & (idx.hour <= 22))
    pos = p.ffill(limit=23).where(np.repeat(hold[:, None], pos.shape[1], axis=1)).fillna(0.0)
    return pos

CANDS = {
    "R1 residual xs-mom 24h->24h (top3/bot3 alts)": lambda p: r1_residual_xs_mom(p, 24, 3),
    "R1b residual xs-mom 72h->24h":                 lambda p: r1_residual_xs_mom(p, 72, 3),
    "R2 dip-in-trend, hold 24h":                    lambda p: r2_dip_in_trend(p, 1.5, 24, 30),
    "R3 trend ensemble 7/14/30/60d vol-target 40%": lambda p: r3_trend_ensemble_voltarget(p),
    "R4 weekend reversal, hold Monday":             lambda p: r4_weekend_reversal(p),
    "(info) flip of 4h residual reversal":           lambda p: r1c_residual_ts_mom_4h(p),
    "(recount) tsmom 7d long/short":                lambda p: bt.c_tsmom(p, 7, False),
    "(recount) tsmom 30d long/short":               lambda p: bt.c_tsmom(p, 30, False),
}
if __name__ == "__main__":
    frames = {c: load_hourly(f"data/{c}_3600s_2022-01-01_2026-09-19.json") for c in COINS}
    panel = build_panel(frames)
    res = run(panel, COINS, CANDS)
    print_report(res)
    # pooled 2022-2025 Sharpe at taker cost
    print("\npooled 2022-2025 at taker 0.15%:")
    for name, fn in CANDS.items():
        pos = fn(panel); pnl, p = bt.evaluate(pos, panel, 0.0015)
        m = (pnl.index >= "2022-01-01") & (pnl.index < "2026-01-01"); port = pnl[m].mean(axis=1)
        sr = port.mean() / port.std() * np.sqrt(8760); yrs = len(port) / 8760
        print(f"  {name:<48} ann {port.sum()/yrs*100:+.1f}%  Sharpe {sr:+.2f}  t≈{sr*np.sqrt(yrs):+.1f}")
