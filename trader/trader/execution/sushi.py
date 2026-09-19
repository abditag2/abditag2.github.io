"""On-chain executor for SushiSwap's RouteProcessor via the Sushi swap API (long-only spot).
Flow per order: quote -> guards (route whitelist, price impact, deviation from reference, gas) -> allowance -> sign -> send -> parse fill."""
import os, json, time, urllib.request, urllib.parse
from web3 import Web3
from .base import Fill, ExecutionError
from .wallet import load_account

ERC20_ABI = json.loads('''[
 {"constant":true,"inputs":[{"name":"o","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"type":"function"},
 {"constant":true,"inputs":[{"name":"o","type":"address"},{"name":"s","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"type":"function"},
 {"constant":false,"inputs":[{"name":"s","type":"address"},{"name":"v","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"type":"function"},
 {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
 {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"}]''')
TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()
NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"   # the Sushi API's sentinel for the chain's native coin (ETH on Arbitrum)

def is_native(token_cfg):
    return bool(token_cfg.get("native")) or token_cfg["address"].lower() == NATIVE.lower()

class SushiExecutor:
    can_short = False

    def __init__(self, chain_cfg, token_map, rpc_url=None, dry_run=False, api_key=None, account=None, dry_cash=10_000.0):
        self.cfg = chain_cfg; self.chain_id = int(chain_cfg["chain_id"]); self.tokens = token_map
        self._sim = {chain_cfg["quote"]["symbol"]: float(dry_cash)}    # dry-run balances: real quotes, simulated fills
        self.quote_cfg = chain_cfg["quote"]; self.quote = self.quote_cfg["symbol"]
        self.dry_run = dry_run; self.api_key = api_key or os.environ.get("SUSHI_API_KEY")
        self.w3 = Web3(Web3.HTTPProvider(rpc_url or os.environ.get(chain_cfg.get("rpc_url_env", "RPC_URL"), ""), request_kwargs={"timeout": 30}))
        self.account = account or (load_account(self.w3) if not dry_run or os.environ.get("TRADER_WALLET_PRIVATE_KEY") else None)
        self.address = self.account.address if self.account else "0x0000000000000000000000000000000000000001"
        self.whitelist = {a.lower() for a in chain_cfg.get("route_processors", [])}

    # ---- chain reads ----
    def _erc20(self, address):
        return self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)

    def balances(self):
        if self.dry_run: return dict(self._sim)
        out = {self.quote: self._erc20(self.quote_cfg["address"]).functions.balanceOf(self.address).call() / 10 ** self.quote_cfg["decimals"]}
        for sym, t in self.tokens.items():
            if is_native(t):   # tradeable native balance excludes the gas reserve
                out[sym] = max(0.0, self.w3.eth.get_balance(self.address) / 1e18 - self.cfg.get("min_native_balance", 0.002))
            else:
                out[sym] = self._erc20(t["address"]).functions.balanceOf(self.address).call() / 10 ** t["decimals"]
        return out

    def native_balance(self):
        return self.w3.eth.get_balance(self.address) / 1e18

    def verify_tokens(self):
        """Read symbol() and decimals() on-chain for every configured token; raises on mismatch."""
        problems = []
        for sym, t in list(self.tokens.items()) + [("QUOTE", self.quote_cfg)]:
            if is_native(t): continue
            c = self._erc20(t["address"]); s = c.functions.symbol().call(); d = c.functions.decimals().call()
            if d != t["decimals"] or s.upper() != t["symbol"].upper(): problems.append(f"{sym}: on-chain {s}/{d} vs config {t['symbol']}/{t['decimals']}")
        if problems: raise ExecutionError("token config mismatch: " + "; ".join(problems))
        return True

    # ---- Sushi API ----
    def quote_swap(self, token_in, token_out, amount_units, simulate=False):
        q = {"tokenIn": token_in, "tokenOut": token_out, "amount": str(int(amount_units)), "maxSlippage": self.cfg.get("max_slippage", 0.003), "sender": self.address}
        if simulate: q["simulate"] = "true"
        if self.api_key: q["apiKey"] = self.api_key
        url = f"https://api.sushi.com/swap/v7/{self.chain_id}?" + urllib.parse.urlencode(q)
        req = urllib.request.Request(url, headers={"User-Agent": "trader/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    # ---- execution ----
    def market_order(self, symbol, side, notional, ref_price, ts=None):
        t = self.tokens[symbol]; qd, td = self.quote_cfg["decimals"], t["decimals"]
        if side == "buy":
            token_in, token_out, dec_in, dec_out = self.quote_cfg["address"], t["address"], qd, td
            amount = int(notional * 10 ** qd)
        else:
            token_in, token_out, dec_in, dec_out = t["address"], self.quote_cfg["address"], td, qd
            qty = notional / ref_price
            qty = min(qty, self.balances().get(symbol, 0.0))
            amount = int(qty * 10 ** td)
        if amount <= 0: raise ExecutionError(f"{symbol} {side}: zero amount")
        q = self.quote_swap(token_in, token_out, amount, simulate=not self.dry_run)
        if q.get("status") != "Success": raise ExecutionError(f"{symbol} {side}: quote status {q.get('status')}")
        impact = float(q.get("priceImpact") or 0.0)
        if impact > self.cfg.get("max_price_impact", 0.003): raise ExecutionError(f"{symbol} {side}: price impact {impact:.3%} above cap")
        amt_in = int(q["amountIn"]) / 10 ** dec_in; amt_out = int(q["assumedAmountOut"]) / 10 ** dec_out
        implied = amt_in / amt_out if side == "buy" else amt_out / amt_in      # quote per coin
        dev = implied / ref_price - 1
        if abs(dev) > self.cfg.get("max_ref_deviation", 0.006): raise ExecutionError(f"{symbol} {side}: quote {implied:.4f} deviates {dev:+.2%} from reference {ref_price:.4f}")
        tx = q["tx"]
        if tx["to"].lower() not in self.whitelist: raise ExecutionError(f"{symbol} {side}: route processor {tx['to']} not whitelisted")
        if self.dry_run:
            qty = amt_out if side == "buy" else amt_in
            if side == "buy": self._sim[self.quote] -= amt_in; self._sim[symbol] = self._sim.get(symbol, 0.0) + qty
            else: self._sim[self.quote] += amt_out; self._sim[symbol] = self._sim.get(symbol, 0.0) - qty
            return Fill(symbol, side, qty, implied, qty * implied, 0.0, "dry-run")
        gas_price = self.w3.eth.gas_price
        if gas_price / 1e9 > self.cfg.get("max_gas_gwei", 2.0): raise ExecutionError(f"gas price {gas_price/1e9:.2f} gwei above cap")
        native_in, native_out = is_native(t) and side == "sell", is_native(t) and side == "buy"
        if not native_in: self._ensure_allowance(token_in, tx["to"], amount, gas_price)
        eth_before = self.w3.eth.get_balance(self.address)
        txn = {"from": self.address, "to": Web3.to_checksum_address(tx["to"]), "data": tx["data"], "value": int(tx.get("value") or 0),
               "nonce": self.w3.eth.get_transaction_count(self.address), "chainId": self.chain_id, "gasPrice": gas_price}
        txn["gas"] = int(int(tx.get("gas") or self.w3.eth.estimate_gas(txn)) * 1.2)
        signed = self.account.sign_transaction(txn)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        if rcpt["status"] != 1: raise ExecutionError(f"{symbol} {side}: tx {h.hex()} reverted")
        gas_wei = rcpt["gasUsed"] * rcpt.get("effectiveGasPrice", gas_price)
        if native_out:   # received native coin: balance delta plus the gas that was paid
            received = (self.w3.eth.get_balance(self.address) - eth_before + gas_wei) / 1e18
        else:
            received = self._received(rcpt, token_out) / 10 ** dec_out
        qty = received if side == "buy" else amt_in
        price = (amt_in / received) if side == "buy" else (received / amt_in)
        gas_cost_eth = gas_wei / 1e18
        return Fill(symbol, side, qty, price, qty * price, 0.0, f"{h.hex()} gas={gas_cost_eth:.6f}ETH impact={impact:.4f}")

    def _ensure_allowance(self, token, spender, amount, gas_price):
        c = self._erc20(token)
        if c.functions.allowance(self.address, Web3.to_checksum_address(spender)).call() >= amount: return
        txn = c.functions.approve(Web3.to_checksum_address(spender), int(amount)).build_transaction(
            {"from": self.address, "nonce": self.w3.eth.get_transaction_count(self.address), "chainId": self.chain_id, "gasPrice": gas_price})
        signed = self.account.sign_transaction(txn)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        rcpt = self.w3.eth.wait_for_transaction_receipt(h, timeout=180)
        if rcpt["status"] != 1: raise ExecutionError("approve reverted")

    def _received(self, rcpt, token_out):
        total = 0; me = self.address.lower()
        for log in rcpt["logs"]:
            if log["address"].lower() != token_out.lower() or not log["topics"]: continue
            if log["topics"][0].hex().lower().removeprefix("0x") != TRANSFER_TOPIC.lower().removeprefix("0x"): continue
            to = "0x" + log["topics"][2].hex()[-40:]
            if to.lower() == me: total += int(log["data"].hex(), 16) if hasattr(log["data"], "hex") else int(log["data"], 16)
        if total == 0: raise ExecutionError("no Transfer to wallet found in receipt")
        return total
