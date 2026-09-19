import numpy as np, pandas as pd, bt, os, sys, strats
NEW = ["BCH-USD","ETC-USD","XLM-USD","XTZ-USD","ALGO-USD","UNI-USD","FIL-USD","AAVE-USD","XRP-USD","ICP-USD","NEAR-USD","APT-USD"]
def load(c):
    paths = [p for p in (f"data/{c}_3600s_2017-01-01_2022-01-01.json", f"data/{c}_3600s_2022-01-01_2026-09-19.json") if os.path.exists(p)]
    if not paths: return None
    df = pd.concat([bt.load_hourly(p) for p in paths]).sort_index(); return df[~df.index.duplicated()]
frames = {c: f for c in NEW if (f := load(c)) is not None and len(f) > 24 * 400}
print("holdout coins (first bar):", {c: str(f.index[0].date()) for c, f in frames.items()})
panel = bt.build_panel(frames); strats.set_panel(panel)
print("\nCOIN-LEVEL OUT-OF-SAMPLE: fixed specs from round 4 on 12 coins never used in selection (per-year at taker 0.15%)")
strats.summarize("B* ens-trend, 24h dip, hold 24h", strats.dip_in_trend(1.5, 24, 24, "ens"))
strats.summarize("B* ens-trend, 24h dip, hold 12h", strats.dip_in_trend(1.5, 12, 24, "ens"))
strats.summarize("B* k=2.0, hold 24h", strats.dip_in_trend(2.0, 24, 24, "ens"))
strats.summarize("B* long-only (spot AMM executable)", strats.dip_in_trend(1.5, 24, 24, "ens").clip(lower=0.0))
strats.summarize("B* k=2.0 long-only", strats.dip_in_trend(2.0, 24, 24, "ens").clip(lower=0.0))
strats.summarize("R2 30d-trend, 24h dip, hold 24h", strats.dip_in_trend(1.5, 24, 24, "30d"))
strats.summarize("R3 trend ensemble daily", strats.trend_ens((7,14,30,60)))
strats.summarize("A2-4h {3,5,10,14}d every 4h", strats.trend_ens((3,5,10,14), rebalance_every=4))
strats.summarize("buy&hold", bt.c_buyhold(panel))
