from dataclasses import dataclass

@dataclass
class Fill:
    symbol: str
    side: str
    qty: float          # base units of the coin, > 0
    price: float        # quote per coin actually achieved
    notional: float     # qty * price
    fee: float          # quote units (explicit fee; on-chain the pool fee is inside the price)
    ref: str            # "paper" | tx hash | "dry-run"

class ExecutionError(Exception): pass
