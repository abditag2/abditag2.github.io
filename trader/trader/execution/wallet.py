"""Wallet loading. The key never touches the repo: TRADER_WALLET_PRIVATE_KEY (hex) or TRADER_KEYSTORE + TRADER_KEYSTORE_PASSWORD."""
import os, json

def load_account(w3):
    key = os.environ.get("TRADER_WALLET_PRIVATE_KEY")
    if key:
        return w3.eth.account.from_key(key)
    ks = os.environ.get("TRADER_KEYSTORE"); pw = os.environ.get("TRADER_KEYSTORE_PASSWORD")
    if ks and pw is not None:
        with open(ks) as f:
            return w3.eth.account.from_key(w3.eth.account.decrypt(json.load(f), pw))
    raise RuntimeError("no wallet: set TRADER_WALLET_PRIVATE_KEY or TRADER_KEYSTORE + TRADER_KEYSTORE_PASSWORD")
