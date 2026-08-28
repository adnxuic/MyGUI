"""Canonical Axes-layout helpers shared by GUI tests."""

from mygui.figuremodify.axes_layout import (
    AxesCellSpec,
    AxesLayoutSpec,
    AxesViewSpec,
)


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


def create_twin_axes_pair(canvas):
    """Create a primary axes with a twinned companion."""

    ids = canvas.create_axes_layout(
        AxesLayoutSpec(
            1,
            1,
            (
                AxesCellSpec(
                    0,
                    0,
                    primary=canvas.axes_layout_service.creation_view_defaults(),
                    right_y=AxesViewSpec(),
                ),
            ),
        )
    )
    return ids[0], ids[1]
