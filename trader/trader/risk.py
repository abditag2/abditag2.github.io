"""Kill switches and sanity checks used by the engine in paper/live modes."""
import datetime as dt, pandas as pd

class RiskError(Exception): pass

def check_data_fresh(panel, now, max_lag_hours=2):
    last = panel["close"].index[-1]
    lag = (now - last.to_pydatetime()).total_seconds() / 3600
    if lag > max_lag_hours:
        raise RiskError(f"stale data: last bar {last} is {lag:.1f}h old")

def check_daily_loss(equity: pd.Series, limit=0.05):
    if len(equity) < 2: return
    day = equity[equity.index >= equity.index[-1] - pd.Timedelta(hours=24)]
    loss = day.iloc[-1] / day.max() - 1
    if loss < -limit:
        raise RiskError(f"daily loss {loss:.1%} beyond limit {limit:.0%}: halting new entries")

def check_drawdown(equity: pd.Series, limit=0.30):
    if len(equity) < 2: return
    dd = equity.iloc[-1] / equity.max() - 1
    if dd < -limit:
        raise RiskError(f"drawdown {dd:.1%} beyond limit {limit:.0%}: halting new entries")
