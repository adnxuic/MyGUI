from dataclasses import dataclass
from typing import Union
from uuid import uuid4
import weakref

from Qt_core import *

from code import status_messages
from code.figuremodify.style_base.color_models import (
    all_single_colors,
    ColorCycleState,
    PaletteDefinition,
    builtin_palettes,
)

from matplotlib.figure import Figure
from matplotlib.axes import Axes


@dataclass(slots=True)
class _ColorTarget:
    token: str
    order: int
    set_color: weakref.WeakMethod
    get_color: weakref.WeakMethod
    sync_widget: weakref.WeakMethod
    is_active: weakref.WeakMethod


class PyAxesModify:
    def __init__(self, fig: Figure, axe: Axes, style=None):
        self.style = style
        self.fig = fig

        self.axe:Axes = axe

        self.vis_objects: list[_ColorTarget] = []
        self.color_selector = ColorCycleState()

        self.legend = None

    def redraw(self):
        self.fig.canvas.draw_idle()

    def update_legend(self):
        legend = self.axe.get_legend()
        if legend is None:
            return
        visible = bool(legend.get_visible())
        location = getattr(legend, "_loc", "best")
        legend.remove()
        try:
            legend = self.axe.legend(loc=location)
        except (TypeError, ValueError):
            legend = self.axe.legend(loc="best")
        legend.set_visible(visible)

    def register_color_target(self, modifier, widget) -> str:
        token = str(uuid4())
        project_record = getattr(modifier, "project_record", None)
        try:
            order = int(project_record.get("color_order"))
        except (AttributeError, TypeError, ValueError):
            order = len(self.vis_objects)
        target = _ColorTarget(
            token=token,
            order=order,
            set_color=weakref.WeakMethod(modifier.update_color),
            get_color=weakref.WeakMethod(modifier.get_color),
            sync_widget=weakref.WeakMethod(widget.set_color),
            is_active=weakref.WeakMethod(modifier.is_color_target_active),
        )
        self.vis_objects.append(target)
        return token

    def unregister_color_target(self, token: str) -> None:
        self.vis_objects = [target for target in self.vis_objects if target.token != token]

    def _live_color_targets(self) -> list[tuple[_ColorTarget, callable, callable, callable]]:
        live = []
        stale_tokens = set()
        for target in self.vis_objects:
            setter = target.set_color()
            getter = target.get_color()
            sync_widget = target.sync_widget()
            active = target.is_active()
            if None in (setter, getter, sync_widget, active):
                stale_tokens.add(target.token)
                continue
            try:
                if not active():
                    stale_tokens.add(target.token)
                    continue
            except RuntimeError:
                stale_tokens.add(target.token)
                continue
            live.append((target, setter, getter, sync_widget))
        if stale_tokens:
            self.vis_objects = [
                target for target in self.vis_objects if target.token not in stale_tokens
            ]
        live.sort(key=lambda item: item[0].order)
        return live

    @staticmethod
    def _resolve_palette(category, subcategory=None) -> PaletteDefinition:
        if isinstance(category, PaletteDefinition):
            return category
        for palette in builtin_palettes():
            if palette.category == category and (
                subcategory is None
                and palette.id == "builtin:all-colors"
                or subcategory is not None
                and palette.name == subcategory
            ):
                return palette
        if category == "单色" and subcategory is None:
            return PaletteDefinition(
                "legacy:all-single", "全部单色", all_single_colors(), category="单色"
            )
        raise ValueError(f"Unknown color palette: {category!r} / {subcategory!r}")

    def change_all_color(self, category, subcategory=None) -> bool:
        try:
            palette = self._resolve_palette(category, subcategory)
        except ValueError as exc:
            status_messages.show_error(str(exc))
            return False

        targets = self._live_color_targets()
        if not targets:
            status_messages.show_warning("当前坐标轴没有可配色的图表对象。")
            return False

        snapshots: list[tuple[callable, callable, str]] = []
        try:
            for index, (_target, setter, getter, sync_widget) in enumerate(targets):
                previous = getter()
                snapshots.append((setter, sync_widget, previous))
                color = palette.colors[index % len(palette.colors)]
                setter(color, redraw=False, refresh_legend=False)
                sync_widget(color, emit=False)
        except Exception as exc:
            for setter, sync_widget, previous in reversed(snapshots):
                try:
                    setter(previous, redraw=False, refresh_legend=False)
                    sync_widget(previous, emit=False)
                except (RuntimeError, ValueError):
                    pass
            self.update_legend()
            self.redraw()
            status_messages.show_error(f"应用配色失败，已恢复原颜色：{exc}")
            return False

        self.color_selector.commit_palette_for_count(palette, len(targets))
        self.update_legend()
        self.redraw()
        status_messages.show_success(
            f"已将“{palette.display_name}”应用到 {len(targets)} 个图表对象。"
        )
        return True

    def color_cycle_snapshot(self):
        return self.color_selector.to_dict()

    def restore_color_cycle(self, value) -> None:
        self.color_selector = ColorCycleState.from_dict(value)

    def set_visible(self, spine: str, visible: bool):
        self.axe.spines[spine].set_visible(visible)
        
        if spine in ['left', 'right']:
            self.axe.yaxis.set_visible(visible)
        elif spine in ['top', 'bottom']:
            self.axe.xaxis.set_visible(visible)
        
        self.redraw()

    def set_legend_position(self, position: Union[str, tuple]):
        self.legend = self.axe.legend(loc=position)
        self.redraw()

    def change_axes(self, axes, **kwargs):
        axes.set(**kwargs)
        return axes

    def set_bottom_spine_position(self, pos):
        self.axe.spines["bottom"].set_position(("axes", pos))
        self.redraw()

    def set_x_range(self, x_min, x_max):
        self.axe.set_xlim(x_min, x_max)
        self.redraw()

    def set_y_range(self, y_min, y_max):
        self.axe.set_ylim(y_min, y_max)
        self.redraw()

    def set_xylabel_font(self, font):
        self.axe.xaxis.label.set_font(font)
        self.axe.yaxis.label.set_font(font)
        self.redraw()

    def set_x_label(self, label):
        self.axe.set_xlabel(label)
        self.redraw()

    def set_y_label(self, label):
        self.axe.set_ylabel(label)
        self.redraw()

    def set_xylabel_fontsize(self, size):
        self.axe.xaxis.label.set_fontsize(size)
        self.axe.yaxis.label.set_fontsize(size)
        self.redraw()

    def set_xy_title_position(self,x_xpos, x_ypos, y_xpos, y_ypos):
        self.axe.xaxis.set_label_coords(x_xpos, x_ypos)
        self.axe.yaxis.set_label_coords(y_xpos, y_ypos)
        self.redraw()
