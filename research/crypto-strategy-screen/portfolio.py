"""Multi-sleeve portfolio simulator with cash accounting: B* dip overlay (K slots, optional vol-scaled sizing, optional stop),
R3 trend ensemble base (daily), idle-cash yield, optional portfolio-level vol targeting, total exposure capped at 100%."""
import numpy as np, pandas as pd, bt, os, sys, json

def load(c):
    paths = [p for p in (f"data/{c}_3600s_2017-01-01_2022-01-01.json", f"data/{c}_3600s_2022-01-01_2026-09-19.json") if os.path.exists(p)]
    if not paths: return None
    df = pd.concat([bt.load_hourly(p) for p in paths]).sort_index(); df = df[~df.index.duplicated()]
    return df if len(df) > 24 * 400 else None

def prepare(coins):
    frames = {c: f for c in coins if (f := load(c)) is not None}
    panel = bt.build_panel(frames); close = panel["close"]
    r = close.pct_change(); rv = r.rolling(720).std() * np.sqrt(8760)
    rw = np.log(close).diff(24); sig24 = rw.rolling(720).std(); z = rw / sig24
    tr = np.sign(sum(np.sign(close / close.shift(lb * 24) - 1) for lb in (7,14,30,60)))
    s = sum(np.sign(close / close.shift(lb * 24) - 1) for lb in (7,14,30,60)) / 4
    return dict(panel=panel, close=close, ret=r.fillna(0.0).values, rv=rv.values, z=z.values, sig24=sig24.values, tr=tr.values,
                s=s.values, avail=panel["avail"].values, idx=close.index, coins=list(close.columns))

