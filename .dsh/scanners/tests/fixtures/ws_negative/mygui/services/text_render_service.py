"""Negative fixture: the Matplotlib configuration owner may write rcParams."""
import matplotlib as mpl


def apply_tex_config(enabled):
    mpl.rcParams["text.usetex"] = bool(enabled)
