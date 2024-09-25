from typing import Union
import random

from Qt_core import *

from code.figuremodify.style_base.color_base import color_combi_dict
from code.widgets.common_widget.min_widget.py_colorchoice_widgets import ColorSelector

import matplotlib as mpl
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import PathCollection

from matplotlib.style import use


class PyAxesModify:
    def __init__(self, fig: Figure, axe: Axes, style=None):
        self.style = style
        self.fig = fig

        self.axe = axe

        self.vis_objects = []

        self.color_selector = ColorSelector()

        self.legend = None

    def redraw(self):
        self.fig.canvas.draw()

    def update_legend(self):
        self.axe.legend().remove()
        self.axe.legend()

    def add_vis_object(self, vis_object):
        self.vis_objects.append(vis_object)

    def change_all_color(self, category, subcategory=None):
        if subcategory is None:
            colors = color_combi_dict[category]
        else:
            colors = color_combi_dict[category][subcategory]

        if category == "单色":
            # 在单色的颜色集合中随机选择跟可视化对象数量相同的不同颜色
            colors = random.sample(color_combi_dict[category], len(self.vis_objects))
            for vis_object, color in zip(self.vis_objects, colors):
                vis_object(color)
        else:
            # 使用颜色组合中的所有颜色
            for vis_object, color in zip(self.vis_objects[:len(colors)], colors):
                vis_object(color)
            
            # 如果还有剩余的可视化对象，从单色集合中随机选择不同的颜色
            if len(self.vis_objects) > len(colors):
                remaining_objects = self.vis_objects[len(colors):]
                used_colors = set(colors)
                for vis_object in remaining_objects:
                    available_colors = [c for c in color_combi_dict["单色"] if c not in used_colors]
                    if not available_colors:
                        available_colors = color_combi_dict["单色"]
                    color = random.choice(available_colors)
                    vis_object(color)
                    used_colors.add(color)

        self.update_legend()
        self.redraw()

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
