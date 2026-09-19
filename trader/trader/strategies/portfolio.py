"""P1: trend base + 24h dip overlay (the mixed portfolio from the research). Also the components on their own."""
from . import register
from .base import Strategy
from .sleeves import TrendBase, DipOverlay

@register("portfolio")
class PortfolioStrategy(Strategy):
    def __init__(self, cfg):
        super().__init__(cfg)
        self.base = TrendBase(cfg.get("base_vol_target", 0.30), cfg.get("base_rebalance_hour", 23), cfg.get("base_enabled", True))
        self.overlay = DipOverlay(cfg.get("overlay_slots", 20), cfg.get("dip_sigma", 1.5), cfg.get("hold_hours", 24),
                                  cfg.get("overlay_long_only", True), cfg.get("exposure_cap", 1.0), cfg.get("overlay_enabled", True))

    def decide(self, ctx):
        self.overlay.exits(ctx)        # free slots and cash first
        self.base.rebalance(ctx)       # once a day
        self.overlay.entries(ctx)      # then new dips
