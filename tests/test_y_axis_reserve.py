"""Unit tests for Axes lower-Y visual reserve in transform space."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from matplotlib.figure import Figure

from mygui.figuremodify.y_axis_reserve import (
    apply_y_lower_reserve,
    write_y_lower_reserve,
)


def _fraction_of_height(axes, y_value: float) -> float:
    display = axes.transAxes.inverted().transform(
        axes.transData.transform((0.0, y_value))
    )
    return float(display[1])


class YAxisReserveTests(unittest.TestCase):
    def _axes(self, y_values, *, scale="linear", inverted=False):
        figure = Figure()
        axes = figure.subplots()
        axes.plot([0.0, 1.0, 2.0], list(y_values))
        axes.set_yscale(scale)
        if inverted:
            axes.invert_yaxis()
        axes.set_autoscaley_on(True)
        axes.relim()
        axes.autoscale_view()
        return axes

    def test_linear_reserve_places_ordinary_span_in_upper_90_percent(self):
        axes = self._axes([1.0, 3.0, 5.0])
        ordinary = tuple(float(value) for value in axes.get_ylim())
        write_y_lower_reserve(axes, 0.1)
        apply_y_lower_reserve(axes)
        final = tuple(float(value) for value in axes.get_ylim())
        self.assertAlmostEqual(_fraction_of_height(axes, ordinary[0]), 0.1, places=6)
        self.assertAlmostEqual(_fraction_of_height(axes, ordinary[1]), 1.0, places=6)
        apply_y_lower_reserve(axes)
        apply_y_lower_reserve(axes)
        self.assertEqual(tuple(float(value) for value in axes.get_ylim()), final)

    def test_repeated_autoscale_plus_reserve_does_not_accumulate(self):
        axes = self._axes([2.0, 4.0, 8.0])
        write_y_lower_reserve(axes, 0.1)
        axes.relim()
        axes.autoscale_view()
        apply_y_lower_reserve(axes)
        first = tuple(float(value) for value in axes.get_ylim())
        for _ in range(5):
            axes.relim()
            axes.autoscale_view()
            apply_y_lower_reserve(axes)
        self.assertEqual(tuple(float(value) for value in axes.get_ylim()), first)

    def test_negative_data_and_log_scale_expand_toward_visual_bottom(self):
        linear = self._axes([-4.0, -1.0, 2.0])
        ordinary = tuple(float(value) for value in linear.get_ylim())
        write_y_lower_reserve(linear, 0.1)
        apply_y_lower_reserve(linear)
        self.assertAlmostEqual(_fraction_of_height(linear, ordinary[0]), 0.1, places=5)

        log_axes = self._axes([1.0, 10.0, 100.0], scale="log")
        ordinary_log = tuple(float(value) for value in log_axes.get_ylim())
        write_y_lower_reserve(log_axes, 0.1)
        apply_y_lower_reserve(log_axes)
        self.assertAlmostEqual(
            _fraction_of_height(log_axes, ordinary_log[0]),
            0.1,
            places=5,
        )

    def test_inverted_axis_and_disabled_autoscale(self):
        axes = self._axes([1.0, 2.0, 4.0], inverted=True)
        ordinary = tuple(float(value) for value in axes.get_ylim())
        write_y_lower_reserve(axes, 0.1)
        apply_y_lower_reserve(axes)
        self.assertAlmostEqual(_fraction_of_height(axes, ordinary[0]), 0.1, places=5)

        manual = self._axes([0.0, 1.0, 2.0])
        manual.set_autoscaley_on(False)
        manual.set_ylim(0.0, 10.0)
        write_y_lower_reserve(manual, 0.1)
        apply_y_lower_reserve(manual)
        self.assertEqual(tuple(float(value) for value in manual.get_ylim()), (0.0, 10.0))

    def test_constant_data_zero_span_is_a_noop_without_margins(self):
        figure = Figure()
        axes = figure.subplots()
        axes.plot([0.0, 1.0], [3.0, 3.0])
        axes.margins(x=0, y=0)
        axes.set_autoscaley_on(True)
        axes.relim()
        axes.autoscale_view()
        before = tuple(float(value) for value in axes.get_ylim())
        write_y_lower_reserve(axes, 0.1)
        apply_y_lower_reserve(axes)
        after = tuple(float(value) for value in axes.get_ylim())
        if np.isclose(before[0], before[1]):
            self.assertEqual(after, before)
        else:
            self.assertAlmostEqual(_fraction_of_height(axes, before[0]), 0.1, places=5)


if __name__ == "__main__":
    unittest.main()
