# trader

Infrastructure to run the strategies from `../research/crypto-strategy-screen` in three modes with one code path:

| mode | data | fills | shorts | use |
|---|---|---|---|---|
| **backtest** | stored hourly candles, replayed | `PaperExecutor` (fee + slippage) | yes (simulated perps) | research parity, parameter studies |
| **paper** | live Coinbase candles, one step per hour | `PaperExecutor` | yes | live rehearsal, weeks of forward test |
| **live** | live Coinbase candles | `SushiExecutor` (on-chain, Arbitrum) | no (spot AMM) | real money, long-only |

The strategy object never knows which mode it is in. It receives signals, prices, its own books and the account, and returns orders.
The engine nets orders per coin, executes through whichever executor is plugged in, books fills into a SQLite ledger, and marks equity every hour.
The dashboard reads those ledgers.

```
trader/
  trader/data/store.py        SQLite bar store + Coinbase candle feed (incremental update)
  trader/signals.py           trend ensemble, realized vol, 24h dip z-score  (identical to the research code; tests prove it)
  trader/strategy.py          P1 = trend base (daily, vol-targeted) + 24h dip overlay (hourly, K slots)  -> orders
  trader/engine.py            step(): decide -> net -> execute -> book -> mark;  backtest() replay;  live_step() with risk checks
  trader/execution/paper.py   simulated fills, shorts, yield on idle cash
  trader/execution/sushi.py   on-chain: Sushi API quote -> guards -> allowance -> sign -> send -> fill from receipt
  trader/execution/wallet.py  key from TRADER_WALLET_PRIVATE_KEY or an encrypted keystore file
  trader/ledger.py            runs, fills, lots, base positions, equity, events (SQLite)
  trader/metrics.py           CAGR, max drawdown, Sharpe, worst month, years positive, hit rate, expectancy
  trader/risk.py              stale-data, daily-loss and drawdown halts
  dashboard/app.py            Streamlit: compare runs, equity, drawdown, yearly returns, trades, live health
  scripts/                    backtest.py, run.py (paper|live), update_data.py, import_research_data.py, quote_check.py, verify_universe.py
  config/strategies.yaml      strategy parameters;  config/universe.yaml  coins, on-chain tokens, chain guards
  deploy/                     Dockerfile, docker-compose.yml, systemd units, .env.example
  tests/                      signals == research, paper executor costs, engine books == holdings
```

## Quick start (simulation)

```bash
cd trader && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python scripts/update_data.py --universe research22 --days 400      # or: scripts/import_research_data.py --dir <research json dir>
python scripts/backtest.py --strategy p1 --universe research22 --start 2023-01-01 --end 2026-09-19
python scripts/run.py --mode paper --strategy p1 --universe research22 --run-id p1_paper --once   # one hourly step
streamlit run dashboard/app.py                                        # http://localhost:8501
python -m pytest -q tests
```

Strategies (`config/strategies.yaml`): `p1` the mixed portfolio from the 30%-return study (trend base at a 30% vol target,
20 overlay slots of 5%, 4% yield on idle cash in simulation), `p1_longflat` the same for venues without shorts,
`bstar_long` the 24h dip overlay alone, `r3` the trend ensemble alone.

## Writing a new strategy

Strategies are plugins. A strategy is a class with `signals(panel)` (vectorized precomputation over the whole hourly panel, run once per
backtest or per live step) and `decide(ctx)` (called every completed hour). It expresses intent through the `Context`:

```python
# trader/strategies/custom/my_strategy.py   (this folder is discovered automatically)
from trader.strategies import register
from trader.strategies.base import Strategy

@register("breakout_20d")
class Breakout(Strategy):
    warmup_hours = 24 * 30                                   # history needed before the first decision

    def signals(self, panel):                                # any dict of DataFrames indexed like panel["close"]
        return {"high20": panel["high"].rolling(24 * 20).max().shift(1), "close": panel["close"]}

    def decide(self, ctx):
        # ctx.symbols()            coins with a price this hour       ctx.value("high20", s)   this hour's signal value
        # ctx.equity, ctx.cash     account                            ctx.hour, ctx.ts         time (UTC hour, unix seconds)
        # ctx.can_short            venue capability                   ctx.deployed()           |positions| in quote units
        for s in ctx.symbols():
            if not ctx.has_lot(s) and ctx.value("close", s) > ctx.value("high20", s):
                ctx.open_lot(s, ctx.equity * 0.05, side=1, reason="20d breakout")     # discrete trade, one lot per coin
            elif ctx.has_lot(s) and ctx.lot_age_hours(s) >= 48:
                ctx.close_lot(s, "time exit")
        # or manage a target-weight book instead:  ctx.target_base(s, signed_notional, "rebalance")
```

Reference it from `config/strategies.yaml` and every script, the engine and the dashboard pick it up:

```yaml
breakout_20d:
  class: breakout_20d
  min_trade_notional: 10
```

```bash
python scripts/backtest.py --strategy breakout_20d --universe research22 --start 2023-01-01 --end 2026-09-19
python scripts/run.py --mode paper --strategy breakout_20d --universe research22 --run-id breakout_paper
```

Two books are available and can be mixed: `target_base` keeps a signed target position per coin (rebalancing strategies), `open_lot`/`close_lot`
run discrete trades with an entry time (event strategies). Both respect `min_trade_notional`, the cash on hand, the exposure cap and whether the venue can
short. `trader/strategies/sleeves.py` holds the validated pieces (`TrendBase`, `DipOverlay`) so a new strategy can compose them, as
`trader/strategies/portfolio.py` does. `trader/strategies/examples.py` has two complete small plugins (`sma_cross`, `xs_momentum`). Orders for the
same coin in the same hour are netted into one trade by the engine, and fills are reconciled against holdings, so a strategy never has to think
about execution. Tests in `tests/test_plugins.py` show how to run a plugin through the engine in a few lines.

## Engine validation against the research

Same rules, same costs (0.05% fee + 0.025% slippage per side, 4% yield on idle cash), 22 coins, 2018-01-01 to 2026-09-19:

| run | CAGR | max DD | Sharpe | worst month | years + | avg exposure | trades | hit rate |
|---|---|---|---|---|---|---|---|---|
| engine `p1` long/short (`scripts/backtest.py`) | 34.4% | -21% (2024-08-05..2024-11-06) | 1.46 | -7.4% | 9/9 | 26% | 2186 | 56% |
| research `portfolio.py` M9 (same spec) | 30.7% | -22% (2024-08-05..2024-11-06) | 1.36 | -7.6% | 9/9 | 25% | - | 54% |

| engine `p1` `--no-short` (spot venue: base long/flat) | 31.2% | -19% | 1.58 | -9.1% | 6/9 | 13% | 2187 | 56% |
| engine `bstar_long` (overlay only, 10 slots of 10%) | 22.8% | -24% | 1.18 | -12.5% | 7/9 | 6% | 2048 | 56% |
| engine `r3` (trend only, 40% vol target) | 26.6% | -23% | 1.13 | -7.4% | 8/9 | 30% | - | - |
| engine `p1` `--no-short` on the 5-token Arbitrum universe | 24.6% | -15% | 1.46 | -6.9% | 7/9 | 14% | 574 | 55% |

The engine nets the base and overlay orders of a coin into one trade per hour, which saves cost, so it runs a few points above the research
simulator; the yearly pattern and the drawdown windows match. `deploy/validate.sh` reproduces every row (each replay takes about three minutes).

## Live mode: plugging in a wallet

