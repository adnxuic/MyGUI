import base64
from io import BytesIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
from PIL import Image

from mygui.excel_io import read_excel_workbook
from mygui.figuremodify.components import decode_in_axes_image
from mygui.figuremodify.in_axes import embedded_image_data
from mygui.project_io import load_project_file
from mygui.resource_limits import (
    ResourceLimits,
    load_resource_limits,
    validate_json_budget,
)
from mygui.text_io import read_text_source


def _png_bytes(size=(2, 2)) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "red").save(buffer, format="PNG")
    return buffer.getvalue()


class ResourceLimitTests(unittest.TestCase):
    def test_environment_overrides_are_validated(self):
        limits = load_resource_limits({"MYGUI_MAX_PROJECT_BYTES": "1024"})
        self.assertEqual(limits.max_project_bytes, 1024)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            load_resource_limits({"MYGUI_MAX_PROJECT_BYTES": "many"})
        with self.assertRaisesRegex(ValueError, "between"):
            load_resource_limits({"MYGUI_MAX_PROJECT_BYTES": "9999999999"})

    def test_json_depth_value_and_component_budgets(self):
        limits = ResourceLimits(max_json_depth=3)
        with self.assertRaisesRegex(ValueError, "maximum depth"):
            validate_json_budget({"a": {"b": {"c": 1}}}, limits=limits)
        limits = ResourceLimits(max_json_values=2)
        with self.assertRaisesRegex(ValueError, "value-count"):
            validate_json_budget([1, 2], limits=limits)
        limits = ResourceLimits(max_project_components=1)
        with self.assertRaisesRegex(ValueError, "component budget"):
            validate_json_budget(
                {"figure": {"components": [{}, {}]}},
                limits=limits,
            )

    def test_project_and_text_files_are_rejected_before_full_read(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "large.mygui"
            project.write_bytes(b"{" + b" " * 64 + b"}")
            text = Path(directory) / "large.txt"
            text.write_bytes(b"1,2\n" * 20)
            with patch.dict(
                os.environ,
                {
                    "MYGUI_MAX_PROJECT_BYTES": "32",
                    "MYGUI_MAX_TEXT_BYTES": "32",
                },
            ):
                with self.assertRaisesRegex(ValueError, "file-size budget"):
                    load_project_file(project)
                with self.assertRaisesRegex(ValueError, "byte budget"):
                    read_text_source(text)

    def test_image_encoded_bytes_and_pixels_are_bounded(self):
        payload = _png_bytes()
        data = {
            "filename": "image.png",
            "mime_type": "image/png",
            "payload_base64": base64.b64encode(payload).decode("ascii"),
        }
        with patch.dict(os.environ, {"MYGUI_MAX_IMAGE_BYTES": "8"}):
            with self.assertRaisesRegex(ValueError, "byte budget"):
                decode_in_axes_image(data)
        with patch.dict(os.environ, {"MYGUI_MAX_IMAGE_PIXELS": "3"}):
            with self.assertRaisesRegex(ValueError, "pixel budget"):
                decode_in_axes_image(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.png"
            path.write_bytes(payload)
            with patch.dict(os.environ, {"MYGUI_MAX_IMAGE_BYTES": "8"}):
                with self.assertRaisesRegex(ValueError, "byte budget"):
                    embedded_image_data(path)

    def test_excel_zip_and_cell_budgets_are_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.xlsx"
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet.append([1, 2])
            sheet.append([3, 4])
            workbook.save(path)
            workbook.close()

            with patch.dict(os.environ, {"MYGUI_MAX_EXCEL_BYTES": "8"}):
                with self.assertRaisesRegex(ValueError, "byte budget"):
                    read_excel_workbook(str(path))
            with patch.dict(os.environ, {"MYGUI_MAX_EXCEL_CELLS": "3"}):
                with self.assertRaisesRegex(ValueError, "cell budget"):
                    read_excel_workbook(str(path))


if __name__ == "__main__":
    unittest.main()
