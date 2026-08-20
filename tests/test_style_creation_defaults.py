import unittest
import tempfile
from pathlib import Path

import matplotlib as mpl

from mygui.figuremodify.matplotlib_adapter import (
    available_colormap_names,
    available_font_families,
    available_marker_definitions,
    available_style_names,
    copy_colormap,
    matplotlib_style_context,
)
from mygui.figuremodify.style_base.creation_defaults import (
    MATPLOTLIB_STYLE_PALETTE_SOURCE,
    resolve_component_creation_defaults,
    resolve_style_palette,
)


class StyleCreationDefaultsTests(unittest.TestCase):
    def test_representative_styles_use_effective_artist_defaults(self):
        classic = resolve_component_creation_defaults("classic")
        five_thirty_eight = resolve_component_creation_defaults(
            "fivethirtyeight"
        )
        dark = resolve_component_creation_defaults("dark_background")
        poster = resolve_component_creation_defaults(
            "seaborn-v0_8-poster"
        )

        self.assertEqual(classic.line.linewidth, 1.0)
        self.assertEqual(classic.scatter.size, 20.0)
        self.assertEqual(classic.text.fontsize, 12.0)
        self.assertEqual(classic.chart_palette.colors[0], "#0000FF")

        self.assertEqual(five_thirty_eight.line.linewidth, 4.0)
        self.assertEqual(five_thirty_eight.text.fontsize, 14.0)
        self.assertEqual(
            five_thirty_eight.chart_palette.colors[0],
            "#008FD5",
        )

        self.assertEqual(dark.text.color, "#FFFFFF")
        self.assertEqual(dark.chart_palette.colors[0], "#8DD3C7")
        self.assertEqual(dark.in_axes.facecolor, "#000000")
        self.assertEqual(dark.in_axes.edgecolor, "#FFFFFF")
        self.assertEqual(five_thirty_eight.in_axes.linewidth, 3.0)
        self.assertEqual(
            five_thirty_eight.in_axes.image_interpolation,
            "bilinear",
        )
        self.assertAlmostEqual(poster.scatter.size, 125.44)

    def test_style_palette_identity_is_deterministic_and_tagged(self):
        first = resolve_component_creation_defaults("ggplot")
        second = resolve_component_creation_defaults("ggplot")
        palette_only = resolve_style_palette("ggplot")

        self.assertEqual(first.chart_palette, second.chart_palette)
        self.assertEqual(first.chart_palette, palette_only)
        self.assertEqual(
            first.chart_palette.source,
            MATPLOTLIB_STYLE_PALETTE_SOURCE,
        )
        self.assertTrue(
            first.chart_palette.id.startswith("matplotlib-style:")
        )

    def test_resolver_restores_global_rcparams(self):
        keys = (
            "axes.prop_cycle",
            "lines.linewidth",
            "lines.markersize",
            "font.family",
            "font.size",
            "text.color",
            "text.usetex",
        )
        before = {key: mpl.rcParams[key] for key in keys}

        resolve_component_creation_defaults("dark_background")

        after = {key: mpl.rcParams[key] for key in keys}
        self.assertEqual(after, before)

    def test_adapter_restores_nested_and_exception_style_contexts(self):
        keys = ("axes.facecolor", "lines.linewidth", "text.color")
        before = {key: mpl.rcParams[key] for key in keys}

        with matplotlib_style_context("ggplot"):
            outer = {key: mpl.rcParams[key] for key in keys}
            with self.assertRaisesRegex(RuntimeError, "injected"):
                with matplotlib_style_context("dark_background"):
                    self.assertNotEqual(
                        mpl.rcParams["axes.facecolor"],
                        outer["axes.facecolor"],
                    )
                    raise RuntimeError("injected")
            self.assertEqual(
                {key: mpl.rcParams[key] for key in keys},
                outer,
            )

        self.assertEqual(
            {key: mpl.rcParams[key] for key in keys},
            before,
        )

    def test_adapter_catalogs_are_immutable_and_resolvable(self):
        self.assertIn("ggplot", available_style_names())
        self.assertIn("viridis", available_colormap_names())
        self.assertIn("o", {value for value, _label in available_marker_definitions()})
        fonts = available_font_families()
        self.assertIsInstance(fonts, tuple)
        self.assertEqual(fonts, tuple(sorted(set(fonts))))
        first = copy_colormap("viridis")
        second = copy_colormap("viridis")
        self.assertIsNot(first, second)
        self.assertEqual(first.name, "viridis")

    def test_custom_compound_cycle_consumes_only_color_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compound.mplstyle"
            path.write_text(
                "\n".join(
                    (
                        "axes.prop_cycle: "
                        "cycler('color', ['red', 'blue']) + "
                        "cycler('linestyle', ['-', '--'])",
                        "lines.linewidth: 3.25",
                    )
                ),
                encoding="utf-8",
            )

            defaults = resolve_component_creation_defaults(str(path))

        self.assertEqual(
            defaults.chart_palette.colors,
            ("#FF0000", "#0000FF"),
        )
        self.assertEqual(defaults.line.linewidth, 3.25)


if __name__ == "__main__":
    unittest.main()
