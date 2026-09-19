"""Stack the slow trend ensemble (R3, ~1/3 deployed) under the 24h dip strategy (B*, K=10 slots) on the same equity."""
import numpy as np, pandas as pd, bt, strats, sizing, os
ALL = sizing.ALL
frames = {c: sizing.load(c) for c in ALL}; panel = bt.build_panel(frames); strats.set_panel(panel)
z, tr = sizing.signals(panel)
def daily_from_sim(K, long_only):
    close = panel["close"]; ret = close.pct_change().fillna(0.0).values; zv = z.values; tv = tr.values; idx = close.index; n, m = ret.shape
    i0 = idx.searchsorted(pd.Timestamp("2018-01-01", tz="UTC")); cash = 1.0; open_pos = {}; eq = np.ones(n - i0); dep = np.zeros(n - i0); cost = 0.0015; k = 1.5
    for t, i in enumerate(range(i0, n)):
        for j, p in open_pos.items(): p[0] *= (1 + p[1] * ret[i, j])
        for j in [j for j, p in open_pos.items() if i - p[2] >= 24]: cash += open_pos[j][0] * (1 - cost / 2); del open_pos[j]
        cands = []
        for j in range(m):
            if j in open_pos or np.isnan(zv[i, j]) or np.isnan(tv[i, j]) or tv[i, j] == 0: continue
            if tv[i, j] > 0 and zv[i, j] <= -k: cands.append((abs(zv[i, j]), j, 1))
            elif tv[i, j] < 0 and zv[i, j] >= k and not long_only: cands.append((abs(zv[i, j]), j, -1))
        cands.sort(reverse=True); equity = cash + sum(p[0] for p in open_pos.values())
        for _, j, side in cands:
            if len(open_pos) >= K: break
            d = min(equity / K, cash)
            if d <= 0: break
            cash -= d; open_pos[j] = [d * (1 - cost / 2), side, i]
        equity = cash + sum(p[0] for p in open_pos.values()); eq[t] = equity; dep[t] = 1 - cash / equity
    s = pd.Series(eq, index=idx[i0:]); return s.resample("1D").last().pct_change().dropna(), pd.Series(dep, index=idx[i0:]).resample("1D").mean()
def daily_r3(long_only):
    pos = strats.trend_ens((7,14,30,60)); pos = pos.clip(lower=0.0) if long_only else pos
    port, pnl, p = strats.portfolio(pos, 0.0015); d = port.resample("1D").sum(); d = d[d.index >= "2018"]
    expo = ((p.abs() * strats.av).sum(axis=1) / strats.av.sum(axis=1).replace(0, np.nan)).fillna(0.0).resample("1D").mean()
    return d, expo[expo.index >= "2018"]
def stats(d, label, expo=None):
    eq = (1 + d).cumprod(); yrs = len(d) / 365.25; cagr = eq.iloc[-1] ** (1 / yrs) - 1; mdd = (eq / eq.cummax() - 1).min()
    sr = d.mean() / d.std() * np.sqrt(365.25); mo = (1 + d).resample("1ME").prod() - 1; yr = (1 + d).resample("1YE").prod() - 1
    ex = f"  avg deployed {expo.mean()*100:3.0f}%  99th pct {expo.quantile(0.99)*100:3.0f}%" if expo is not None else ""
    print(f"{label:<52} CAGR {cagr*100:>5.1f}%  maxDD {mdd*100:>4.0f}%  Sharpe {sr:>4.2f}  worst month {mo.min()*100:>6.1f}%  years+ {int((yr>0).sum())}/{len(yr)}{ex}")
print("22 coins, 0.15% cost, 2018-2026, compounded daily")
for lo in (False, True):
    tag = "long-only" if lo else "long/short"
    dB, eB = daily_from_sim(10, lo); dR, eR = daily_r3(lo)
    idx = dB.index.intersection(dR.index); dB, dR, eB, eR = dB[idx], dR[idx], eB.reindex(idx).fillna(0), eR.reindex(idx).fillna(0)
    stats(dB, f"B* alone, K=10 slots ({tag})", eB)
    stats(dR, f"R3 trend ensemble alone ({tag})", eR)
    stats(dB + dR, f"STACKED: R3 base + B* overlay ({tag})", eB + eR)
    stats(dB + dR + 0.04/365.25 * (1 - eB - eR).clip(lower=0), f"STACKED + 4%/yr yield on idle cash ({tag})", eB + eR)
