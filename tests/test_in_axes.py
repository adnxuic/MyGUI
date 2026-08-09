import base64
import os
import unittest
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image

from Qt_core import QApplication
from code.database import ColumnRef, TableRepository
from code.figuremodify.components import (
    ComponentKind,
    ComponentRole,
    ComponentValidationError,
    decode_in_axes_image,
)
from code.figuremodify.components.serialization import (
    normalize_v6_figure,
    validate_v7_figure,
)
from code.figuremodify.in_axes import (
    ImageInAxesCreateSpec,
    ZoomInAxesCreateSpec,
)
from code.project_io import migrate_project_snapshot
from code.widgets.fig_control_window.component_editors.inspector import (
    EditorPlacement,
)
from code.widgets.fig_control_window.figure_inspector import (
    FigureInspectorHost,
)
from code.widgets.figure_canvas.py_figure_canves import PyFigureCanvas


def image_payload(
    image_format="PNG",
    *,
    size=(4, 3),
    mode="RGBA",
    color=(20, 40, 80, 128),
    exif=None,
):
    image = Image.new(mode, size, color)
    buffer = BytesIO()
    kwargs = {"format": image_format}
    if exif is not None:
        kwargs["exif"] = exif
    image.save(buffer, **kwargs)
    return buffer.getvalue()


class InAxesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.repository = TableRepository()
        self.project = self.repository.create_project("InAxes")
        self.canvas = PyFigureCanvas(
            style="default",
            repository=self.repository,
            project_id=self.project.id,
            project_name=self.project.name,
        )
        self.host = FigureInspectorHost()
        panel = self.host.add_figure_inspector(
            self.canvas.component_registry.get(
                self.canvas.root_component_id
            ),
            self.canvas.editor_context,
            self.canvas.color_library,
        )
        self.canvas.set_figure_inspector(panel)
        self.canvas.add_axes(1, 1)

    def tearDown(self):
        self.canvas.dispose()
        self.host.dispose()
        self.app.processEvents()

    def zoom_spec(self, **overrides):
        defaults = self.canvas.component_creation_defaults().in_axes
        values = {
            "bounds": (0.55, 0.55, 0.4, 0.4),
            "xlim": (0.25, 1.75),
            "ylim": (0.5, 3.5),
            "facecolor": defaults.facecolor,
            "edgecolor": defaults.edgecolor,
            "linewidth": defaults.linewidth,
            "indicator_color": defaults.indicator_color,
            "indicator_linestyle": defaults.indicator_linestyle,
            "indicator_linewidth": defaults.indicator_linewidth,
        }
        values.update(overrides)
        return ZoomInAxesCreateSpec(**values)

    def image_spec(self, payload=None, **overrides):
        defaults = self.canvas.component_creation_defaults().in_axes
        values = {
            "bounds": (0.05, 0.55, 0.35, 0.35),
            "filename": "sample.png",
            "mime_type": "image/png",
            "payload_base64": base64.b64encode(
                payload or image_payload()
            ).decode("ascii"),
            "facecolor": defaults.facecolor,
            "edgecolor": defaults.edgecolor,
            "linewidth": defaults.linewidth,
            "interpolation": defaults.image_interpolation,
        }
        values.update(overrides)
        return ImageInAxesCreateSpec(**values)

    def test_zoom_mirrors_visible_charts_and_tracks_registry_commits(self):
        axes = self.canvas.current_axes
        cycle_before = self.canvas.axes_commands.cycle_state(
            self.canvas.current_axes_component_id
        ).to_dict()
        self.canvas.add_component_line(
            [0, 1, 2],
            [0, 1, 4],
            "-",
            "#123456",
            "source",
        )
        self.canvas.add_in_axes(self.zoom_spec())
        zoom = self.canvas.component_registry.query(
            kind=ComponentKind.IN_AXES,
            role=ComponentRole.IN_AXES_ZOOM,
        )[0]
        runtime = zoom.resolve_target()

        self.assertEqual(len(self.canvas.fig.axes), 1)
        self.assertEqual(axes.child_axes, [runtime.axes])
        self.assertEqual(len(runtime.content_artists), 1)
        self.assertEqual(runtime.content_artists[0].get_color(), "#123456")
        self.assertEqual(runtime.content_artists[0].get_label(), "_nolegend_")
        self.assertEqual(
            self.canvas.axes_commands.cycle_state(
                self.canvas.current_axes_component_id
            ).to_dict(),
            cycle_before,
        )

        sheet = next(iter(self.project.sheets.values()))
        sheet.set_block(0, 0, [[0.5, 0.75], [1.5, 2.5]])
        x_ref = ColumnRef(
            self.project.id,
            sheet.id,
            sheet.columns[0].id,
        )
        y_ref = ColumnRef(
            self.project.id,
            sheet.id,
            sheet.columns[1].id,
        )
        self.canvas.add_scatter(
            [0.5, 1.5],
            [0.75, 2.5],
            24.0,
            "#654321",
            "o",
            "points",
            x_ref,
            y_ref,
        )
        self.assertEqual(len(runtime.content_artists), 2)
        scatter = self.canvas.component_registry.query(
            role=ComponentRole.SCATTER
        )[0]
        self.assertTrue(
            self.canvas.delete_component_group(
                (scatter.component_id,),
                "scatter",
            )
        )
        self.assertEqual(len(runtime.content_artists), 1)

        source = self.canvas.component_registry.query(
            role=ComponentRole.LINE
        )[0]
        self.assertTrue(source.set_property("color", "#ABCDEF").ok)
        self.assertEqual(runtime.content_artists[0].get_color(), "#abcdef")
        self.assertTrue(source.set_property("visible", False).ok)
        self.assertEqual(runtime.content_artists, [])
        self.assertEqual(len(runtime.axes.texts), 0)
        self.assertIsNone(runtime.axes.get_legend())

    def test_image_formats_mime_base64_and_exif_orientation_are_strict(self):
        cases = (
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("BMP", "image/bmp"),
            ("TIFF", "image/tiff"),
        )
        for image_format, mime_type in cases:
            with self.subTest(image_format=image_format):
                payload = image_payload(
                    image_format,
                    mode="RGB",
                    color=(20, 40, 80),
                )
                array = decode_in_axes_image(
                    {
                        "filename": f"sample.{image_format.lower()}",
                        "mime_type": mime_type,
                        "payload_base64": base64.b64encode(payload).decode(),
                    }
                )
                self.assertEqual(array.shape[:2], (3, 4))

        exif = Image.Exif()
        exif[274] = 6
        oriented = decode_in_axes_image(
            {
                "filename": "oriented.jpg",
                "mime_type": "image/jpeg",
                "payload_base64": base64.b64encode(
                    image_payload(
                        "JPEG",
                        size=(4, 2),
                        mode="RGB",
                        color=(1, 2, 3),
                        exif=exif,
                    )
                ).decode(),
            }
        )
        self.assertEqual(oriented.shape[:2], (4, 2))

        valid = self.image_spec().data()
        invalid_cases = (
            {**valid, "payload_base64": "not base64"},
            {**valid, "mime_type": "image/jpeg"},
            {**valid, "filename": "C:/sample.png"},
        )
        for candidate in invalid_cases:
            with self.assertRaises(ComponentValidationError):
                decode_in_axes_image(candidate)

    def test_image_bytes_survive_roundtrip_without_source_file(self):
        raw = image_payload()
        self.canvas.add_in_axes(self.image_spec(raw))
        before = self.canvas.component_snapshot()
        inset_ids = sorted(
            component["id"]
            for component in before["components"]
            if component["kind"] == "in_axes"
        )

        restored = PyFigureCanvas(
            style="default",
            repository=self.repository,
            project_id=self.project.id,
            project_name=self.project.name,
            component_tree=before,
        )
        second_host = FigureInspectorHost()
        panel = second_host.add_figure_inspector(
            restored.component_registry.get(restored.root_component_id),
            restored.editor_context,
            restored.color_library,
        )
        restored.set_figure_inspector(panel)
        try:
            restored.restore_component_tree(before)
            image = restored.component_registry.query(
                kind=ComponentKind.IN_AXES,
                role=ComponentRole.IN_AXES_IMAGE,
            )[0]
            self.assertEqual(
                base64.b64decode(image.read_state().data["payload_base64"]),
                raw,
            )
            self.assertEqual(
                inset_ids,
                sorted(
                    component["id"]
                    for component in restored.component_snapshot()["components"]
                    if component["kind"] == "in_axes"
                ),
            )
            self.assertEqual(len(restored.fig.axes), 1)
            self.assertEqual(len(restored.fig.axes[0].child_axes), 1)
        finally:
            restored.dispose()
            second_host.dispose()

    def test_image_display_properties_and_replacement_use_controller_service(self):
        self.canvas.add_in_axes(self.image_spec())
        controller = self.canvas.component_registry.query(
            kind=ComponentKind.IN_AXES,
            role=ComponentRole.IN_AXES_IMAGE,
        )[0]
        runtime = controller.resolve_target()
        self.assertTrue(controller.set_property("opacity", 0.35).ok)
        self.assertTrue(controller.set_property("fit_mode", "stretch").ok)
        self.assertTrue(
            controller.set_property("interpolation", "nearest").ok
        )
        self.assertAlmostEqual(runtime.image_artist.get_alpha(), 0.35)
        self.assertEqual(runtime.axes.get_aspect(), "auto")
        self.assertEqual(runtime.image_artist.get_interpolation(), "nearest")

        jpeg = image_payload(
            "JPEG",
            size=(6, 2),
            mode="RGB",
            color=(120, 80, 40),
        )
        change = self.canvas.in_axes_service.replace_image(
            controller,
            {
                "filename": "replacement.jpg",
                "mime_type": "image/jpeg",
                "payload_base64": base64.b64encode(jpeg).decode(),
            },
        )
        self.assertTrue(change.ok)
        self.assertEqual(
            controller.read_state().data["filename"],
            "replacement.jpg",
        )
        self.assertEqual(runtime.image_artist.get_array().shape[:2], (2, 6))

    def test_profiles_are_exact_element_profiles_and_reused(self):
        self.canvas.add_in_axes(self.zoom_spec())
        self.canvas.add_in_axes(self.image_spec())
        panel = self.canvas.figure_inspector
        for role in (
            ComponentRole.IN_AXES_ZOOM,
            ComponentRole.IN_AXES_IMAGE,
        ):
            controller = self.canvas.component_registry.query(
                kind=ComponentKind.IN_AXES,
                role=role,
            )[0]
            profile = self.canvas.editor_registry.resolve_profile(controller)
            self.assertEqual(profile.placement, EditorPlacement.ELEMENT)
            first = panel.inspector(controller.component_id)
            self.assertIsNotNone(first)
            self.assertTrue(panel.show_component(controller.component_id))
            self.assertIs(panel.inspector(controller.component_id), first)
        image_profile = self.canvas.editor_registry.profile_for(
            ComponentKind.IN_AXES,
            ComponentRole.IN_AXES_IMAGE,
        )
        self.assertEqual(image_profile.tree.group_title, "Image Insets")

    def test_same_role_batch_and_parent_axes_cascade_cleanup(self):
        parent = self.canvas.current_axes
        self.canvas.add_in_axes(self.zoom_spec(bounds=(0.5, 0.5, 0.2, 0.2)))
        self.canvas.add_in_axes(self.zoom_spec(bounds=(0.7, 0.7, 0.2, 0.2)))
        zoom_ids = tuple(
            controller.component_id
            for controller in self.canvas.component_registry.query(
                kind=ComponentKind.IN_AXES,
                role=ComponentRole.IN_AXES_ZOOM,
            )
        )
        self.assertTrue(
            self.canvas.delete_component_group(zoom_ids, "zoom inset")
        )
        self.assertEqual(parent.child_axes, [])

        self.canvas.add_in_axes(self.zoom_spec())
        self.canvas.add_in_axes(self.image_spec())
        axes_id = self.canvas.current_axes_component_id
        inset_ids = {
            controller.component_id
            for controller in self.canvas.component_registry.query(
                kind=ComponentKind.IN_AXES
            )
        }
        self.assertTrue(
            self.canvas.delete_component_group((axes_id,), "axes")
        )
        self.assertEqual(len(self.canvas.fig.axes), 0)
        self.assertEqual(parent.child_axes, [])
        self.assertTrue(
            inset_ids.isdisjoint(
                controller.component_id
                for controller in self.canvas.component_registry.query()
            )
        )

    def test_creation_and_deletion_failure_restore_exact_runtime(self):
        parent = self.canvas.current_axes
        selected = self.canvas.current_component_id
        component_id = "failing-inset"
        with patch.object(
            self.canvas.in_axes_service,
            "register_runtime",
            side_effect=RuntimeError("injected registration failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.canvas.add_in_axes(
                    self.zoom_spec(),
                    object_id=component_id,
                )
        self.assertEqual(parent.child_axes, [])
        self.assertNotIn(component_id, self.canvas.component_registry)
        self.assertEqual(self.canvas.current_component_id, selected)

        self.canvas.add_in_axes(self.zoom_spec())
        controller = self.canvas.component_registry.query(
            kind=ComponentKind.IN_AXES,
            role=ComponentRole.IN_AXES_ZOOM,
        )[0]
        runtime = controller.resolve_target()
        rectangle = runtime.indicator_rectangle
        connectors = runtime.connectors
        with patch.object(
            self.canvas,
            "component_snapshot",
            side_effect=RuntimeError("injected verifier failure"),
        ):
            self.assertFalse(
                self.canvas.delete_component_group(
                    (controller.component_id,),
                    "zoom inset",
                )
            )
        self.assertIn(controller.component_id, self.canvas.component_registry)
        self.assertIs(controller.resolve_target(), runtime)
        self.assertIn(runtime.axes, parent.child_axes)
        self.assertIn(rectangle, parent.patches)
        self.assertTrue(all(item in parent.patches for item in connectors))

    def test_schema_v7_validation_and_v6_migration(self):
        self.canvas.add_in_axes(self.zoom_spec())
        self.canvas.add_in_axes(self.image_spec())
        figure = self.canvas.component_snapshot()
        validate_v7_figure(
            figure,
            {},
            self.project.id,
            self.project.name,
        )

        image = next(
            component
            for component in figure["components"]
            if component["role"] == "in_axes_image"
        )
        zoom = next(
            component
            for component in figure["components"]
            if component["role"] == "in_axes_zoom"
        )

        def mutate(component_id, callback):
            candidate = deepcopy(figure)
            record = next(
                component
                for component in candidate["components"]
                if component["id"] == component_id
            )
            callback(record)
            return candidate

        invalid = (
            (
                mutate(
                    image["id"],
                    lambda record: record["data"].__setitem__(
                        "payload_base64", "corrupt"
                    ),
                ),
                "Base64",
            ),
            (
                mutate(
                    image["id"],
                    lambda record: record["data"].__setitem__(
                        "mime_type", "image/jpeg"
                    ),
                ),
                "MIME type does not match",
            ),
            (
                mutate(
                    image["id"],
                    lambda record: record["properties"].__setitem__(
                        "opacity", 2.0
                    ),
                ),
                "opacity",
            ),
            (
                mutate(
                    image["id"],
                    lambda record: record["properties"].__setitem__(
                        "fit_mode", "crop"
                    ),
                ),
                "must be one of",
            ),
            (
                mutate(
                    zoom["id"],
                    lambda record: record["properties"]["bounds"].__setitem__(
                        2, 0.0
                    ),
                ),
                "width and height must be positive",
            ),
            (
                mutate(
                    zoom["id"],
                    lambda record: record["properties"].__setitem__(
                        "xlim", [1.0, 1.0]
                    ),
                ),
                "must not be degenerate",
            ),
            (
                mutate(
                    zoom["id"],
                    lambda record: record.__setitem__("data", {"x": 1}),
                ),
                "data fields",
            ),
        )
        for candidate, message in invalid:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_v7_figure(
                        candidate,
                        {},
                        self.project.id,
                        self.project.name,
                    )

        with self.assertRaisesRegex(ValueError, "does not support in_axes"):
            normalize_v6_figure(figure)

        without_insets = deepcopy(figure)
        without_insets["components"] = [
            component
            for component in without_insets["components"]
            if component["kind"] != "in_axes"
        ]
        legacy_project = {
            "schema": "mygui-project",
            "schema_version": 6,
            "project": {
                "id": self.project.id,
                "name": self.project.name,
            },
            "table": self.repository.snapshot(self.project.id),
            "figure": without_insets,
        }
        migrated = migrate_project_snapshot(legacy_project)
        self.assertEqual(migrated["schema_version"], 8)
        self.assertEqual(migrated["figure"], without_insets)


if __name__ == "__main__":
    unittest.main()
