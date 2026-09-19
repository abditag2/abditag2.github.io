import sys, pathlib, json, datetime as dt
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trader import config
from trader.data.store import BarStore, CoinbaseFeed
from trader.ledger import Ledger
from trader.strategies import load_strategy, available
from trader.engine import Engine
from trader.execution.paper import PaperExecutor
from trader import metrics

def state_dir():
    d = config.STATE_DIR; d.mkdir(parents=True, exist_ok=True); return d

def print_metrics(m):
    if not m: print("no metrics (too little equity history)"); return
    print(f"  {m['start']} .. {m['end']}  total {m['total_return']*100:+.1f}%  CAGR {m['cagr']*100:+.1f}%  maxDD {m['max_drawdown']*100:.0f}% ({m['dd_peak']}..{m['dd_trough']})  "
          f"Sharpe {m['sharpe']:.2f}  worst month {m['worst_month']*100:+.1f}%  years+ {m['years_positive']}/{m['years']}"
          + (f"  avg exposure {m['avg_exposure']*100:.0f}%" if 'avg_exposure' in m else "")
          + (f"  trades {m['trades']} hit {m['hit_rate']*100:.0f}% expectancy {m['expectancy']*100:+.2f}%" if 'trades' in m else ""))
    print("  by year: " + "  ".join(f"{y}: {v*100:+.0f}%" for y, v in m["yearly"].items()))
