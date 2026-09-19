import os, pathlib, yaml
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = pathlib.Path(os.environ.get("TRADER_STATE_DIR", ROOT / "state"))

def load_yaml(name):
    with open(ROOT / "config" / name) as f:
        return yaml.safe_load(f)

def strategy_config(name):
    cfgs = load_yaml("strategies.yaml")
    if name not in cfgs:
        raise KeyError(f"unknown strategy '{name}'; known: {list(cfgs)}")
    cfg = dict(cfgs["_defaults"]); cfg.update(cfgs[name]); cfg["name"] = name
    return cfg

def universe(name="research22"):
    u = load_yaml("universe.yaml")
    return u[name]

def chain_config(chain="arbitrum"):
    return load_yaml("universe.yaml")["chains"][chain]
