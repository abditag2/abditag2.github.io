import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from trader.execution.paper import PaperExecutor
from trader.execution.base import ExecutionError

def test_round_trip_costs():
    ex = PaperExecutor(cash=1000, fee_rate=0.0005, slippage=0.00025)
    f = ex.market_order("ETH-USD", "buy", 500, 2000.0)
    assert abs(f.price - 2000 * 1.00025) < 1e-9 and abs(f.notional - 500) < 1e-9
    g = ex.market_order("ETH-USD", "sell", f.qty * 2000.0, 2000.0)
    b = ex.balances()
    assert abs(b["ETH-USD"]) < 1e-12
    assert 1000 - b["USDC"] == pytest.approx(500 * 0.0005 * 2 + 500 * 0.00025 * 2, rel=0.05)   # two fees, two slippages

def test_no_short_clamps():
    ex = PaperExecutor(cash=1000, can_short=False)
    with pytest.raises(ExecutionError): ex.market_order("BTC-USD", "sell", 100, 50000.0)
    ex2 = PaperExecutor(cash=1000, can_short=True); f = ex2.market_order("BTC-USD", "sell", 100, 50000.0)
    assert ex2.balances()["BTC-USD"] < 0 and f.qty > 0

def test_yield_accrual():
    ex = PaperExecutor(cash=1000); ex.accrue_yield(0.04, 8760)
    assert ex.balances()["USDC"] == pytest.approx(1040, rel=1e-6)
