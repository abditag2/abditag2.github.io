"""Performance metrics with the same definitions as the research (daily resample of hourly equity)."""
import numpy as np, pandas as pd

def summarize(equity: pd.Series, lots: pd.DataFrame = None, exposure: pd.Series = None):
    s = equity.dropna()
    if len(s) < 48: return {}
    d = s.resample("1D").last().dropna().pct_change().dropna()
    yrs = max(len(d) / 365.25, 1e-9)
    cagr = (s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1 if yrs > 0.05 else np.nan
    dd = s / s.cummax() - 1; trough = dd.idxmin(); peak = s[:trough].idxmax()
    sharpe = d.mean() / d.std() * np.sqrt(365.25) if d.std() > 0 else np.nan
    mo = s.resample("1ME").last().pct_change().dropna()
    ye = s.resample("1YE").last(); yr = ye.pct_change().dropna()
    if len(ye): yr = pd.concat([pd.Series({ye.index[0]: ye.iloc[0] / s.iloc[0] - 1}), yr])
    out = dict(start=str(s.index[0].date()), end=str(s.index[-1].date()), total_return=s.iloc[-1] / s.iloc[0] - 1, cagr=cagr,
               max_drawdown=dd.min(), dd_peak=str(peak.date()), dd_trough=str(trough.date()), sharpe=sharpe,
               worst_month=mo.min() if len(mo) else np.nan, best_month=mo.max() if len(mo) else np.nan,
               years_positive=int((yr > 0).sum()), years=len(yr), yearly={str(k.year): float(v) for k, v in yr.items()})
    if exposure is not None and len(exposure): out["avg_exposure"] = float(exposure.mean())
    if lots is not None and len(lots):
        cl = lots[lots["status"] == "closed"]
        if len(cl):
            r = cl["pnl"] / cl["notional"]
            out.update(trades=int(len(cl)), hit_rate=float((r > 0).mean()), expectancy=float(r.mean()), worst_trade=float(r.min()), best_trade=float(r.max()))
    return out

def drawdown(equity: pd.Series):
    s = equity.dropna(); return s / s.cummax() - 1
