from Qt_core import *
from code import tex_config
from code import status_messages

import matplotlib as mpl
from matplotlib.figure import Figure

from matplotlib.text import Text
from matplotlib.style import use
from typing import Any
import re
import warnings


class TextRenderError(ValueError):
    pass


def _missing_glyph_message(message: str) -> str | None:
    if "Glyph" not in message or "missing from font" not in message:
        return None
    match = re.search(r"Glyph\s+(\d+)", message)
    if not match:
        return "Current font is missing a glyph; text may render incorrectly."
    codepoint = int(match.group(1))
    return f"Current font is missing glyph U+{codepoint:04X}; text may render incorrectly."


class PyTextModify:
    def __init__(self, fig, style=None, text: Text=None, project_record: dict[str, Any] | None = None,
                 project_collection: list[dict[str, Any]] | None = None):
        self.style = style
        self.fig = fig

        self.text = text
        self.project_record = project_record
        self.project_collection = project_collection
        self._deleted = False
        self.last_render_warning = None

    def update_project_record(self, **values):
        if self.project_record is not None:
            self.project_record.update(values)

    def redraw(self):
        self.last_render_warning = None
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always", UserWarning)
            self.fig.canvas.draw()

        for warning in caught_warnings:
            message = str(warning.message)
            glyph_message = _missing_glyph_message(message)
            if glyph_message is not None:
                tex_config.tex_logger().warning(
                    "Matplotlib text glyph warning action=redraw message=%s",
                    message,
                )
                self.last_render_warning = glyph_message
                status_messages.show_error(glyph_message)
                continue
            warnings.warn(warning.message, warning.category, stacklevel=2)

    def delete_object(self):
        if self._deleted:
            return
        self._deleted = True
        if self.project_collection is not None and self.project_record is not None:
            try:
                self.project_collection.remove(self.project_record)
            except ValueError:
                pass
        try:
            self.text.remove()
        except ValueError:
            pass
        self.redraw()

    def set_text_font(self, font):
        size = self.text.get_fontsize()
        self.text.set_fontproperties(font)
        self.text.set_fontsize(size)
        self.update_project_record(fontfamily=font)
        self.redraw()

    def set_text_fontsize(self, size):
        self.text.set_fontsize(size)
        self.update_project_record(fontsize=float(self.text.get_fontsize()))
        self.redraw()

    def get_text_usetex(self) -> bool:
        get_usetex = getattr(self.text, "get_usetex", None)
        if get_usetex is None:
            return False
        return bool(get_usetex())

    def set_text_usetex(self, use_tex: bool):
        use_tex = bool(use_tex)
        set_usetex = getattr(self.text, "set_usetex", None)
        if set_usetex is None:
            self.update_project_record(usetex=False)
            return

        if use_tex and not tex_config.is_tex_enabled():
            set_usetex(False)
            self.update_project_record(usetex=False)
            raise TextRenderError("Enable TeX before using TeX rendering for this text.")

        current_usetex = self.get_text_usetex()
        current_record_usetex = None
        if self.project_record is not None:
            current_record_usetex = self.project_record.get("usetex", current_usetex)

        try:
            set_usetex(use_tex)
            self.update_project_record(usetex=use_tex)
            self.redraw()
        except Exception as exc:
            tex_config.tex_logger().warning(
                "TeX text render mode change failed action=set_text_usetex requested=%s error=%s",
                use_tex,
                exc,
            )
            set_usetex(current_usetex)
            self.update_project_record(
                usetex=current_record_usetex if current_record_usetex is not None else current_usetex
            )
            try:
                self.redraw()
            except Exception as rollback_exc:
                tex_config.tex_logger().warning(
                    "TeX text render mode rollback redraw failed action=set_text_usetex error=%s",
                    rollback_exc,
                )
            raise TextRenderError("Text TeX render failed; keeping previous rendering mode.") from exc

    def set_text_content(self, content):
        current_text = self.text.get_text()
        current_record_text = None
        if self.project_record is not None:
            current_record_text = self.project_record.get("text", current_text)
        try:
            self.text.set_text(content)
            self.update_project_record(text=content)
            self.redraw()
        except Exception as exc:
            tex_config.tex_logger().warning(
                "TeX text render failed action=set_text_content text_length=%s text_preview=%r error=%s",
                len(content),
                content[:80],
                exc,
            )
            self.text.set_text(current_text)
            self.update_project_record(text=current_record_text if current_record_text is not None else current_text)
            try:
                self.redraw()
            except Exception as rollback_exc:
                tex_config.tex_logger().warning(
                    "TeX text rollback redraw failed action=set_text_content error=%s",
                    rollback_exc,
                )
            raise TextRenderError(
                "Text render failed; keeping last valid text. Remove unsupported TeX or Unicode input."
            ) from exc

    def set_xy_position(self, x, y):
        self.text.set_position((x, y))
        self.update_project_record(x=float(x), y=float(y))
        self.redraw()