def simulate(D, K=10, vol_scale=False, stop=None, use_r3=True, long_only=False, cash_yield=0.04, port_vol=None,
             cost=0.0015, k=1.5, hold=24, start="2018-01-01", cap=1.0, r3_vt=0.40, max_new_per_day=None, delay=0):
    ret, rv, z, sig24, tr, avail, idx = D["ret"], D["rv"], D["z"], D["sig24"], D["tr"], D["avail"], D["idx"]
    with np.errstate(divide="ignore", invalid="ignore"):
        r3 = D["s"] * np.minimum(1.0, r3_vt / D["rv"])
    day_of = idx.floor("D").values; new_today = 0; today = None
    n, m = ret.shape; i0 = idx.searchsorted(pd.Timestamp(start, tz="UTC")); hours = idx.hour.values
    cash = 1.0; slots = {}; base = np.zeros(m)          # base: dollar position per coin for the R3 sleeve (signed)
    eq = np.ones(n - i0); dep = np.zeros(n - i0); hy = (1 + cash_yield) ** (1 / 8760) - 1
    f = 1.0; daily_eq = []
    for t, i in enumerate(range(i0, n)):
        # mark to market
        for j, p in slots.items(): p[0] *= (1 + p[1] * ret[i, j])
        base = base * (1 + np.sign(base) * ret[i])             # signed dollars: long gains with ret, short gains when ret < 0
        cash *= (1 + hy)
        equity = cash + sum(p[0] for p in slots.values()) + np.abs(base).sum()
        # portfolio vol targeting: scale factor from trailing 30-day realized vol of daily equity
        if hours[i] == 23:
            daily_eq.append(equity)
            if port_vol and len(daily_eq) > 31:
                d = np.diff(np.log(daily_eq[-31:])); pv = d.std() * np.sqrt(365.25)
                f = min(1.0, port_vol / pv) if pv > 0 else 1.0
        # slot exits: time stop or price stop
        for j in [j for j, p in slots.items() if (i - p[2] >= hold) or (stop is not None and p[0] / p[3] - 1 <= -p[4])]:
            cash += slots[j][0] * (1 - cost / 2); del slots[j]
        # R3 base rebalance daily at 23:00
        si = i - delay
        if use_r3 and hours[i] == 23:
            listed = avail[i].astype(bool); nl = listed.sum()
            for j in range(m):
                tgt = 0.0 if (not listed[j] or np.isnan(r3[si, j])) else equity * f * r3[si, j] / nl
                delta = tgt - base[j]
                if abs(delta) > 1e-9:
                    cash -= (abs(tgt) - abs(base[j])) + abs(delta) * cost / 2   # capital moves into/out of the base book, cost on turnover
                    base[j] = tgt
        # slot entries
        cands = []
        for j in range(m):
            if j in slots or not avail[i, j] or np.isnan(z[si, j]) or np.isnan(tr[si, j]) or tr[si, j] == 0: continue
            if tr[si, j] > 0 and z[si, j] <= -k: cands.append((abs(z[si, j]), j, 1))
            elif tr[si, j] < 0 and z[si, j] >= k and not long_only: cands.append((abs(z[si, j]), j, -1))
        cands.sort(reverse=True)
        if day_of[i] != today: today = day_of[i]; new_today = 0
        equity = cash + sum(p[0] for p in slots.values()) + np.abs(base).sum()
        for _, j, side in cands:
            if len(slots) >= K: break
            if max_new_per_day is not None and new_today >= max_new_per_day: break
            mult = float(np.clip(0.8 / rv[i, j], 0.5, 1.5)) if (vol_scale and not np.isnan(rv[i, j])) else 1.0
            d = equity / K * f * mult
            deployed = sum(p[0] for p in slots.values()) + np.abs(base).sum()
            d = min(d, cash, cap * equity - deployed)
            if d <= 0: continue
            st = (2.0 * sig24[i, j] if (stop is not None and not np.isnan(sig24[i, j])) else 9.0)
            cash -= d; slots[j] = [d * (1 - cost / 2), side, i, d * (1 - cost / 2), st]; new_today += 1
        equity = cash + sum(p[0] for p in slots.values()) + np.abs(base).sum()
        eq[t] = equity; dep[t] = 1 - cash / equity
    s = pd.Series(eq, index=idx[i0:]); d = s.resample("1D").last().pct_change().dropna()
    yrs = len(d) / 365.25; cagr = s.iloc[-1] ** (1 / yrs) - 1; ddser = (s / s.cummax() - 1); mdd = ddser.min()
    trough = ddser.idxmin(); peak = s[:trough].idxmax()
    sharpe = d.mean() / d.std() * np.sqrt(365.25); mo = s.resample("1ME").last().pct_change().dropna()
    ye = s.resample("1YE").last(); yr = ye.pct_change().dropna(); first = ye.iloc[0] - 1
    yrs_pos = int((yr > 0).sum()) + int(first > 0); ytd26 = s.iloc[-1] / s[s.index < "2026-01-01"].iloc[-1] - 1
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, worst_mo=mo.min(), dep=dep.mean(), yrs_pos=yrs_pos, n_yrs=len(yr) + 1, ytd26=ytd26,
                dd_when=f"{peak:%Y-%m-%d}..{trough:%Y-%m-%d}",
                years=" ".join(f"{y.year%100:02d}:{v*100:+.0f}" for y, v in ([(ye.index[0], first)] + list(yr.items()))))

def row(label, r):
    ok = (r['cagr'] >= 0.30) and (r['mdd'] >= -0.25) and (r['sharpe'] >= 1.5) and (r['worst_mo'] >= -0.10) and (r['yrs_pos'] >= 8)
    print(f"{'PASS' if ok else '    '} {label:<50} CAGR {r['cagr']*100:>5.1f}%  maxDD {r['mdd']*100:>4.0f}%  Sharpe {r['sharpe']:>4.2f}  worst mo {r['worst_mo']*100:>6.1f}%  yrs+ {r['yrs_pos']}/{r['n_yrs']}  deployed {r['dep']*100:>3.0f}%  2026ytd {r['ytd26']*100:+.0f}%  DD {r['dd_when']}  | {r['years']}")

