"""Fetch hourly candles from Coinbase into the bar store: python scripts/update_data.py --universe research22 --days 400"""
import argparse
from common import *
ap = argparse.ArgumentParser(); ap.add_argument("--universe", default="research22"); ap.add_argument("--days", type=int, default=120); a = ap.parse_args()
store = BarStore(state_dir() / "bars.db"); feed = CoinbaseFeed()
print(feed.update(store, config.universe(a.universe), lookback_days=a.days))
