import numpy as np, pandas as pd, bt, round2
from bt import COINS, load_coin, build_panel, run, print_report
CANDS = {
    "buy&hold (benchmark)":                          lambda p: bt.c_buyhold(p),
    "R3 trend ensemble 7/14/30/60d vol-target 40%":  lambda p: round2.r3_trend_ensemble_voltarget(p),
    "R2 dip-in-trend, hold 24h":                     lambda p: round2.r2_dip_in_trend(p, 1.5, 24, 30),
    "tsmom 30d long/short":                          lambda p: bt.c_tsmom(p, 30, False),
    "xs mom 28d weekly top3/bottom3":                lambda p: bt.c_xsmom(p, 28, 3),
    "intraday mom 1h->last 1h":                      lambda p: bt.c_intraday_mom(p, 1, 1),
}
frames = {c: load_coin(c) for c in COINS}
panel = build_panel(frames)
print("panel:", panel["close"].shape, panel["close"].index[0], "->", panel["close"].index[-1])
print("first listed:", {c: str(panel["avail"][c].idxmax().date()) for c in COINS})
res = run(panel, COINS, CANDS, costs={"taker 0.15%": 0.0015, "maker 0.06%": 0.0006})
print_report(res)
print("\npooled all windows 2018-2025 (dev) and 2026 (holdout), taker 0.15%:")
for name, fn in CANDS.items():
    pos = fn(panel); pnl, p = bt.evaluate(pos, panel, 0.0015)
    av = panel["avail"].astype(float); port = ((pnl * av).sum(axis=1) / av.sum(axis=1).replace(0, np.nan)).fillna(0.0)
    for label, a, b in (("2018-2025", "2018-01-01", "2026-01-01"), ("2026", "2026-01-01", "2027-01-01")):
        m = (port.index >= a) & (port.index < b); x = port[m]; yrs = len(x) / 8760
        sr = x.mean() / x.std() * np.sqrt(8760) if x.std() > 0 else float('nan')
        cum = x.cumsum(); mdd = (cum - cum.cummax()).min()
        print(f"  {name:<48} {label}: ann {x.sum()/yrs*100:+.1f}%  Sharpe {sr:+.2f}  t≈{sr*np.sqrt(yrs):+.1f}  maxDD {mdd*100:.0f}%")
