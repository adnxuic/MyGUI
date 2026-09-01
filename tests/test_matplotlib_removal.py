"""Fault-injected coverage for reversible Matplotlib removal handles."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
import unittest

import numpy as np
from matplotlib.figure import Figure
from matplotlib.image import AxesImage

from mygui.figuremodify.components.errors import ComponentValidationError
from mygui.figuremodify.components.matplotlib_removal import (
    MATPLOTLIB_REMOVAL,
    AxesRemovalHandle,
    AxesSubtreeRemovalHandle,
    AuxiliaryRemovalState,
    ChildAxesRemovalHandle,
    ColorbarRemovalHandle,
    ErrorBarRemovalHandle,
    Field2DRemovalHandle,
    InAxesRemovalHandle,
    RemovalHandle,
)


class MatplotlibRemovalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.figure = Figure()
        self.axes = self.figure.add_subplot(111)
        self.line, = self.axes.plot([0, 1], [1, 2])

    def test_prepare_artist_and_round_trip_identity(self):
        owner = list(self.axes.lines)
        handle = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        self.assertIs(handle.target, self.line)
        self.assertIn(self.line, handle.owner)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(self.line, self.axes.lines)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIs(self.axes.lines[self.axes.lines.index(self.line)], self.line)
        self.assertEqual(list(self.axes.lines), owner)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.finalize(handle)
        self.assertIsNone(self.line.axes)

    def test_prepare_artist_rejects_detached_target(self):
        orphan = SimpleNamespace(axes=None, figure=None)
        with self.assertRaisesRegex(
            ComponentValidationError,
            "no reversible list container",
        ):
            MATPLOTLIB_REMOVAL.prepare_artist(orphan, subject=self.axes)

    def test_commit_is_idempotent_and_rollback_skips_attached_handles(self):
        handle = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIn(self.line, self.axes.lines)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(self.line, self.axes.lines)

    def test_commit_restores_when_owner_changes_before_deletion(self):
        handle = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        handle.owner.remove(self.line)
        with self.assertRaisesRegex(
            ComponentValidationError,
            "changed before deletion",
        ):
            MATPLOTLIB_REMOVAL.commit(handle)
        self.assertIn(self.line, self.axes.lines)
        self.assertFalse(handle.detached)

    def test_prepare_axes_rejects_unsupported_contracts(self):
        detached = Figure().add_subplot(111)
        detached.remove()
        with self.assertRaisesRegex(ComponentValidationError, "not attached"):
            MATPLOTLIB_REMOVAL.prepare_axes(detached)

        with mock.patch.object(self.figure, "_remove_axes", None):
            with self.assertRaisesRegex(
                ComponentValidationError,
                "unsupported",
            ):
                MATPLOTLIB_REMOVAL.prepare_axes(self.axes)

        stack = self.figure._axstack
        original = dict(stack._axes)
        stack._axes.pop(self.axes, None)
        try:
            with self.assertRaisesRegex(ComponentValidationError, "Axes stack"):
                MATPLOTLIB_REMOVAL.prepare_axes(self.axes)
        finally:
            stack._axes = original

    def test_axes_commit_rollback_and_finalize_keep_identity(self):
        handle = MATPLOTLIB_REMOVAL.prepare_axes(self.axes)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(self.axes, self.figure._localaxes)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIn(self.axes, self.figure._localaxes)
        MATPLOTLIB_REMOVAL.commit(handle)
        child = mock.Mock()
        child.remove.side_effect = RuntimeError("already gone")
        handle.child_axes = (child,)
        MATPLOTLIB_REMOVAL.finalize(handle)
        child.remove.assert_called_once()
        self.assertIsNone(self.axes.figure)

    def test_prepare_child_axes_and_finalize_remove_from_parent_slot(self):
        child = self.axes.inset_axes([0.5, 0.5, 0.3, 0.3])
        handle = MATPLOTLIB_REMOVAL.prepare_child_axes(child, self.axes)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(child, self.axes.child_axes)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIn(child, self.axes.child_axes)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.finalize(handle)
        self.assertNotIn(child, self.axes.child_axes)

        with self.assertRaisesRegex(ComponentValidationError, "detached"):
            MATPLOTLIB_REMOVAL.prepare_child_axes(child, self.axes)

    def test_prepare_in_axes_rejects_broken_runtimes(self):
        with self.assertRaisesRegex(ComponentValidationError, "parent/child"):
            MATPLOTLIB_REMOVAL.prepare_in_axes(SimpleNamespace(axes=None))

        child = self.axes.inset_axes([0.1, 0.1, 0.2, 0.2])
        runtime = SimpleNamespace(
            axes=child,
            parent_axes=self.axes,
            indicator_rectangle=object(),
            connectors=(),
        )
        with self.assertRaisesRegex(ComponentValidationError, "indicator"):
            MATPLOTLIB_REMOVAL.prepare_in_axes(runtime)

    def test_in_axes_commit_force_restore_and_finalize(self):
        child = self.axes.inset_axes([0.2, 0.2, 0.3, 0.3])
        rectangle = self.axes.add_patch(
            __import__("matplotlib.patches", fromlist=["Rectangle"]).Rectangle(
                (0.0, 0.0), 0.1, 0.1
            )
        )
        runtime = SimpleNamespace(
            axes=child,
            parent_axes=self.axes,
            indicator_rectangle=rectangle,
            connectors=(),
        )
        handle = MATPLOTLIB_REMOVAL.prepare_in_axes(runtime)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(child, self.axes.child_axes)
        MATPLOTLIB_REMOVAL.force_restore(handle)
        self.assertIn(child, self.axes.child_axes)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.finalize(handle)
        self.assertNotIn(child, self.axes.child_axes)

    def test_prepare_colorbar_requires_owner_and_callbacks(self):
        with self.assertRaisesRegex(ComponentValidationError, "Colorbar target"):
            MATPLOTLIB_REMOVAL.prepare_colorbar(object())

        image = self.axes.imshow(np.arange(9).reshape(3, 3))
        colorbar = self.figure.colorbar(image, ax=self.axes)
        colorbar.mappable.callbacks = None
        with self.assertRaisesRegex(ComponentValidationError, "callback"):
            MATPLOTLIB_REMOVAL.prepare_colorbar(colorbar)

    def test_colorbar_and_axes_subtree_commit_rollback_and_finalize(self):
        image = self.axes.imshow(np.arange(9).reshape(3, 3))
        colorbar = self.figure.colorbar(image, ax=self.axes)
        handle = MATPLOTLIB_REMOVAL.prepare_colorbar(colorbar)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIs(image.colorbar, colorbar)
        subtree = MATPLOTLIB_REMOVAL.prepare_axes_subtree(self.axes, (colorbar,))
        MATPLOTLIB_REMOVAL.commit(subtree)
        MATPLOTLIB_REMOVAL.rollback(subtree)
        self.assertIn(self.axes, self.figure._localaxes)
        MATPLOTLIB_REMOVAL.commit(subtree)
        MATPLOTLIB_REMOVAL.finalize(subtree)

    def test_composite_commit_failures_force_restore(self):
        artist = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        field = Field2DRemovalHandle(
            runtime=SimpleNamespace(axes=self.axes),
            artist_handles=(artist,),
        )
        artist.owner.remove(self.line)
        with self.assertRaisesRegex(
            ComponentValidationError,
            "changed before deletion",
        ):
            MATPLOTLIB_REMOVAL.commit(field)
        self.assertIn(self.line, self.axes.lines)

        artist = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        container = object()
        errorbar = ErrorBarRemovalHandle(
            runtime=SimpleNamespace(axes=self.axes),
            container=container,
            container_owner=[],
            container_index=0,
            artist_handles=(artist,),
            subject=self.axes,
        )
        with self.assertRaises(ValueError):
            MATPLOTLIB_REMOVAL.commit(errorbar)
        self.assertIn(self.line, self.axes.lines)

    def test_axes_subtree_commit_failure_force_restores(self):
        image = self.axes.imshow(np.arange(4).reshape(2, 2))
        colorbar = self.figure.colorbar(image, ax=self.axes)
        subtree = MATPLOTLIB_REMOVAL.prepare_axes_subtree(self.axes, (colorbar,))
        subtree.colorbar_handles[0].parent_entries = (([], 0),)
        with self.assertRaises(Exception):
            MATPLOTLIB_REMOVAL.commit(subtree)
        self.assertIn(self.axes, self.figure._localaxes)

    def test_field_2d_and_errorbar_successful_round_trip(self):
        image = AxesImage(self.axes)
        self.axes.add_image(image)
        runtime = SimpleNamespace(
            axes=self.axes,
            iter_artists=lambda: (image,),
        )
        handle = MATPLOTLIB_REMOVAL.prepare_field_2d(runtime)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIn(image, self.axes.images)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.finalize(handle)

        with self.assertRaisesRegex(ComponentValidationError, "not attached"):
            MATPLOTLIB_REMOVAL.prepare_field_2d(SimpleNamespace(axes=None))

        with self.assertRaisesRegex(ComponentValidationError, "Error Bar"):
            MATPLOTLIB_REMOVAL.prepare_errorbar(SimpleNamespace(axes=self.axes, container=None))

    def test_prepare_errorbar_round_trip_uses_container_owner(self):
        container = self.axes.errorbar([0, 1], [1, 2], yerr=[0.1, 0.1])
        runtime = SimpleNamespace(
            axes=self.axes,
            container=container,
            iter_artists=lambda: tuple(container.get_children()),
        )
        handle = MATPLOTLIB_REMOVAL.prepare_errorbar(runtime)
        MATPLOTLIB_REMOVAL.commit(handle)
        self.assertNotIn(container, self.axes.containers)
        MATPLOTLIB_REMOVAL.rollback(handle)
        self.assertIn(container, self.axes.containers)
        MATPLOTLIB_REMOVAL.commit(handle)
        MATPLOTLIB_REMOVAL.finalize(handle)

    def test_force_restore_reinserts_already_present_targets(self):
        handle = MATPLOTLIB_REMOVAL.prepare_artist(self.line, subject=self.axes)
        handle.detached = True
        MATPLOTLIB_REMOVAL.force_restore(handle)
        self.assertIn(self.line, self.axes.lines)
        child_handle = ChildAxesRemovalHandle(
            target=self.axes,
            owner=[self.axes],
            index=0,
            subject=self.axes,
            detached=True,
        )
        MATPLOTLIB_REMOVAL.force_restore(child_handle)
        self.assertFalse(child_handle.detached)

    def test_finalize_child_axes_removes_restored_slot(self):
        child = self.axes.inset_axes([0.6, 0.6, 0.2, 0.2])
        handle = MATPLOTLIB_REMOVAL.prepare_child_axes(child, self.axes)
        handle.detached = True
        handle.owner.remove(child)
        MATPLOTLIB_REMOVAL.finalize(handle)
        self.assertNotIn(child, self.axes.child_axes)

    def test_handle_types_are_explicit_mementos(self):
        self.assertTrue(RemovalHandle.__dataclass_params__.slots)
        self.assertTrue(AxesRemovalHandle.__dataclass_params__.slots)
        self.assertTrue(ColorbarRemovalHandle.__dataclass_params__.slots)
        self.assertTrue(InAxesRemovalHandle.__dataclass_params__.slots)
        self.assertTrue(AuxiliaryRemovalState.__dataclass_params__.slots)
        self.assertTrue(AxesSubtreeRemovalHandle.__dataclass_params__.slots)

    def test_field_2d_empty_handles_resolve_subject_from_runtime(self):
        empty = Field2DRemovalHandle(
            runtime=SimpleNamespace(axes=self.axes),
            artist_handles=(),
        )
        self.assertIs(empty.subject, self.axes)
        missing = Field2DRemovalHandle(
            runtime=SimpleNamespace(axes="not-axes"),
            artist_handles=(),
        )
        self.assertIsNone(missing.subject)


if __name__ == "__main__":
    unittest.main()
