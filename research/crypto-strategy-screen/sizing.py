"""Capital deployment study for B*: K concurrent slots of equity/K each (signals beyond K skipped, priority by |z|),
compounding cash accounting, optional yield on idle cash."""
import numpy as np, pandas as pd, bt, os
ALL = bt.COINS + ["BCH-USD","ETC-USD","XLM-USD","XTZ-USD","ALGO-USD","UNI-USD","FIL-USD","AAVE-USD","XRP-USD","ICP-USD","NEAR-USD","APT-USD"]
def load(c):
    paths = [p for p in (f"data/{c}_3600s_2017-01-01_2022-01-01.json", f"data/{c}_3600s_2022-01-01_2026-09-19.json") if os.path.exists(p)]
    df = pd.concat([bt.load_hourly(p) for p in paths]).sort_index(); return df[~df.index.duplicated()]

def signals(panel, k=1.5, window=24):
    close = panel["close"]; rw = np.log(close).diff(window); z = rw / rw.rolling(720).std()
    tr = np.sign(sum(np.sign(close / close.shift(lb * 24) - 1) for lb in (7,14,30,60)))
    return z, tr

def simulate(panel, z, tr, K, hold=24, cost=0.0015, k=1.5, long_only=False, cash_yield=0.0, start="2018-01-01"):
    close = panel["close"]; ret = close.pct_change().fillna(0.0).values; zv = z.values; tv = tr.values
    idx = close.index; coins = list(close.columns); n, m = ret.shape
    i0 = idx.searchsorted(pd.Timestamp(start, tz="UTC"))
    cash = 1.0; open_pos = {}   # coin j -> [dollars, side, entry_i]
    eq = np.ones(n - i0); dep = np.zeros(n - i0)
    hy = (1 + cash_yield) ** (1 / 8760) - 1
    for t, i in enumerate(range(i0, n)):
        # mark to market
        for j, p in open_pos.items(): p[0] *= (1 + p[1] * ret[i, j])
        cash *= (1 + hy)
        # exits
        for j in [j for j, p in open_pos.items() if i - p[2] >= hold]:
            cash += open_pos[j][0] * (1 - cost / 2); del open_pos[j]
        # entries: candidates this hour, priority by |z|
        cands = []
        for j in range(m):
            if j in open_pos or np.isnan(zv[i, j]) or np.isnan(tv[i, j]) or tv[i, j] == 0: continue
            if tv[i, j] > 0 and zv[i, j] <= -k: cands.append((abs(zv[i, j]), j, 1))
            elif tv[i, j] < 0 and zv[i, j] >= k and not long_only: cands.append((abs(zv[i, j]), j, -1))
        cands.sort(reverse=True)
        equity = cash + sum(p[0] for p in open_pos.values())
        for _, j, side in cands:
            if len(open_pos) >= K: break
            d = min(equity / K, cash)
            if d <= 0: break
            cash -= d; open_pos[j] = [d * (1 - cost / 2), side, i]
        equity = cash + sum(p[0] for p in open_pos.values())
        eq[t] = equity; dep[t] = 1 - cash / equity
    s = pd.Series(eq, index=idx[i0:]); d = s.resample("1D").last().pct_change().dropna()
    yrs = len(d) / 365.25; cagr = s.iloc[-1] ** (1 / yrs) - 1; mdd = (s / s.cummax() - 1).min()
    sharpe = d.mean() / d.std() * np.sqrt(365.25); mo = s.resample("1ME").last().pct_change().dropna()
    yr = s.resample("1YE").last().pct_change().dropna(); first = s.resample("1YE").last().iloc[0] - 1
    yrs_pos = int((yr > 0).sum()) + int(first > 0)
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, worst_mo=mo.min(), dep=dep.mean(), yrs_pos=yrs_pos, n_yrs=len(yr) + 1)

def row(label, r): print(f"{label:<44} CAGR {r['cagr']*100:>6.1f}%  maxDD {r['mdd']*100:>5.0f}%  Sharpe {r['sharpe']:>5.2f}  worst month {r['worst_mo']*100:>6.1f}%  avg deployed {r['dep']*100:>4.0f}%  years+ {r['yrs_pos']}/{r['n_yrs']}")

for label, coins in (("10 original coins", bt.COINS), ("22 coins (original + holdout)", ALL)):
    frames = {c: load(c) for c in coins}; panel = bt.build_panel(frames); z, tr = signals(panel); N = len(coins)
    for lo in (False, True):
        print(f"\n== {label}, {'long-only' if lo else 'long/short'}, 0.15% cost, 2018-2026 ==")
        for K, name in ((N, f"1 slice per coin (K={N}, as tested)"), (10, "K=10 slots of equity/10"), (5, "K=5 slots of equity/5"), (3, "K=3 slots of equity/3"), (2, "K=2 slots of equity/2"), (1, "K=1: all cash into the first signal")):
            row(name, simulate(panel, z, tr, K, long_only=lo))
        row(f"1 slice per coin + 4%/yr yield on idle cash", simulate(panel, z, tr, N, long_only=lo, cash_yield=0.04))
