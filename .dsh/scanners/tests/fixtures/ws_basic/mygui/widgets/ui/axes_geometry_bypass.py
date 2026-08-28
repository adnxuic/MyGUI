"""Positive fixture for ARCH-AXES-GEOMETRY-BYPASS."""


def direct_axes_geometry_mutations(ax, target):
    ax.set_position([0.1, 0.1, 0.8, 0.8])
    target.set_subplotspec(None)
    target.set_in_layout(False)
    spec = ax._subplotspec
    return spec