CONFIGS_M = [
    ("B* K=10 L/S + yield (ref)",                        dict(use_r3=False)),
    ("B* K=10 long-only + yield",                        dict(use_r3=False, long_only=True)),
    ("B* K=10 long-only, max 3 new/day + yield",         dict(use_r3=False, long_only=True, max_new_per_day=3)),
    ("R3 L/S vt40 + yield (ref)",                        dict(K=0)),
    ("R3 L/S vt60 + yield",                              dict(K=0, r3_vt=0.60)),
    ("R3 L/S vt80 + yield",                              dict(K=0, r3_vt=0.80)),
    ("M1 R3 vt40 + B* long-only K=10 + yield",           dict(long_only=True)),
    ("M2 R3 vt60 + B* long-only K=10 + yield",           dict(long_only=True, r3_vt=0.60)),
    ("M3 R3 vt40 + B* long-only, max 3 new/day",         dict(long_only=True, max_new_per_day=3)),
    ("M4 R3 vt40 + B* L/S, max 3 new/day",               dict(max_new_per_day=3)),
    ("M5 R3 vt60 + B* L/S K=10",                         dict(r3_vt=0.60)),
    ("M6 R3 vt40 + B* long-only K=20 (5% slots)",        dict(long_only=True, K=20)),
    ("M7 R3 vt60 + B* long-only K=10, port vol 25%",     dict(long_only=True, r3_vt=0.60, port_vol=0.25)),
    ("M8 R3 vt40 + B* long-only K=10, port vol 20%",     dict(long_only=True, port_vol=0.20)),
    ("M9 R3 vt30 + B* long-only K=20",                   dict(long_only=True, K=20, r3_vt=0.30)),
    ("M10 R3 vt30 + B* long-only K=15",                  dict(long_only=True, K=15, r3_vt=0.30)),
    ("M11 R3 vt40 + B* long-only K=20, port vol 20%",    dict(long_only=True, K=20, port_vol=0.20)),
    ("M12 R3 vt50 + B* long-only K=20",                  dict(long_only=True, K=20, r3_vt=0.50)),
]
CONFIGS = [
    ("B* K=10 only, no yield",                   dict(use_r3=False, cash_yield=0.0)),
    ("B* K=10 + yield 4%",                       dict(use_r3=False)),
    ("B* K=10 vol-scaled + stop 2σ + yield",     dict(use_r3=False, vol_scale=True, stop=None)),  # stop set below
    ("R3 only + yield",                          dict(K=0)),
    ("Stacked: R3 + B* K=10 + yield",            dict()),
    ("Stacked, slots vol-scaled",                dict(vol_scale=True)),
    ("Stacked, vol-scaled, stop -2σ24",          dict(vol_scale=True, stop="2s")),
    ("Stacked, vol-scaled, stop, port vol 25%",  dict(vol_scale=True, stop="2s", port_vol=0.25)),
    ("Stacked, vol-scaled, stop, port vol 20%",  dict(vol_scale=True, stop="2s", port_vol=0.20)),
    ("Stacked, vol-scaled, stop, port vol 15%",  dict(vol_scale=True, stop="2s", port_vol=0.15)),
    ("Stacked K=15, vol-scaled, stop, port vol 20%", dict(K=15, vol_scale=True, stop="2s", port_vol=0.20)),
    ("Long-only stacked, vol-scaled, stop",      dict(vol_scale=True, stop="2s", long_only=True)),
    ("Long-only stacked, vol-scaled, stop, port vol 20%", dict(vol_scale=True, stop="2s", long_only=True, port_vol=0.20)),
]
if __name__ == "__main__":
    coins = sys.argv[1].split(",") if len(sys.argv) > 1 else bt.COINS
    D = prepare(coins); print(f"panel: {len(D['coins'])} coins, {D['idx'][0].date()} .. {D['idx'][-1].date()}")
    print("PASS bar: CAGR>=30%, maxDD>=-25%, Sharpe>=1.5, worst month>=-10%, years+>=8/9, no leverage\n")
    for label, cfg in (CONFIGS_M if os.environ.get("MSET") else CONFIGS):
        cfg = dict(cfg)
        if cfg.get("stop") == "2s": cfg["stop"] = True
        row(label, simulate(D, **cfg))
