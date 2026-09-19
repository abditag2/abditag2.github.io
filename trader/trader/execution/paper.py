"""Simulated executor: fills at the reference price with fee and slippage; optional shorts; optional yield on idle cash."""
from .base import Fill, ExecutionError

class PaperExecutor:
    def __init__(self, cash=10_000.0, fee_rate=0.0005, slippage=0.00025, can_short=True, quote="USDC"):
        self.quote = quote; self.fee_rate = fee_rate; self.slippage = slippage; self.can_short = can_short
        self._bal = {quote: float(cash)}

    def balances(self):
        return dict(self._bal)

    def restore(self, balances):
        self._bal = {k: float(v) for k, v in balances.items()}

    def accrue_yield(self, apy, hours=1.0):
        c = self._bal[self.quote]
        if c > 0 and apy > 0:
            self._bal[self.quote] = c * (1 + apy) ** (hours / 8760)

    def market_order(self, symbol, side, notional, ref_price, ts=None):
        if notional <= 0 or ref_price <= 0: raise ExecutionError("bad order")
        if side == "buy":
            price = ref_price * (1 + self.slippage); qty = notional / price; fee = notional * self.fee_rate
            if self._bal[self.quote] < notional + fee - 1e-9: raise ExecutionError(f"insufficient cash for {symbol} buy {notional:.2f}")
            self._bal[self.quote] -= notional + fee; self._bal[symbol] = self._bal.get(symbol, 0.0) + qty
        else:   # sells are sized in coins (notional / reference price); slippage reduces the proceeds
            price = ref_price * (1 - self.slippage); qty = notional / ref_price
            have = self._bal.get(symbol, 0.0)
            if have - qty < -1e-12 and not self.can_short:
                qty = max(have, 0.0)
                if qty <= 0: raise ExecutionError(f"nothing to sell for {symbol}")
            proceeds = qty * price; fee = proceeds * self.fee_rate
            self._bal[self.quote] += proceeds - fee; self._bal[symbol] = have - qty
            return Fill(symbol, side, qty, price, proceeds, fee, "paper")
        return Fill(symbol, side, qty, price, qty * price, fee, "paper")
