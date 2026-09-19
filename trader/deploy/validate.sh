#!/usr/bin/env bash
# Reproduce the engine validation rows (22 coins, 2018-2026). Needs the bar store filled first.
set -e; cd "$(dirname "$0")/.."
python scripts/backtest.py --strategy p1 --universe research22 --start 2018-01-01 --end 2026-09-19 --run-id p1_22_2018_2026
python scripts/backtest.py --strategy p1 --universe research22 --start 2018-01-01 --end 2026-09-19 --no-short --run-id p1_22_2018_2026_noshort
python scripts/backtest.py --strategy bstar_long --universe research22 --start 2018-01-01 --end 2026-09-19 --run-id bstar_long_22
python scripts/backtest.py --strategy r3 --universe research22 --start 2018-01-01 --end 2026-09-19 --run-id r3_22
python scripts/backtest.py --strategy p1 --universe evm_arbitrum --start 2018-01-01 --end 2026-09-19 --no-short --run-id p1_evm_noshort
