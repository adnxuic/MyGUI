"""Regression tests for the Matplotlib 3.9 property exposure contract."""

from __future__ import annotations

import math
import unittest

from mygui.figuremodify.components import (
    AxesController,
    ComponentKind,
    CONTROLLER_TYPES,
    EditorKind,
    TickGroupController,
    TickLabelGroupController,
    XAxisController,
    YAxisController,
    ComponentValidationError,
    ROLES_BY_KIND,
)
from mygui.figuremodify.components.exposure_contract import (
    MATPLOTLIB_39_EXPOSURE,
    validate_matplotlib_exposure_contracts,
)
from mygui.figuremodify.components.property_values import (
    build_formatter,
    build_locator,
    legend_anchor_value,
    legend_location_value,
    normalize_legend_anchor,
    normalize_legend_location,
    normalize_line_pattern,
    normalize_scale,
    validate_fixed_ticker_pair,
)
from mygui.widgets.fig_control_window.component_editors.base import (
    ComponentEditorBase,
)
from mygui.widgets.fig_control_window.component_editors.profiles import (
    register_production_profiles,
)
from mygui.widgets.fig_control_window.component_editors.registry import (
    EditorRegistry,
)


# The Axes palette is the only property rendered by a dedicated Section
# (``PaletteSection``) instead of an automatically generated control.
_SECTION_OWNED_PROPERTIES = frozenset(
    {
        (ComponentKind.AXES, "color_cycle"),
    }
)


class MatplotlibExposureContractTests(unittest.TestCase):
    def test_every_matplotlib_39_setter_is_classified_once(self):
        validate_matplotlib_exposure_contracts()
        for name, contract in MATPLOTLIB_39_EXPOSURE.items():
            categories = (
                contract.core,
                contract.advanced,
                contract.aliases,
                contract.derived,
                frozenset(contract.unsupported),
            )
            flattened = [key for category in categories for key in category]
            self.assertEqual(
                len(flattened),
                len(set(flattened)),
                f"{name} classifies a setter more than once",
            )
            self.assertTrue(all(contract.unsupported.values()))

    def test_all_32_profiles_expose_exact_controller_contracts(self):
        registry = EditorRegistry()
        register_production_profiles(registry)
        registry.freeze()
        expected = {
            (kind, role)
            for kind, roles in ROLES_BY_KIND.items()
            for role in roles
        }
        self.assertEqual(len(expected), 32)
        self.assertTrue(
            all(registry.profile_for(kind, role) for kind, role in expected)
        )

    def test_no_generated_property_control_falls_back_to_json_text(self):
        for (kind, role), controller_type in CONTROLLER_TYPES.items():
            for spec in controller_type.PROPERTY_SPECS:
                if (kind, spec.key) in _SECTION_OWNED_PROPERTIES:
                    continue
                with self.subTest(kind=kind, role=role, key=spec.key):
                    self.assertIsNot(spec.editor, EditorKind.JSON)
                    resolved = ComponentEditorBase._editor_kind(
                        spec,
                        spec.default,
                        key=spec.key,
                    )
                    self.assertIsNot(resolved, EditorKind.JSON)

    def test_overlapping_matplotlib_state_has_one_persistent_owner(self):
        axes = AxesController.property_specs()
        x_axis = XAxisController.property_specs()
        y_axis = YAxisController.property_specs()
        ticks = TickGroupController.property_specs()
        labels = TickLabelGroupController.property_specs()

        self.assertFalse({"xscale", "yscale"} & set(axes))
        self.assertNotIn("inverted", x_axis)
        self.assertNotIn("ticks_position", x_axis)
        self.assertNotIn("pad", ticks)
        self.assertIn("pad", labels)
        self.assertEqual(x_axis["label_position"].choices, ("bottom", "top"))
        self.assertEqual(y_axis["label_position"].choices, ("left", "right"))


class TaggedMatplotlibValueTests(unittest.TestCase):
    def test_scale_rejects_unknown_fields_and_nonfinite_values(self):
        with self.assertRaises(ComponentValidationError):
            normalize_scale(
                {"kind": "linear", "params": {"unexpected": 1}}
            )
        with self.assertRaises(ComponentValidationError):
            normalize_scale(
                {
                    "kind": "asinh",
                    "params": {
                        "linear_width": math.inf,
                        "base": 10.0,
                        "subs": [2.0, 5.0],
                    },
                }
            )

    def test_custom_line_pattern_is_closed_and_finite(self):
        value = normalize_line_pattern(
            {"kind": "custom", "offset": 1.5, "dashes": [3, 2, 1, 2]}
        )
        self.assertEqual(value["dashes"], [3.0, 2.0, 1.0, 2.0])
        with self.assertRaises(ComponentValidationError):
            normalize_line_pattern(
                {
                    "kind": "custom",
                    "offset": 0,
                    "dashes": [1, float("nan")],
                }
            )

    def test_fixed_formatter_requires_equal_fixed_locator(self):
        locator = {
            "kind": "fixed",
            "params": {"locations": [0, 1], "nbins": None},
        }
        formatter = {
            "kind": "fixed",
            "params": {"labels": ["zero", "one"]},
        }
        validate_fixed_ticker_pair(locator, formatter)
        self.assertEqual(len(build_locator(locator).locs), 2)
        self.assertEqual(list(build_formatter(formatter).seq), ["zero", "one"])
        with self.assertRaises(ComponentValidationError):
            validate_fixed_ticker_pair(
                locator,
                {"kind": "fixed", "params": {"labels": ["zero"]}},
            )

    def test_legend_location_and_anchor_round_trip_without_runtime_objects(self):
        location = normalize_legend_location((0.25, 0.75))
        anchor = normalize_legend_anchor((0.1, 0.2, 0.7, 0.6))
        self.assertEqual(legend_location_value(location), (0.25, 0.75))
        self.assertEqual(
            legend_anchor_value(anchor),
            (0.1, 0.2, 0.7, 0.6),
        )
        with self.assertRaises(ComponentValidationError):
            normalize_legend_anchor(
                {"kind": "none", "unexpected": True}
            )


if __name__ == "__main__":
    unittest.main()
