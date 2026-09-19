"""Pre-live health check without a wallet: Sushi quotes and price impact for the EVM universe at a given clip size."""
import argparse
from common import *
from trader.execution.sushi import SushiExecutor
ap = argparse.ArgumentParser(); ap.add_argument("--chain", default="arbitrum"); ap.add_argument("--universe", default="evm_arbitrum"); ap.add_argument("--notional", type=float, default=1000); a = ap.parse_args()
chain = config.chain_config(a.chain); tokens = {s: chain["tokens"][s] for s in config.universe(a.universe) if s in chain["tokens"]}
ex = SushiExecutor(chain, tokens, dry_run=True)
for sym, t in tokens.items():
    try:
        q = ex.quote_swap(chain["quote"]["address"], t["address"], int(a.notional * 10 ** chain["quote"]["decimals"]))
        amt_out = int(q["assumedAmountOut"]) / 10 ** t["decimals"]
        print(f"{sym:<9} buy ${a.notional:.0f}: status {q['status']}, impact {float(q.get('priceImpact') or 0):.3%}, implied price {a.notional/amt_out:.4f}, route processor {q['tx']['to']} {'OK' if q['tx']['to'].lower() in ex.whitelist else 'NOT WHITELISTED'}")
    except Exception as e:
        print(f"{sym:<9} quote failed: {e}")