1. Create a **dedicated hot wallet** (a fresh EOA). Fund it on Arbitrum with the trading capital in USDC and about 0.01 ETH for gas. Keep everything else in a wallet the bot never sees.
2. Copy `deploy/.env.example` to `trader/.env`; set `RPC_URL`, `TRADER_WALLET_PRIVATE_KEY` (or `TRADER_KEYSTORE` + `TRADER_KEYSTORE_PASSWORD`), `TRADER_MODE=live`, `TRADER_UNIVERSE=evm_arbitrum`, `TRADER_STRATEGY=p1_longflat`.
3. `python scripts/verify_universe.py` reads `symbol()` and `decimals()` of every configured token on-chain and refuses mismatches.
4. `python scripts/quote_check.py --notional 1000` prints price impact per token and whether the RouteProcessor the API returns is whitelisted in `config/universe.yaml`.
5. Rehearse: `python scripts/run.py --mode live --strategy p1_longflat --universe evm_arbitrum --run-id live_dry --dry-run --once`. Everything runs except signing and sending; the ledger records what would have been traded.
6. Go live with `--once` under the systemd timer or with the compose loop. Start with a size where a total loss is tolerable.

Guards applied to every on-chain order: quote status must be `Success`; price impact <= 0.3%; the quoted price must be within 0.6% of the Coinbase reference;
`tx.to` must be a whitelisted RouteProcessor; gas price <= 2 gwei; exact-amount ERC-20 approvals; the fill quantity is read from the receipt, not the quote.
ETH is traded as the chain's native coin (the Sushi API rejects WETH on Arbitrum); a gas reserve (`min_native_balance`) is never sold.
A browser wallet cannot approve a transaction at 3 a.m.; the bot needs a programmatic signer. A Safe with a scoped session key is the safer upgrade path.

What a spot AMM cannot do: short. `p1_longflat` keeps the overlay and clips the trend base at zero. In the research the long/flat base was
positive in 6 of 9 years (it loses the bear years), so the on-chain version is the lower-risk, lower-return branch; the full long/short strategy needs a perp venue.

## Where to run it

The strategy acts once an hour and is not latency-sensitive, so it needs an always-on machine with a reliable clock and network, not a fast one.

* **Recommended: one small Linux VPS**, 1 to 2 vCPU, 2 GB RAM, 20 GB disk (Hetzner CX22, DigitalOcean basic droplet, AWS Lightsail, Fly.io machine: roughly USD 5 to 12 a month). Ubuntu LTS, Docker installed.
  Region: anywhere with stable connectivity; Coinbase's public API and the Sushi API are reachable worldwide, Arbitrum RPC is global. If you later add a centralized exchange executor, pick a region that exchange serves.
* **Process model**: `docker compose -f deploy/docker-compose.yml up -d` starts the hourly loop and the dashboard; or install the systemd units in `deploy/systemd/` (`trader-step.timer` fires two minutes past every hour and runs one idempotent step, `trader-dashboard.service` serves the dashboard). The timer form survives crashes better because every hour starts a fresh process.
* **State**: everything lives in `state/` (bars, ledgers). Back it up daily (`sqlite3 state/live.db ".backup ..."` or a volume snapshot).
* **Access**: the dashboard binds to `127.0.0.1:8501`. Reach it through an SSH tunnel (`ssh -L 8501:127.0.0.1:8501 user@host`) or Tailscale; do not expose it publicly.
* **Secrets**: `.env` on the server only, `chmod 600`, owned by the `trader` user. Never in git. Rotate the key by moving funds to a new wallet.
* **Monitoring**: the dashboard's run detail turns red when the last step is older than 2.5 hours. For alerts, add a cron that checks `SELECT MAX(ts) FROM equity` in the ledger and pings you.
* **Paper first**: run paper mode on the VPS for several weeks and compare its fills and equity with a backtest over the same window before funding the wallet.
* **Local laptop**: fine for backtests and the dashboard; not for paper or live, which need every hour.

Keep this directory in a **private** repository when you go live. This site repository is public.
