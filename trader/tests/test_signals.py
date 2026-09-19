"""The trader's signals and overlay entries must match the research implementation (research/crypto-strategy-screen/strats.py)."""
import sys, pathlib, numpy as np, pandas as pd, pytest
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT.parent / "research" / "crypto-strategy-screen"))
from trader import signals as S
from trader.data.store import BarStore
from trader import config

@pytest.fixture(scope="module")
def panel():
    store = BarStore(config.STATE_DIR / "bars.db")
    if store.count("BTC-USD") == 0: pytest.skip("bar store empty; run scripts/import_research_data.py or update_data.py")
    return store.panel(["BTC-USD", "ETH-USD", "SOL-USD"], pd.Timestamp("2023-06-01", tz="UTC").timestamp(), pd.Timestamp("2024-06-01", tz="UTC").timestamp())

def test_signal_shapes_and_ranges(panel):
    sig = S.compute(panel)
    assert set(sig["score"].dropna().stack().unique()) <= {-4, -3, -2, -1, 0, 1, 2, 3, 4}
    assert sig["z"].abs().max().max() < 15
    assert (sig["rv"].dropna() > 0).all().all()

def test_overlay_entries_match_research(panel):
    import bt, strats
    strats.set_panel(panel)
    ref = strats.dip_in_trend(1.5, 24, 24, "ens").clip(lower=0.0)          # research positions: 1 during a long lot, else 0
    sig = S.compute(panel); z, tr = sig["z"], sig["trend"]
    for c in panel["close"].columns:                                        # rebuild the research position series from the trader's signals
        zz, t = z[c].values, tr[c].values; p = np.zeros(len(zz)); i = 0
        while i < len(zz):
            if not np.isnan(zz[i]) and not np.isnan(t[i]) and t[i] > 0 and zz[i] <= -1.5: p[i:i+24] = 1.0; i += 24
            else: i += 1
        assert (p == ref[c].values).all(), c
