# Crypto strategy screen: what survives realistic costs across coins and years

Research notebook-style scripts and raw outputs behind a one-day study (2026-09-19).
Question: is there a short-holding-period crypto strategy that makes money net of fees
across several coins and several backtest windows?

Short answer: no sub-daily strategy survived. A daily-rebalanced, volatility-targeted
trend ensemble did, across 10 coins and 8 of 9 calendar years (2018-2026), including a
pre-registered 2026 holdout and four years (2018-2021) it was never designed on.

## Data

* Coinbase Exchange public candles (`fetch_gran.py`), hourly, 2016-12 to 2026-09-19, for
  BTC, ETH, SOL, ADA, DOGE, LINK, AVAX, DOT, LTC, ATOM (USD pairs). Coins enter the panel
  when Coinbase listed them (3 coins in 2018, 10 from late 2021). Data files are not
  committed (about 100 MB); the fetch script regenerates them.
* 1-minute BTC/ETH candles for the last 12 months (event studies), Kraken Futures 5-minute
  open interest and hourly funding (`oi_study.py`, `final_stats.py`).

## Protocol

* Positions are decided at the close of hour t and applied to the return of hour t+1.
* Costs: 0.15% round trip per unit of position change (perp taker plus slippage); also
  reported at 0.06% (maker) and 0.30% (spot).
* Equal-weight portfolio over listed coins, daily rebalanced, unlevered.
* Windows: calendar years. 2022-2025 were the development windows; 2026 was held out;
  2018-2021 were added afterwards as a second out-of-sample test with the specs unchanged.
* Candidates were specified with fixed parameters before each run (`bt.py`, `round2.py`).

## Result: R3, volatility-targeted trend ensemble

Signal once a day at 00:00 UTC from hourly closes, per coin:

    s   = mean over L in {7, 14, 30, 60} days of sign(close / close_L_days_ago - 1)
    rv  = std(hourly returns, trailing 30 days) * sqrt(8760)
    pos = s * min(1, 0.40 / rv)            # long/short;  long/flat variant: max(pos, 0)

Compounded, equal weight, 0.15% costs, 2018-01-01 to 2026-09-19 (`results/final_stats.out`):

| strategy | CAGR | max drawdown | Sharpe | worst month | avg exposure |
|---|---|---|---|---|---|
| R3 long/short | 22.4% | -25% | 0.95 | -8.0% | 0.32 |
| R3 long/flat (spot only) | 21.1% | -20% | 1.23 | -4.7% | 0.15 |
| buy and hold, equal weight | 13.5% | -87% | 0.58 | -42.1% | 1.00 |

By year, R3 long/short at 0.15% costs (coins with positive net P&L / coins listed):
2018 +21.8% (3/3), 2019 +61.8% (4/4), 2020 +35.3% (4/5), 2021 +33.4% (8/10), 2022 +14.1% (7/10),
2023 +20.4% (7/10), 2024 +19.5% (8/10), 2025 -8.8% (4/10), 2026 YTD +9.7% (5/10).
Long/flat: positive in 6 of 9 years, losing in the bear years 2018, 2022 and 2025.
All 10 coins have positive net P&L over their listed history. Pooled 2018-2025 Sharpe 0.94,
t about 2.6. Results are unchanged by a one or two hour execution delay. Median directional
holding period about 7.5 days; about 39 direction changes per coin per year.

## What did not survive

* Fading fast 5-minute moves on BTC/ETH (1-minute data, 12 months): zero gross edge at every
  horizon; waiting for the move to stall, conditioning on open-interest changes, or on time
  of day did not help out of sample (`study.py`, `oi_study.py`, `oos.py`).
* Intraday momentum (first hour predicts last hour): negative every year 2018-2026, even at
  maker fees. Time-of-day longs (US or Asia hours): negative. 24-hour breakout with day-end
  exit: negative before costs.
* Alt-versus-BTC residual reversal at 4 hours: negative before costs (residuals continue);
  residual momentum at 1-3 days: negative after costs. Weekend reversal: negative.
* Cross-sectional 4-week momentum, weekly: about zero. Raw 7-day and 30-day trend without
  vol targeting: positive most years but -54% and -13% in 2025.
* Dip-buying inside a 30-day uptrend, 24-hour hold (R2): positive in 7 of 9 years, pooled
  Sharpe 0.78, but lost 19% in the 2026 holdout and loses most of its 2025 gain with a
  one-hour execution delay. Not validated.

## Caveats

* Survivorship: the universe is ten coins that are major today. Long/short trend is less
  exposed to this than buy and hold, but not immune.
* Prices are Coinbase spot; a long/short implementation needs perpetual futures. Funding is
  not modeled; over the last 12 months the strategy's BTC and ETH positions would have paid
  about zero net funding, but in a crowded bull year longs pay several percent annualized.
* Slippage is assumed inside the 0.15% cost. No leverage. 2018-2020 rest on 3 to 5 coins.
* The trend family was chosen after the first screen showed it as the only positive family;
  its parameters were fixed before any of the 2018-2021 or 2026 windows were examined.

## Reproduce

    pip install pandas numpy
    for c in BTC-USD ETH-USD SOL-USD ADA-USD DOGE-USD LINK-USD AVAX-USD DOT-USD LTC-USD ATOM-USD; do
      python3 fetch_gran.py $c 2017-01-01 2022-01-01 3600
      python3 fetch_gran.py $c 2022-01-01 2026-09-19 3600
    done
    python3 bt.py          # round 1 screen (2022-2026)
    python3 round2.py      # round 2 candidates
    python3 round3.py      # extended windows 2018-2026
    python3 final_stats.py # compounded statistics, per-coin, funding estimate
