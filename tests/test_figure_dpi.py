import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROBE = textwrap.dedent(
    r"""
    import json
    import struct
    import tempfile
    from pathlib import Path

    from PySide6.QtWidgets import QApplication
    from mygui.database import TableRepository
    from mygui.widgets.common_widget.min_widget.color_library import ColorLibrary
    from mygui.widgets.figure_canvas.py_figure_canves import PyFigureCanvas

    app = QApplication([])
    repository = TableRepository()
    project = repository.create_project("DPI Probe")
    class ProjectMetadataStub:
        def apply_controller_name(self, _project_id, _new_name):
            pass
    canvas = PyFigureCanvas(
        width=6.4,
        height=4.8,
        dpi=100,
        style="default",
        repository=repository,
        project_id=project.id,
        project_metadata=ProjectMetadataStub(),
        color_library=ColorLibrary(),
    )
    canvas.show()
    app.processEvents()

    readonly = False
    try:
        canvas.document_dpi = 72
    except AttributeError:
        readonly = True

    with tempfile.TemporaryDirectory() as directory:
        default_path = Path(directory) / "default.png"
        explicit_path = Path(directory) / "explicit.png"
        canvas.save(default_path)
        canvas.save(explicit_path, dpi=200)

        default_bytes = default_path.read_bytes()
        explicit_bytes = explicit_path.read_bytes()
        default_size = struct.unpack(">II", default_bytes[16:24])
        explicit_size = struct.unpack(">II", explicit_bytes[16:24])

    snapshot = canvas.component_snapshot()
    root = next(
        component
        for component in snapshot["components"]
        if component["id"] == snapshot["root_component_id"]
    )
    result = {
        "device_pixel_ratio": float(canvas.canva.device_pixel_ratio),
        "runtime_dpi": float(canvas.fig.dpi),
        "document_dpi": canvas.document_dpi,
        "size_inches": [float(value) for value in canvas.fig.get_size_inches()],
        "snapshot_dpi": root["properties"]["dpi"],
        "snapshot_size_inches": root["properties"]["size_inches"],
        "default_size": list(default_size),
        "explicit_size": list(explicit_size),
        "readonly": readonly,
    }
    print("DPI_RESULT=" + json.dumps(result))
    canvas.close()
    app.processEvents()
    """
)


class FigureDocumentDpiTests(unittest.TestCase):
    def _probe_scale(self, scale: str) -> dict:
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        environment["QT_SCALE_FACTOR"] = scale
        completed = subprocess.run(
            [sys.executable, "-c", PROBE],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"DPI probe failed at scale {scale}:\n{completed.stdout}\n{completed.stderr}",
        )
        result_line = next(
            (line for line in completed.stdout.splitlines() if line.startswith("DPI_RESULT=")),
            None,
        )
        self.assertIsNotNone(result_line, msg=completed.stdout)
        return json.loads(result_line.removeprefix("DPI_RESULT="))

    def test_document_dpi_export_and_snapshot_are_scale_independent(self):
        for scale in ("1", "1.25", "1.5", "2"):
            with self.subTest(scale=scale):
                result = self._probe_scale(scale)
                self.assertAlmostEqual(result["device_pixel_ratio"], float(scale))
                self.assertAlmostEqual(result["runtime_dpi"], 100 * float(scale))
                self.assertEqual(result["document_dpi"], 100)
                self.assertEqual(result["snapshot_dpi"], 100)
                self.assertEqual(result["default_size"], [640, 480])
                self.assertEqual(result["explicit_size"], [1280, 960])
                self.assertEqual(result["size_inches"], [6.4, 4.8])
                self.assertEqual(result["snapshot_size_inches"], [6.4, 4.8])
                self.assertTrue(result["readonly"])


if __name__ == "__main__":
    unittest.main()
