"""UI-only Style gallery labels. Matplotlib style keys stay unchanged."""

from __future__ import annotations

HIDDEN_STYLE_NAMES = frozenset(
    {
        "_classic_test_patch",
        "_mpl-gallery",
        "_mpl-gallery-nogrid",
    }
)

STYLE_TOOLBAR_LABELS = {
    "default": "Default",
    "classic": "Classic",
    "seaborn-v0_8": "Seaborn",
    "ggplot": "ggplot",
    "grayscale": "Grayscale",
    "dark_background": "Dark Background",
    "tableau-colorblind10": "Colorblind 10",
    "Solarize_Light2": "Solarize Light",
    "bmh": "BMH",
    "fast": "Fast",
    "fivethirtyeight": "FiveThirtyEight",
    "seaborn-v0_8-bright": "Bright",
    "seaborn-v0_8-colorblind": "Colorblind",
    "seaborn-v0_8-dark": "Dark",
    "seaborn-v0_8-dark-palette": "Dark Palette",
    "seaborn-v0_8-darkgrid": "Dark Grid",
    "seaborn-v0_8-deep": "Deep",
    "seaborn-v0_8-muted": "Muted",
    "seaborn-v0_8-notebook": "Notebook",
    "seaborn-v0_8-paper": "Paper",
    "seaborn-v0_8-pastel": "Pastel",
    "seaborn-v0_8-poster": "Poster",
    "seaborn-v0_8-talk": "Talk",
    "seaborn-v0_8-ticks": "Ticks",
    "seaborn-v0_8-white": "White",
    "seaborn-v0_8-whitegrid": "White Grid",
}

LAYOUT_BUTTON_MIN_WIDTH = 112


def style_toolbar_label(style_name: str) -> str:
    """Return the compact gallery label for a Matplotlib style key."""

    mapped = STYLE_TOOLBAR_LABELS.get(style_name)
    if mapped is not None:
        return mapped
    text = str(style_name).replace("seaborn-v0_8-", "").replace("seaborn-v0_8", "Seaborn")
    text = text.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in text.split()) or str(style_name)
