"""Strategy registry. Every module in this package is imported so its @register decorators run;
drop a new file here (or in strategies/custom/) and reference its class name in config/strategies.yaml."""
import importlib, pkgutil, pathlib
from .base import Strategy, Context, Order, Lot, State

REGISTRY = {}
_DISCOVERED = False

def register(name):
    def deco(cls):
        REGISTRY[name] = cls; cls.plugin_name = name; return cls
    return deco

def _discover():
    global _DISCOVERED
    if _DISCOVERED: return
    _DISCOVERED = True
    pkg_dir = pathlib.Path(__file__).parent
    for m in pkgutil.iter_modules([str(pkg_dir)]):
        if m.name not in ("base", "__init__"): importlib.import_module(f"{__name__}.{m.name}")
    custom = pkg_dir / "custom"
    if custom.is_dir():
        for m in pkgutil.iter_modules([str(custom)]): importlib.import_module(f"{__name__}.custom.{m.name}")

def load_strategy(cfg):
    """cfg: dict from config.strategy_config(name); its `class` key selects the plugin (default: portfolio)."""
    _discover()
    cls_name = cfg.get("class", "portfolio")
    if cls_name not in REGISTRY: raise KeyError(f"no strategy class '{cls_name}'; registered: {sorted(REGISTRY)}")
    return REGISTRY[cls_name](cfg)

def available():
    _discover()
    return dict(REGISTRY)
