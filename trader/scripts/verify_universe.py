"""Read symbol() and decimals() on-chain for every configured token (needs RPC_URL). Run before the first live session."""
import argparse
from common import *
from trader.execution.sushi import SushiExecutor
ap = argparse.ArgumentParser(); ap.add_argument("--chain", default="arbitrum"); a = ap.parse_args()
chain = config.chain_config(a.chain); ex = SushiExecutor(chain, chain["tokens"], dry_run=True)
ex.verify_tokens(); print("all token addresses match their configured symbol and decimals")
