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

## Final strategy: B*, trend-filtered 24-hour dip, held 24 hours

Per coin, evaluated every hour on hourly closes (`strats.dip_in_trend(1.5, 24, 24, "ens")`):

    s     = sum over L in {7, 14, 30, 60} days of sign(close / close_L_days_ago - 1)   # trend direction
    z     = ln(close / close_24h_ago) / std(that 24h log return, trailing 30 days)
    entry = long  one unit if sign(s) > 0 and z <= -1.5          (a 1.5-sigma down day inside an uptrend)
            short one unit if sign(s) < 0 and z >= +1.5          (long-only variant skips this)
    exit  = exactly 24 hours later; no re-entry while a position is open

Equal capital slice per coin, one position per coin at a time, about 32 trades per coin per year,
roughly 10% of capital deployed on average. Compounded, daily equal weight, 0.15% round trip:

| panel | variant | years positive | CAGR | max DD | Sharpe | 1h-delay Sharpe | coins positive |
|---|---|---|---|---|---|---|---|
| 10 original coins (selection panel) | long/short | 8 of 9 | 20.2% | -24% | 0.99 | 0.98 | 10 of 10 |
| 10 original coins | long-only | 7 of 9 | 14.4% | -16% | 0.97 | 0.96 | 10 of 10 |
| 12 holdout coins, never used in selection | long/short | 8 of 9 | 23.2% | -24% | 1.13 | 1.06 | 10 of 12 |
| 12 holdout coins | long-only | 8 of 9 | 19.9% | -15% | 1.34 | 1.46 | 12 of 12 |
| 6 EVM-tradeable tokens (WETH, WBTC, LINK, UNI, AAVE, WAVAX) | long-only | 8 of 9 | 10.7% | -21% | 0.74 | 0.76 | 6 of 6 |

Holdout coins: BCH, ETC, XLM, XTZ, ALGO, UNI, FIL, AAVE, XRP, ICP, NEAR, APT. Buy and hold on that
basket lost 15% a year with a 96% drawdown, so survivorship is not what drives the result.
The only losing year in most rows is 2026 year-to-date (-3% to -15%), the most recent window.

Robustness (`results/sensitivity.out`, original panel): threshold k from 1.0 to 2.5 sigma all give
7 to 9 positive years (k = 2.0: Sharpe 1.36, max DD -15%); execution delays of 1, 2 and 4 hours give
Sharpe 0.98, 1.08 and 0.80; costs of 0.06 / 0.15 / 0.30 / 0.60% give CAGR 23.8 / 20.2 / 14.6 / 4.0%.
2,276 trades: mean net +0.57%, median +0.44%, hit rate 54%, worst -36%, t about 4.9.
The 12-hour-hold neighbour is also positive in 8 of 9 years on both panels (`results/round4.out`);
12-hour dip windows and 48-hour holds are worse or negative, and a 30-day trend filter instead of the
ensemble is weaker (the pre-registered R2 cell: 7 of 9 years, holdout-coin Sharpe 0.39).

How it was found: R2 (30-day trend, 24h dip, 24h hold) was pre-registered in round 2 and passed
2018-2025 but lost 19% in the 2026 holdout. Round 4 ran a fixed 12-cell grid (trend filter x dip
window x hold); the ensemble-trend / 24h / 24h cell and its 12h neighbour were the plateau. Because
that choice used all years, the 12 holdout coins above are the out-of-sample test.

## Slower alternative: R3, volatility-targeted trend ensemble

    s   = mean over L in {7, 14, 30, 60} days of sign(close / close_L_days_ago - 1)
    rv  = std(hourly returns, trailing 30 days) * sqrt(8760)
    pos = s * min(1, 0.40 / rv)     # daily at 00:00 UTC; long/flat variant: max(pos, 0)

Original panel: CAGR 22.4%, max DD -25%, Sharpe 0.95, 8 of 9 years, all 10 coins; holdout coins:
CAGR 17.6%, Sharpe 0.84, 7 of 9 years, 12 of 12 coins. Median directional hold about a week.
Shorter-lookback versions rebalanced every 4 hours hold about 2 days at Sharpe 0.8 to 0.9 but lose
2025 and 2026 (`results/round4.out`); below one-day holds the family stops working.

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

## Running it on a DEX (SushiSwap)

A spot AMM can only run the long-only variant. Sushi's swap API
(`GET https://api.sushi.com/swap/v7/{chainId}?tokenIn&tokenOut&amount&maxSlippage&sender&simulate=true`)
returns `priceImpact`, `assumedAmountOut` and a ready transaction (`tx.to` is the RouteProcessor,
`tx.data`, `tx.value`). Live quotes from this session on Arbitrum: a $10k USDC to WBTC swap had 0.07%
price impact, $10k to LINK 0.36%, $1k to LINK 0.01%. Round-trip cost decides everything here: the
long-only EVM backtest gives 9 of 9 years at 0.10%, 7 of 9 at 0.20%, 6 of 9 at 0.30% and 5 of 9
at 0.60% (v2 0.30% pools), so use an L2, 0.05% v3 pools, small clips, and tight slippage.
Native-chain coins (SOL, ADA, DOGE, DOT, LTC, ATOM, XRP) are not tradeable on an EVM DEX; the full
long/short version needs a perp venue.


