import sys, pathlib, pandas as pd, pytest; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trader import config, metrics
from trader.data.store import BarStore
from trader.ledger import Ledger
from trader.strategy import PortfolioStrategy
from trader.engine import Engine
from trader.execution.paper import PaperExecutor

def test_backtest_runs_and_books_balance(tmp_path):
    store = BarStore(config.STATE_DIR / "bars.db")
    if store.count("BTC-USD") == 0: pytest.skip("bar store empty")
    symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD"]; ledger = Ledger(tmp_path / "t.db"); cfg = config.strategy_config("p1")
    ledger.new_run("t", "backtest", "p1", cfg, symbols)
    ex = PaperExecutor(cash=10_000, can_short=True); eng = Engine(PortfolioStrategy(cfg), ex, ledger, "t", symbols, cash_yield=0.04)
    eq = eng.backtest(store, "2024-01-01", "2024-07-01")
    assert len(eq) > 24 * 150 and eq["equity"].min() > 0
    m = metrics.summarize(eq["equity"], ledger.lots("t"), eq["exposure"]); assert "cagr" in m and m["trades"] >= 1
    # logical books must equal executor holdings per symbol
    bal = ex.balances()
    for s in symbols:
        logical = eng.state.base_qty.get(s, 0.0) + sum(l.qty * l.side for l in eng.state.lots.values() if l.symbol == s)
        assert abs(logical - bal.get(s, 0.0)) < 1e-6, (s, logical, bal.get(s))
    assert (eq["exposure"] <= 1.0001).all()
