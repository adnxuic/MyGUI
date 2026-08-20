"""Fixture: an authorized configuration-owning Service may write rcParams."""
import matplotlib as mpl


class TexConfigService:
    def apply(self):
        mpl.rcParams["text.usetex"] = True  # legal: Service owns Matplotlib config
