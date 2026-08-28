"""Canonical Axes-layout helpers shared by GUI tests."""

from mygui.figuremodify.axes_layout import AxesLayoutSpec


def create_regular_axes(canvas, nrows=1, ncols=1, slots=None):
    """Create a regular grid through the production layout contract."""

    return canvas.create_axes_layout(
        AxesLayoutSpec.grid(
            int(nrows),
            int(ncols),
            slots=(
                tuple(int(slot) for slot in slots)
                if slots is not None
                else None
            ),
            cell_view=canvas.axes_layout_service.creation_view_defaults(),
        )
    )
