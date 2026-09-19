"""Pre-registered multi-coin, multi-window strategy screen on hourly Coinbase data.
Positions are decided at the close of bar t and applied to the return of bar t+1 (no look-ahead).
Costs: round-trip cost per unit of position change, charged per side. Equal-weight portfolio across coins."""
import json, sys, numpy as np, pandas as pd, datetime as dt

COINS = ["BTC-USD","ETH-USD","SOL-USD","ADA-USD","DOGE-USD","LINK-USD","AVAX-USD","DOT-USD","LTC-USD","ATOM-USD"]
COSTS = {"maker 0.06%": 0.0006, "taker 0.15%": 0.0015, "spot 0.30%": 0.0030}
WINDOWS = {"2018": ("2018-01-01","2019-01-01"), "2019": ("2019-01-01","2020-01-01"), "2020": ("2020-01-01","2021-01-01"), "2021": ("2021-01-01","2022-01-01"),
           "2022": ("2022-01-01","2023-01-01"), "2023": ("2023-01-01","2024-01-01"), "2024": ("2024-01-01","2025-01-01"),
           "2025": ("2025-01-01","2026-01-01"), "2026 holdout": ("2026-01-01","2026-12-31")}

def load_hourly(path):
    rows = json.load(open(path))
    df = pd.DataFrame(rows, columns=["t","low","high","open","close","volume"])
    df["t"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df = df.set_index("t").sort_index(); df = df[~df.index.duplicated()]
    return df

def load_coin(c):
    import os
    paths = [p for p in (f"data/{c}_3600s_2017-01-01_2022-01-01.json", f"data/{c}_3600s_2022-01-01_2026-09-19.json") if os.path.exists(p)]
    df = pd.concat([load_hourly(p) for p in paths]).sort_index(); return df[~df.index.duplicated()]

def resample_1m(paths):
    df = pd.concat([load_hourly(p) for p in paths]).sort_index(); df = df[~df.index.duplicated()]
    return df.resample("1h").agg({"low":"min","high":"max","open":"first","close":"last","volume":"sum"})

def build_panel(frames):
    idx = pd.DatetimeIndex(sorted(set().union(*[d.index for d in frames.values()])))
    idx = pd.date_range(idx[0], idx[-1], freq="1h", tz="UTC")
    def col(name, fill):
        out = pd.DataFrame({c: d[name].reindex(idx) for c, d in frames.items()})
        return out
    raw_close = col("close", None); avail = raw_close.notna()
    close = raw_close.ffill()
    high = col("high", None).fillna(close); low = col("low", None).fillna(close)
    openp = col("open", None).fillna(close); vol = col("volume", None).fillna(0.0)
    return dict(close=close, high=high, low=low, open=openp, volume=vol, avail=avail)

# ---------------- candidates: each returns positions (rows=hours, cols=coins) ----------------
def rowmask(df, cond):
    return df.where(np.repeat(np.asarray(cond)[:, None], df.shape[1], axis=1))

def c_buyhold(panel):
    return pd.DataFrame(1.0, index=panel["close"].index, columns=panel["close"].columns)

def c_intraday_mom(panel, first_h=1, last_h=1):
    close, openp = panel["close"], panel["open"]; idx = close.index; hour = idx.hour; day = idx.floor("D")
    open00 = rowmask(openp, hour == 0).groupby(day).transform("first")
    close_first = rowmask(close, hour == first_h - 1).groupby(day).transform("first")
    sig = np.sign(close_first / open00 - 1).fillna(0.0)
    hold = (hour >= 23 - last_h) & (hour <= 22)          # pos at bar t applies to bar t+1 = last `last_h` bars of the day
    pos = pd.DataFrame(0.0, index=idx, columns=close.columns); pos.loc[hold, :] = sig.loc[hold, :].values
    return pos

def c_residual_reversal(panel, k=2.5, hold=4, lookback=720, hedge=False):
    close = panel["close"]; r = np.log(close).diff(); rh = np.log(close).diff(hold); btc = r["BTC-USD"]
    pos = pd.DataFrame(0.0, index=close.index, columns=close.columns); btc_hedge = np.zeros(len(close))
    for c in close.columns:
        if c == "BTC-USD": continue
        beta = r[c].rolling(lookback).cov(btc) / btc.rolling(lookback).var()
        e = rh[c] - beta * rh["BTC-USD"]; z = (e / e.rolling(lookback).std()).values
        p = np.zeros(len(z)); i = 0
        while i < len(z):
            if not np.isnan(z[i]) and abs(z[i]) >= k:
                p[i:i+hold] = -np.sign(z[i]); i += hold
            else: i += 1
        pos[c] = p
        if hedge: btc_hedge += -np.nan_to_num(beta.values) * p
    if hedge: pos["BTC-USD"] = btc_hedge
    return pos

def c_tsmom(panel, lookback_days=30, long_only=False):
    close = panel["close"]; hour = close.index.hour
    sig = np.sign(close / close.shift(lookback_days * 24) - 1)
    if long_only: sig = sig.clip(lower=0)
    return rowmask(sig, hour == 23).ffill().fillna(0.0)

def c_xsmom(panel, lookback_days=28, n=3):
    close = panel["close"]; idx = close.index
    mom = close / close.shift(lookback_days * 24) - 1
    decide = (idx.weekday == 6) & (idx.hour == 23)
    pos = pd.DataFrame(np.nan, index=idx, columns=close.columns)
    for t in idx[decide]:
        row = mom.loc[t].dropna()
        if len(row) < 2 * n: continue
        s = row.sort_values(); p = pd.Series(0.0, index=close.columns)
        p[s.index[:n]] = -1.0; p[s.index[-n:]] = 1.0; pos.loc[t] = p
    return pos.ffill().fillna(0.0)

def c_donchian(panel, entry=80, exit=40):
    close, high, low = panel["close"], panel["high"], panel["low"]
    up = high.rolling(entry).max().shift(1); dn = low.rolling(entry).min().shift(1)
    xl = low.rolling(exit).min().shift(1); xs = high.rolling(exit).max().shift(1)
    pos = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for c in close.columns:
        cl, u, d, el, es = close[c].values, up[c].values, dn[c].values, xl[c].values, xs[c].values
        p = np.zeros(len(cl)); st = 0
        for i in range(len(cl)):
            if np.isnan(u[i]) or np.isnan(cl[i]): p[i] = 0; continue
            if st == 0:
                if cl[i] > u[i]: st = 1
                elif cl[i] < d[i]: st = -1
            elif st == 1:
                if cl[i] < el[i]: st = -1 if cl[i] < d[i] else 0
            else:
                if cl[i] > es[i]: st = 1 if cl[i] > u[i] else 0
            p[i] = st
        pos[c] = p
    return pos

def c_breakout_dayend(panel, lookback=24):
    close, high, low = panel["close"], panel["high"], panel["low"]; hour = close.index.hour
    up = high.rolling(lookback).max().shift(1); dn = low.rolling(lookback).min().shift(1)
    pos = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for c in close.columns:
        cl, u, d = close[c].values, up[c].values, dn[c].values
        p = np.zeros(len(cl)); st = 0
        for i in range(len(cl)):
            if hour[i] == 23: st = 0                      # flat at day end (decision at bar 23 close -> no position overnight)
            elif st == 0 and not np.isnan(u[i]):
                if cl[i] > u[i]: st = 1
                elif cl[i] < d[i]: st = -1
            p[i] = st
        pos[c] = p
    return pos

def c_timeofday(panel, start=13, end=21):
    idx = panel["close"].index; hour = idx.hour
    hold_hours = [(h - 1) % 24 for h in range(start, end)]   # pos at bar h-1 applies to bar h
    pos = pd.DataFrame(0.0, index=idx, columns=panel["close"].columns); pos[np.isin(hour, hold_hours)] = 1.0
    return pos

CANDIDATES = {
    "buy&hold (benchmark)":            lambda p: c_buyhold(p),
    "intraday mom 1h->last 1h":        lambda p: c_intraday_mom(p, 1, 1),
    "intraday mom 2h->last 2h":        lambda p: c_intraday_mom(p, 2, 2),
    "residual reversal 4h (alt only)": lambda p: c_residual_reversal(p, 2.5, 4, 720, False),
    "residual reversal 4h (hedged)":   lambda p: c_residual_reversal(p, 2.5, 4, 720, True),
    "tsmom 7d long/short":             lambda p: c_tsmom(p, 7, False),
    "tsmom 30d long/short":            lambda p: c_tsmom(p, 30, False),
    "tsmom 30d long/flat":             lambda p: c_tsmom(p, 30, True),
    "xs mom 28d weekly top3/bottom3":  lambda p: c_xsmom(p, 28, 3),
    "donchian 80h/40h":                lambda p: c_donchian(p, 80, 40),
    "breakout 24h, exit day end":      lambda p: c_breakout_dayend(p, 24),
    "long US hours 13-21 UTC":         lambda p: c_timeofday(p, 13, 21),
    "long Asia hours 0-8 UTC":         lambda p: c_timeofday(p, 0, 8),
}

# ---------------- evaluation ----------------
def evaluate(pos, panel, cost_rt):
    ret = panel["close"].pct_change().fillna(0.0)
    pos = pos.reindex(ret.index).fillna(0.0) * panel["avail"].astype(float)
    turnover = (pos - pos.shift(1)).abs().fillna(0.0)
    pnl = pos.shift(1).fillna(0.0) * ret - turnover * (cost_rt / 2)
    return pnl, pos

AVAIL = None
def window_stats(pnl, pos, w):
    a, b = WINDOWS[w]; m = (pnl.index >= a) & (pnl.index < b)
    if m.sum() < 24 * 30: return None
    p = pnl[m]; q = pos[m]
    av = AVAIL[m].astype(float) if AVAIL is not None else pd.DataFrame(1.0, index=p.index, columns=p.columns)
    n_listed = av.sum(axis=1).replace(0, np.nan)
    port = (p * av).sum(axis=1) / n_listed
    port = port.fillna(0.0)
    hours = len(port); ann = port.sum() * 8760 / hours
    sharpe = port.mean() / port.std() * np.sqrt(8760) if port.std() > 0 else np.nan
    cum = port.cumsum(); mdd = (cum - cum.cummax()).min()
    listed = av.sum(axis=0) > 24 * 30
    coin_tot = p.sum()[listed]
    sq = np.sign(q); entries = ((sq != 0) & (sq != sq.shift(1).fillna(0))).sum().sum()
    inpos = (q != 0).sum().sum()
    return dict(ann=ann, sharpe=sharpe, mdd=mdd, n_pos=int((coin_tot > 0).sum()), n_coins=int(listed.sum()),
                entries=int(entries), hold=(inpos / entries if entries else np.nan), per_trade=(port.sum() * len(coin_tot) / entries if entries else np.nan))

def run(panel, coins, candidates=CANDIDATES, costs=COSTS, windows=None):
    global AVAIL; AVAIL = panel["avail"]
    windows = windows or list(WINDOWS)
    results = {}
    for name, fn in candidates.items():
        try: pos = fn(panel)
        except Exception as e: print(f"{name}: ERROR {e}"); continue
        results[name] = {}
        for cname, cost in costs.items():
            pnl, p = evaluate(pos, panel, cost)
            results[name][cname] = {w: window_stats(pnl, p, w) for w in windows}
    return results

def print_report(results, cost_focus="taker 0.15%"):
    ws = None
    for name, by_cost in results.items():
        print(f"\n### {name}")
        for cname, by_w in by_cost.items():
            line = []
            for w, s in by_w.items():
                if s is None: line.append(f"{w}: n/a"); continue
                line.append(f"{w}: {s['ann']*100:+.1f}%/yr SR {s['sharpe']:+.2f} coins+ {s['n_pos']}/{s['n_coins']}")
            print(f"  [{cname:<12}] " + " | ".join(line))
        s = [v for v in by_cost[cost_focus].values() if v]
        if s:
            print(f"  trades/window ~{np.mean([x['entries'] for x in s]):.0f}, avg hold {np.nanmean([x['hold'] for x in s]):.1f}h, net per trade {np.nanmean([x['per_trade'] for x in s])*100:+.3f}% at {cost_focus}; "
                  f"max DD (portfolio, {cost_focus}) worst window {min(x['mdd'] for x in s)*100:.1f}%")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke":
        frames = {"BTC-USD": resample_1m(["BTC-USD_1m_2025-09-19_2026-06-21.json","BTC-USD_1m_90d.json"]),
                  "ETH-USD": resample_1m(["ETH-USD_1m_2025-09-19_2026-06-21.json","ETH-USD_1m_90d.json"])}
        panel = build_panel(frames)
        print("smoke panel:", panel["close"].shape, panel["close"].index[0], panel["close"].index[-1])
        cands = {k: v for k, v in CANDIDATES.items() if "xs mom" not in k}
        res = run(panel, list(frames), cands, windows=["2025", "2026 holdout"])
        print_report(res)
    else:
        frames = {c: load_coin(c) for c in COINS}
        panel = build_panel(frames)
        print("panel:", panel["close"].shape, panel["close"].index[0], panel["close"].index[-1])
        print("missing hours per coin:", {c: int(panel['close'][c].isna().sum()) for c in COINS})
        res = run(panel, COINS)
        print_report(res)
        json.dump(res, open("screen_results.json", "w"), default=lambda o: None if (isinstance(o, float) and np.isnan(o)) else float(o) if isinstance(o, (np.floating,)) else int(o) if isinstance(o, np.integer) else str(o))