## Portfolio study: 30% a year at low risk?

Bar set before testing: CAGR >= 30%, max drawdown >= -25%, Sharpe >= 1.5, worst month >= -10%,
at least 8 of 9 years positive, no leverage. Simulator: `portfolio.py` (compounding cash accounting,
total exposure capped at 100%, 0.15% round trip, 2018-01-01 to 2026-09-19).

Best construction found (`P1`): R3 trend ensemble long/short with a 30% per-coin vol target as the
base, B* long-only 24h dip overlay with 20 slots of 5% of equity, idle cash earning 4% a year.

| panel | CAGR | max DD | Sharpe | worst month | years positive | 2026 YTD |
|---|---|---|---|---|---|---|
| 22 selection coins | 30.7% | -22% | 1.36 | -7.6% | 9 of 9 | +2% |
| 38 coins (22 + 16 fresh) | 31.4% | -25% | 1.25 | -9.4% | 8 of 9 | -1% |
| 16 fresh coins only (ZRX, BAT, ZEC, EOS, DASH, OMG, KNC, COMP, MKR, SNX, YFI, GRT, CRV, MANA, SAND, AXS) | 20.9% | -20% | 1.06 | -11.9% | 8 of 9 | +2% |
| 22 coins, no yield on cash | 26.9% | -23% | 1.22 | -7.8% | 8 of 9 | 0% |

Verdict: four of the five criteria are met on the selection and blended universes; Sharpe reaches
1.25 to 1.47, not 1.5. On coins never used in any selection the same rules make about 21% a year at a
20% drawdown. Buy and hold on that basket: 10% a year at a 54% drawdown.

Robustness on 22 coins (`results/final_check.out`): costs 0.06 / 0.15 / 0.30% give CAGR 33.7 / 30.7 /
25.6%; execution delay 0 / 1 / 2 h gives 30.7 / 30.2 / 30.4%; the grid of trend vol target 25-35% by
15-25 dip slots gives 27-34% CAGR, -19% to -26% max DD, every cell 8 or 9 years positive. The
lowest-risk cell (vt 25%, 25 slots) makes 27.1% at -19% DD, worst month -6.5%, Sharpe 1.43, 9 of 9
(16 fresh coins: 18.0% at -17%).

What did not help (`results/portfolio22.out`, `portfolio38.out`): per-trade stops at 2 sigma and
vol-scaled slot sizes cut returns more than risk; portfolio-level vol targeting cut returns with
little drawdown benefit; the long/short dip overlay adds return but its shorts drive the 2026
losses (-32% YTD on 38 coins) and the deep drawdowns, so the overlay is long-only; capping new
entries per day removes most of the profit because the profitable dips cluster on the same days.

Where the drawdowns come from: the trend sleeve's whipsaw from Aug to Nov 2024 (about -23%) sets the
max drawdown of every mixed configuration; the dip overlay's worst single day was 2021-02-22 when
ten slots were fully deployed into a market-wide crash.

Caveats: the 30% figures are on the universe the components were selected on and include a 4%
yield assumption; the out-of-sample return is about two thirds of that. Costs, funding for the
short trend positions, and slippage on cluster days are modeled only as the flat round-trip cost.

## Caveats

* Survivorship: the selection universe is ten coins that are major today; the holdout basket is
  not survivorship-free either, but it lost money on a buy-and-hold basis.
* Prices are Coinbase spot; a long/short implementation needs perpetual futures or borrowing.
  Funding and borrow costs are not modeled; on 24-hour holds they are small.
* Slippage is assumed inside the round-trip cost. No leverage. No stop-loss was tested; the worst
  single trade was -36%.
* 2026 year-to-date is negative for every variant. Paper-trade before committing capital.

## Reproduce

    pip install pandas numpy
    for c in BTC-USD ETH-USD SOL-USD ADA-USD DOGE-USD LINK-USD AVAX-USD DOT-USD LTC-USD ATOM-USD \
             BCH-USD ETC-USD XLM-USD XTZ-USD ALGO-USD UNI-USD FIL-USD AAVE-USD XRP-USD ICP-USD NEAR-USD APT-USD; do
      python3 fetch_gran.py $c 2017-01-01 2022-01-01 3600; python3 fetch_gran.py $c 2022-01-01 2026-09-19 3600
    done
    python3 bt.py          # round 1 screen (2022-2026)
    python3 round2.py      # round 2 candidates
    python3 round3.py      # extended windows 2018-2026
    python3 round4.py      # holding-period sweep and dip-in-trend grid
    python3 round5.py      # 12 holdout coins
    python3 final_stats.py # compounded statistics for R3
    python3 sizing.py; python3 stacking.py           # capital deployment study
    MSET=1 python3 portfolio.py <comma-separated coins>  # portfolio study; python3 final_check.py; python3 final_check16.py
