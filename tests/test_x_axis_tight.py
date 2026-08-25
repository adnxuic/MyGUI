"""Unit tests for tight X limits after autoscale when xmargin is 0."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib as mpl
from matplotlib.figure import Figure

from mygui.figuremodify.x_axis_tight import apply_tight_xlim


class XAxisTightTests(unittest.TestCase):
    def _axes(self, x_values, *, xmargin=0.0, inverted=False):
        figure = Figure()
        axes = figure.subplots()
        y_values = [float(index) for index in range(len(x_values))]
        axes.plot(list(x_values), y_values)
        axes.set_xmargin(xmargin)
        if inverted:
            axes.invert_xaxis()
        axes.set_autoscalex_on(True)
        axes.relim()
        axes.autoscale_view()
        return axes

    def test_zero_xmargin_matches_data_interval(self):
        axes = self._axes((10.2, 14.0, 17.8))
        apply_tight_xlim(axes)
        self.assertEqual(
            tuple(float(value) for value in axes.get_xlim()),
            (10.2, 17.8),
        )

    def test_zero_xmargin_clamps_round_number_locator(self):
        with mpl.rc_context({"axes.autolimit_mode": "round_numbers"}):
            axes = self._axes((10.2, 14.0, 17.8))
            before = tuple(float(value) for value in axes.get_xlim())
            self.assertTrue(before[0] < 10.2 or before[1] > 17.8)
            apply_tight_xlim(axes)
            self.assertEqual(
                tuple(float(value) for value in axes.get_xlim()),
                (10.2, 17.8),
            )

    def test_default_xmargin_is_left_alone(self):
        axes = self._axes((10.2, 14.0, 17.8), xmargin=0.05)
        before = tuple(float(value) for value in axes.get_xlim())
        apply_tight_xlim(axes)
        self.assertEqual(
            tuple(float(value) for value in axes.get_xlim()),
            before,
        )
        self.assertLess(before[0], 10.2)
        self.assertGreater(before[1], 17.8)

    def test_inverted_axis_preserves_order(self):
        axes = self._axes((10.2, 14.0, 17.8), inverted=True)
        apply_tight_xlim(axes)
        self.assertEqual(
            tuple(float(value) for value in axes.get_xlim()),
            (17.8, 10.2),
        )

    def test_disabled_autoscale_is_noop(self):
        axes = self._axes((10.2, 14.0, 17.8))
        axes.set_autoscalex_on(False)
        axes.set_xlim(0.0, 30.0)
        apply_tight_xlim(axes)
        self.assertEqual(
            tuple(float(value) for value in axes.get_xlim()),
            (0.0, 30.0),
        )


if __name__ == "__main__":
    unittest.main()
