import json, numpy as np, pandas as pd, bt, round2, datetime as dt
from bt import COINS, load_coin, build_panel
frames = {c: load_coin(c) for c in COINS}; panel = build_panel(frames); bt.AVAIL = panel["avail"]
av = panel["avail"].astype(float); ret = panel["close"].pct_change().fillna(0.0)

def r3_longflat(p): return round2.r3_trend_ensemble_voltarget(p).clip(lower=0.0)
STRATS = {"R3 trend ensemble L/S": round2.r3_trend_ensemble_voltarget, "R3 long/flat (spot only)": r3_longflat,
          "R2 dip-in-trend 24h": lambda p: round2.r2_dip_in_trend(p, 1.5, 24, 30), "buy&hold": bt.c_buyhold}

def portfolio_daily(pos, cost=0.0015):
    pnl, p = bt.evaluate(pos, panel, cost)
    port_h = ((pnl * av).sum(axis=1) / av.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    daily = port_h.resample("1D").sum()                      # daily simple return of equal-weight, daily-rebalanced portfolio
    expo = ((p.abs() * av).sum(axis=1) / av.sum(axis=1).replace(0, np.nan)).fillna(0.0).resample("1D").mean()
    return daily, expo, pnl, p

def stats(d):
    d = d[(d.index >= "2018-01-01")]
    eq = (1 + d).cumprod(); yrs = len(d) / 365.25
    cagr = eq.iloc[-1] ** (1 / yrs) - 1; mdd = (eq / eq.cummax() - 1).min()
    sr = d.mean() / d.std() * np.sqrt(365.25); mo = (1 + d).resample("1ME").prod() - 1
    return cagr, mdd, sr, (mo > 0).mean(), mo.min(), yrs

print("Compounded, equal-weight over listed coins, daily rebalanced, taker 0.15% RT costs, 2018-01-01 .. 2026-09-19")
print(f"{'strategy':<26}{'CAGR':>8}{'maxDD':>8}{'Sharpe':>8}{'pos.months':>11}{'worst mo':>10}{'avg |exposure|':>16}")
for name, fn in STRATS.items():
    d, expo, pnl, p = portfolio_daily(fn(panel))
    cagr, mdd, sr, pm, wm, yrs = stats(d)
    print(f"{name:<26}{cagr*100:>7.1f}%{mdd*100:>7.0f}%{sr:>8.2f}{pm*100:>10.0f}%{wm*100:>9.1f}%{expo[expo.index>='2018'].mean():>15.2f}")

print("\nR3 L/S: compounded return by calendar year (portfolio) and per-coin net total (sum of hourly returns, 2018-2026):")
d, expo, pnl, p = portfolio_daily(round2.r3_trend_ensemble_voltarget(panel))
yr = ((1 + d[d.index >= "2018"]).resample("1YE").prod() - 1)
print("  by year: " + "  ".join(f"{t.year}: {v*100:+.1f}%" for t, v in yr.items()))
coin_tot = (pnl * av)[pnl.index >= "2018"].sum()
listed_years = av[av.index >= "2018"].sum() / 8760
print("  per coin: " + "  ".join(f"{c.split('-')[0]} {coin_tot[c]*100:+.0f}% ({listed_years[c]:.1f}y)" for c in COINS))
sq = np.sign(p); flips = ((sq != 0) & (sq != sq.shift(1).fillna(0)))[p.index >= "2018"].sum()
inpos = (p != 0)[p.index >= "2018"].sum()
print(f"  directional holding period (hours in position / sign changes), median across coins: {np.median((inpos / flips).values):.0f}h; sign changes per coin per year, median: {np.median((flips / listed_years).values):.0f}")

# funding cost estimate for a perp implementation, last 12 months, BTC and ETH (Kraken hourly funding; long pays when positive)
import urllib.request
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"x"}), timeout=30) as r: return json.loads(r.read())
print("\nFunding paid by R3 positions over the last 12 months (Kraken hourly funding, position x rate, negative = cost):")
for coin, sym in (("BTC-USD","PF_XBTUSD"), ("ETH-USD","PF_ETHUSD")):
    rates = get(f"https://futures.kraken.com/derivatives/api/v4/historical-funding-rates?symbol={sym}")["rates"]
    f = pd.Series({pd.Timestamp(r["timestamp"]): float(r["relativeFundingRate"]) for r in rates}).sort_index()
    pos = p[coin].reindex(f.index, method="ffill").fillna(0.0)
    paid = -(pos * f).sum(); gross = (pnl[coin].reindex(f.index).fillna(0.0)).sum()
    print(f"  {coin}: funding P&L {paid*100:+.2f}% vs strategy net P&L {gross*100:+.2f}% over {len(f)/8760:.1f}y  (avg position {pos.mean():+.2f})")
