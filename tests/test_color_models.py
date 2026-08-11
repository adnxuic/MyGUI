import unittest

from mygui.figuremodify.style_base.color_models import (
    ColorCycleState,
    ColorSelection,
    PaletteDefinition,
    PaletteSource,
    all_single_colors,
    builtin_palettes,
    normalize_color,
)


class ColorModelTests(unittest.TestCase):
    def test_palette_source_enum_preserves_schema_wire_value(self):
        palette = PaletteDefinition(
            "wire",
            "Wire",
            ("red", "blue"),
            source=PaletteSource.MATPLOTLIB_STYLE,
        )
        self.assertIs(palette.source, PaletteSource.MATPLOTLIB_STYLE)
        self.assertEqual(palette.to_dict()["source"], "matplotlib-style")

    def test_normalize_named_hex_and_rgba_colors(self):
        self.assertEqual(normalize_color("tab:blue"), "#1F77B4")
        self.assertEqual(normalize_color("#abc"), "#AABBCC")
        self.assertEqual(normalize_color((1.0, 0.0, 0.0, 0.5)), "#FF000080")
        self.assertEqual(normalize_color("#01020300"), "#01020300")

    def test_invalid_color_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid color"):
            normalize_color("definitely-not-a-color")

    def test_builtin_library_preserves_counts(self):
        self.assertEqual(len(all_single_colors()), 296)
        self.assertEqual(len(builtin_palettes()), 77)

    def test_peek_does_not_advance_and_commit_does(self):
        palette = PaletteDefinition("test", "Test", ("red", "green", "blue"))
        state = ColorCycleState(palette)
        first = state.peek()
        self.assertEqual(first.color, "#FF0000")
        self.assertEqual(state.peek(), first)
        state.commit(first)
        self.assertEqual(state.peek().color, "#008000")

    def test_custom_single_color_does_not_replace_active_palette(self):
        palette = PaletteDefinition("test", "Test", ("red", "blue"))
        state = ColorCycleState(palette, 1)
        state.commit(ColorSelection("#123456"))
        self.assertIs(state.active_palette, palette)
        self.assertEqual(state.peek().color, "#0000FF")

    def test_batch_commit_uses_object_count_modulo_palette_size(self):
        palette = PaletteDefinition("test", "Test", ("red", "green", "blue"))
        state = ColorCycleState()
        state.commit_palette_for_count(palette, 5)
        self.assertEqual(state.next_index, 2)
        self.assertEqual(state.peek().color, "#0000FF")

    def test_cycle_snapshot_roundtrip_includes_palette_snapshot(self):
        palette = PaletteDefinition(
            "custom:stable", "Deleted later", ("#112233", "#445566"), source="custom"
        )
        restored = ColorCycleState.from_dict(ColorCycleState(palette, 1).to_dict())
        self.assertEqual(restored.active_palette.id, "custom:stable")
        self.assertEqual(restored.active_palette.colors, ("#112233", "#445566"))
        self.assertEqual(restored.next_index, 1)


if __name__ == "__main__":
    unittest.main()
