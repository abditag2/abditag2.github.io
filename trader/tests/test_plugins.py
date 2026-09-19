import sys, pathlib, pandas as pd, pytest; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from trader import config
from trader.strategies import load_strategy, available, register
from trader.strategies.base import Strategy
from trader.data.store import BarStore
from trader.ledger import Ledger
from trader.engine import Engine
from trader.execution.paper import PaperExecutor

def test_registry_has_builtins():
    assert {"portfolio", "sma_cross", "xs_momentum"} <= set(available())

@pytest.mark.parametrize("name", ["sma_cross", "xs_momentum", "bstar_long"])
def test_example_strategies_run(name, tmp_path):
    store = BarStore(config.STATE_DIR / "bars.db")
    if store.count("BTC-USD") == 0: pytest.skip("bar store empty")
    symbols = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "ADA-USD", "DOGE-USD"]
    cfg = config.strategy_config(name); ledger = Ledger(tmp_path / "t.db"); ledger.new_run("t", "backtest", name, cfg, symbols)
    eng = Engine(load_strategy(cfg), PaperExecutor(cash=10_000), ledger, "t", symbols)
    eq = eng.backtest(store, "2024-01-01", "2024-04-01")
    assert len(eq) > 24 * 80 and eq["equity"].min() > 0 and len(ledger.fills("t")) > 0

def test_custom_inline_strategy(tmp_path):
    @register("always_btc")
    class AlwaysBtc(Strategy):
        warmup_hours = 24
        def signals(self, panel): return {}
        def decide(self, ctx):
            if ctx.hour == 23: ctx.target_base("BTC-USD", ctx.equity * 0.5, "hold half in BTC")
    store = BarStore(config.STATE_DIR / "bars.db")
    if store.count("BTC-USD") == 0: pytest.skip("bar store empty")
    cfg = {"name": "always_btc", "class": "always_btc"}; ledger = Ledger(tmp_path / "t.db"); ledger.new_run("t", "backtest", "always_btc", cfg, ["BTC-USD"])
    eng = Engine(load_strategy(cfg), PaperExecutor(cash=1_000), ledger, "t", ["BTC-USD"])
    eq = eng.backtest(store, "2024-01-01", "2024-02-01")
    assert 0.45 < eq["exposure"].iloc[-1] < 0.55
