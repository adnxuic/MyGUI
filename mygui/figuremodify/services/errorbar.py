"""Error Bar data resolution, stable runtime, and table-driven refresh."""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.container import ErrorbarContainer
from matplotlib.lines import Line2D

from mygui.database import (
    ColumnRef,
    ColumnType,
    DataPreprocessSpec,
    resolve_preprocessed_pair,
)
from mygui.figuremodify.components import (
    ChangeStatus,
    ComponentChange,
    ComponentMutation,
    ComponentRegistry,
    ErrorBarData,
    ErrorBarController,
    ObserverFailure,
)
from mygui.figuremodify.components.property_values import (
    DEFAULT_ERROR_SPEC,
    error_spec_references,
    marker_value,
    normalize_error_spec,
)
from mygui.figuremodify.style_base.color_models import normalize_color
from ._helpers import (
    _column_ref,
    _controller,
    _notices,
    _rejected,
    _warning,
)


def resolve_errorbar_data(
    repository,
    x_ref: ColumnRef | dict[str, Any],
    y_ref: ColumnRef | dict[str, Any],
    xerr: Any,
    yerr: Any,
    preprocess: DataPreprocessSpec | dict[str, Any] | None,
) -> ErrorBarData:
    """Resolve aligned X/Y values plus masked error magnitudes atomically.

    X/Y keep the existing ``DataPreprocessSpec`` pipeline; error columns are
    never transformed and only contribute absolute magnitudes aligned to the
    post-preprocessing row mask.  Rows excluded by the mask neither draw nor
    validate their error values; any invalid magnitude on a drawable row
    rejects the whole operation.
    """

    x_ref = _column_ref(x_ref)
    y_ref = _column_ref(y_ref)
    xerr_spec = normalize_error_spec(
        xerr if xerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
    )
    yerr_spec = normalize_error_spec(
        yerr if yerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
    )
    spec = DataPreprocessSpec.from_dict(
        preprocess if preprocess is not None else DataPreprocessSpec().to_dict()
    )
    pair = resolve_preprocessed_pair(
        repository,
        x_ref,
        y_ref,
        spec,
        preserve_gaps=False,
    )
    mask = np.asarray(pair.valid_mask, dtype=bool)
    raw_length = int(len(mask))
    drawable = int(mask.sum())
    x_values = np.asarray(pair.x)
    y_values = np.asarray(pair.y)
    x_error = _resolve_error_dimension(
        repository, xerr_spec, mask, raw_length, drawable, "xerr"
    )
    y_error = _resolve_error_dimension(
        repository, yerr_spec, mask, raw_length, drawable, "yerr"
    )
    return ErrorBarData(x_values, y_values, x_error, y_error)


def _resolve_error_dimension(
    repository,
    spec: dict[str, Any],
    mask: np.ndarray,
    raw_length: int,
    drawable: int,
    name: str,
) -> np.ndarray | None:
    """Return one Matplotlib-shaped error array or ``None`` for no errors."""

    kind = spec["kind"]
    if kind == "none":
        return None
    if kind == "constant":
        return np.vstack(
            [
                np.full(drawable, float(spec["minus"]), dtype=float),
                np.full(drawable, float(spec["plus"]), dtype=float),
            ]
        )
    if kind == "symmetric_ref":
        column = _read_error_column(repository, spec["ref"], raw_length, name)
        values = column[mask]
        _validate_error_values(values, name)
        return values
    minus = _read_error_column(repository, spec["minus_ref"], raw_length, name)
    plus = _read_error_column(repository, spec["plus_ref"], raw_length, name)
    values = np.vstack([minus[mask], plus[mask]])
    _validate_error_values(values, name)
    return values


def _read_error_column(
    repository,
    raw_ref: dict[str, Any],
    raw_length: int,
    name: str,
) -> np.ndarray:
    """Read one numeric error column aligned to the raw X/Y row count."""

    ref = _column_ref(raw_ref)
    if not repository.has_ref(ref):
        raise ValueError(f"Error Bar {name} column was removed.")
    sheet = repository.sheet(ref.project_id, ref.sheet_id)
    if sheet.column(ref.column_id).type is not ColumnType.NUMBER:
        raise ValueError(f"Error Bar {name} column must be numeric.")
    raw = np.asarray(repository.series(ref))
    if len(raw) < raw_length:
        raise ValueError(
            f"Error Bar {name} column is not row-aligned with its X/Y source."
        )
    try:
        return raw[:raw_length].astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Error Bar {name} column must contain numeric values."
        ) from exc


def _validate_error_values(values: np.ndarray, name: str) -> None:
    """Reject non-finite or negative magnitudes on drawable rows."""

    if not values.size:
        return
    if not np.isfinite(values).all() or bool((values < 0).any()):
        raise ValueError(
            f"Error Bar {name} must contain finite non-negative magnitudes."
        )


def errorbar_properties_from_appearance(
    appearance: Any,
    *,
    label: str,
) -> dict[str, Any]:
    """Build one complete Error Bar property record from resolved values."""

    from mygui.figuremodify.components.property_values import (
        normalize_error_every,
    )
    from mygui.figuremodify.components.controllers import (
        _line_pattern,
        _marker_spec,
    )

    properties = ErrorBarController.default_properties()
    properties.update(
        {
            "label": str(label),
            "color": appearance.color,
            "linestyle": _line_pattern(appearance.linestyle),
            "linewidth": float(appearance.linewidth),
            "marker": _marker_spec(appearance.marker),
            "markersize": float(appearance.markersize),
            "markeredgewidth": float(appearance.markeredgewidth),
            "markerfacecolor": appearance.color,
            "markeredgecolor": appearance.color,
            "markerfacecoloralt": str(appearance.markerfacecoloralt),
            "fillstyle": str(appearance.fillstyle),
            "drawstyle": str(appearance.drawstyle),
            "antialiased": bool(appearance.antialiased),
            "ecolor": appearance.ecolor,
            "elinewidth": float(appearance.elinewidth),
            "capsize": float(appearance.capsize),
            "capthick": float(appearance.capthick),
            "error_linestyle": _line_pattern(appearance.error_linestyle),
            "error_capstyle": (
                None
                if appearance.error_capstyle is None
                else str(appearance.error_capstyle)
            ),
            "error_antialiased": bool(appearance.error_antialiased),
            "errorevery": normalize_error_every(appearance.errorevery),
            "lolims": bool(appearance.lolims),
            "uplims": bool(appearance.uplims),
            "xlolims": bool(appearance.xlolims),
            "xuplims": bool(appearance.xuplims),
            "barsabove": bool(appearance.barsabove),
        }
    )
    return properties


@dataclass(slots=True)
class _ArtistEntry:
    """One pinned artist location for reversible container swaps."""

    artist: Any
    owner: list[Any] | None
    index: int


@dataclass(slots=True)
class ErrorBarSwapMemento:
    """Everything needed to undo one transactional runtime rebuild."""

    old_container: ErrorbarContainer
    old_container_index: int
    old_artists: tuple[_ArtistEntry, ...]
    new_artists: tuple[_ArtistEntry, ...]
    old_data: ErrorBarData
    old_properties: dict[str, Any]
    old_x_inverted: bool
    old_y_inverted: bool


def _artist_entry(artist: Any) -> _ArtistEntry:
    """Pin one artist's owner list and position for exact restoration."""

    owner = None
    remove_method = getattr(artist, "_remove_method", None)
    candidate = getattr(remove_method, "__self__", None)
    if isinstance(candidate, list) and artist in candidate:
        owner = candidate
        index = candidate.index(artist)
    else:
        index = -1
    return _ArtistEntry(artist, owner, index)


def _line_style_value(spec: dict[str, Any]) -> Any:
    """Convert a tagged line pattern into a Matplotlib linestyle value."""

    if spec.get("kind") == "custom":
        return (float(spec["offset"]), tuple(spec["dashes"]))
    return str(spec.get("value", "-"))


class ErrorBarRuntime:
    """Stable runtime wrapper around one Matplotlib ErrorbarContainer.

    The runtime object itself never changes identity, so the ComponentLocator
    binding survives every transactional rebuild.  Like ``Field2DRuntime``,
    instances do not support weak references, so the ComponentLocator keeps
    its strong-target binding alive for the component's whole lifetime.  When
    either dimension carries errors the cap artists always exist — zero sized
    while ``capsize`` is zero — so a later capsize increase never changes the
    component structure.
    """

    __slots__ = (
        "_axes",
        "_container",
        "_data",
        "_properties",
        "_gid",
        "_x_inverted",
        "_y_inverted",
    )

    def __init__(
        self,
        axes: Axes,
        container: ErrorbarContainer,
        *,
        data: ErrorBarData,
        properties: dict[str, Any],
        gid: str | None = None,
    ):
        self._axes = axes
        self._container = container
        self._data = data
        self._properties = deepcopy(properties)
        self._gid = gid
        self._x_inverted = bool(axes.xaxis.get_inverted())
        self._y_inverted = bool(axes.yaxis.get_inverted())
        self._container.set_label(str(properties.get("label", "")))

    @property
    def axes(self) -> Axes:
        """Return the owning Matplotlib Axes."""

        return self._axes

    @property
    def container(self) -> ErrorbarContainer:
        """Return the live Matplotlib errorbar container."""

        return self._container

    @property
    def data_line(self) -> Line2D:
        """Return the data line inside the container."""

        return self._container[0]

    @property
    def caplines(self) -> tuple[Line2D, ...]:
        """Return the cap artists inside the container."""

        return tuple(self._container[1])

    @property
    def barlinecols(self) -> tuple[Any, ...]:
        """Return the error-bar line collections inside the container."""

        return tuple(self._container[2])

    @property
    def data(self) -> ErrorBarData:
        """Return a copy of the current drawable arrays."""

        return ErrorBarData(
            np.asarray(self._data.x).copy(),
            np.asarray(self._data.y).copy(),
            None if self._data.xerr is None else np.asarray(self._data.xerr).copy(),
            None if self._data.yerr is None else np.asarray(self._data.yerr).copy(),
        )

    @property
    def is_empty(self) -> bool:
        """Return whether the component currently draws no rows."""

        return len(np.asarray(self._data.x)) == 0

    @property
    def has_errors(self) -> bool:
        """Return whether either dimension carries errors."""

        return self._data.xerr is not None or self._data.yerr is not None

    @property
    def limit_arrows_active(self) -> bool:
        """Return whether any limit-arrow switch is enabled."""

        return any(
            bool(self._properties.get(key, False))
            for key in ("lolims", "uplims", "xlolims", "xuplims")
        )

    def direction_changed(self) -> bool:
        """Return whether either Axes direction flipped since the last build.

        Matplotlib 3.9 picks the limit-arrow caret direction from the axis
        inversion state at container creation time, so a direction flip makes
        the drawn arrows stale until the container is rebuilt.
        """

        return self._x_inverted != bool(
            self._axes.xaxis.get_inverted()
        ) or self._y_inverted != bool(self._axes.yaxis.get_inverted())

    def iter_artists(self) -> tuple[Any, ...]:
        """Return every Matplotlib artist owned by this component."""

        return (self.data_line, *self.caplines, *self.barlinecols)

    def set_gid(self, gid: str | None) -> None:
        """Apply the stable component gid to every owned artist."""

        self._gid = gid
        for artist in self.iter_artists():
            artist.set_gid(gid)

    # ------------------------------------------------------------------
    # Transactional rebuild
    # ------------------------------------------------------------------
    def rebuild(
        self,
        *,
        data: ErrorBarData,
        properties: dict[str, Any],
    ) -> ErrorBarSwapMemento:
        """Atomically replace the live container with a validated candidate.

        The candidate is created and validated first; the old container and
        artists are only detached once the candidate is live.  The returned
        memento restores the exact previous objects, owner lists, and indices
        on rollback, and may be finalized after the caller commits.
        """

        old_container = self._container
        old_data = self._data
        old_properties = deepcopy(self._properties)
        old_x_inverted = self._x_inverted
        old_y_inverted = self._y_inverted
        old_entries = tuple(
            _artist_entry(artist) for artist in self.iter_artists()
        )
        old_container_entry = _artist_entry(old_container)
        candidate = create_errorbar_container(
            self._axes,
            data,
            properties,
        )
        candidate_entries = tuple(
            _artist_entry(artist) for artist in _candidate_artists(candidate)
        )
        try:
            _validate_candidate(candidate, data)
            _swap_container(
                self._axes,
                old_container,
                old_container_entry,
                candidate,
            )
        except Exception:
            _detach_entries(candidate_entries)
            _detach_container(self._axes, candidate)
            raise
        self._container = candidate
        self._data = data
        self._properties = deepcopy(properties)
        self._x_inverted = bool(self._axes.xaxis.get_inverted())
        self._y_inverted = bool(self._axes.yaxis.get_inverted())
        self._container.set_label(str(properties.get("label", "")))
        if self._gid is not None:
            for artist in self.iter_artists():
                artist.set_gid(self._gid)
        return ErrorBarSwapMemento(
            old_container=old_container,
            old_container_index=old_container_entry.index,
            old_artists=old_entries,
            new_artists=candidate_entries,
            old_data=old_data,
            old_properties=old_properties,
            old_x_inverted=old_x_inverted,
            old_y_inverted=old_y_inverted,
        )

    def restore_swap(self, memento: ErrorBarSwapMemento) -> None:
        """Undo one committed rebuild by restoring the previous container."""

        current_entries = tuple(
            _artist_entry(artist) for artist in self.iter_artists()
        )
        _detach_entries(current_entries)
        _detach_container(self._axes, self._container)
        _restore_entries(memento.old_artists)
        _restore_container(self._axes, memento)
        self._container = memento.old_container
        self._data = memento.old_data
        self._properties = deepcopy(memento.old_properties)
        self._x_inverted = bool(memento.old_x_inverted)
        self._y_inverted = bool(memento.old_y_inverted)

    def finalize_swap(self, memento: ErrorBarSwapMemento) -> None:
        """Discard the rollback memento after the caller has committed."""

        del memento.old_container
        del memento.old_artists

    # ------------------------------------------------------------------
    # Composite property surface (used by ErrorBarController PropertySpecs)
    # ------------------------------------------------------------------
    def get_label(self) -> str:
        return str(self._container.get_label())

    def set_label(self, value: str) -> None:
        self._container.set_label(str(value))
        self._properties["label"] = str(value)

    def get_color(self) -> str:
        return Line2D.get_color(self.data_line)

    def set_color(self, value: str) -> None:
        self.data_line.set_color(value)
        self._properties["color"] = str(value)

    def get_linestyle(self) -> dict[str, Any]:
        return deepcopy(self._properties["linestyle"])

    def set_linestyle(self, value: dict[str, Any]) -> None:
        self.data_line.set_linestyle(_line_style_value(value))
        self._properties["linestyle"] = deepcopy(value)

    def get_linewidth(self) -> float:
        return float(self.data_line.get_linewidth())

    def set_linewidth(self, value: float) -> None:
        self.data_line.set_linewidth(float(value))
        self._properties["linewidth"] = float(value)

    def get_marker(self) -> dict[str, Any]:
        return deepcopy(self._properties["marker"])

    def set_marker(self, value: dict[str, Any]) -> None:
        from mygui.figuremodify.components.property_values import marker_value

        self.data_line.set_marker(marker_value(value))
        self._properties["marker"] = deepcopy(value)

    def get_markersize(self) -> float:
        return float(self.data_line.get_markersize())

    def set_markersize(self, value: float) -> None:
        self.data_line.set_markersize(float(value))
        self._properties["markersize"] = float(value)

    def get_markerfacecolor(self) -> str:
        return Line2D.get_markerfacecolor(self.data_line)

    def set_markerfacecolor(self, value: str) -> None:
        self.data_line.set_markerfacecolor(value)
        self._properties["markerfacecolor"] = str(value)

    def get_markeredgecolor(self) -> str:
        return Line2D.get_markeredgecolor(self.data_line)

    def set_markeredgecolor(self, value: str) -> None:
        self.data_line.set_markeredgecolor(value)
        self._properties["markeredgecolor"] = str(value)

    def get_markeredgewidth(self) -> float:
        return float(self.data_line.get_markeredgewidth())

    def set_markeredgewidth(self, value: float) -> None:
        # Independent from capthick: this only styles the data-line markers.
        self.data_line.set_markeredgewidth(float(value))
        self._properties["markeredgewidth"] = float(value)

    def get_markerfacecoloralt(self) -> str:
        return str(self.data_line.get_markerfacecoloralt())

    def set_markerfacecoloralt(self, value: str) -> None:
        self.data_line.set_markerfacecoloralt(str(value))
        self._properties["markerfacecoloralt"] = str(value)

    def get_fillstyle(self) -> str:
        return str(self.data_line.get_fillstyle())

    def set_fillstyle(self, value: str) -> None:
        self.data_line.set_fillstyle(str(value))
        self._properties["fillstyle"] = str(value)

    def get_drawstyle(self) -> str:
        return str(self.data_line.get_drawstyle())

    def set_drawstyle(self, value: str) -> None:
        self.data_line.set_drawstyle(str(value))
        self._properties["drawstyle"] = str(value)

    def get_antialiased(self) -> bool:
        return bool(self.data_line.get_antialiased())

    def set_antialiased(self, value: bool) -> None:
        self.data_line.set_antialiased(bool(value))
        self._properties["antialiased"] = bool(value)

    def get_ecolor(self) -> str:
        colors = self.barlinecols[0].get_color() if self.barlinecols else None
        if colors is not None and len(colors):
            return normalize_color(colors[0])
        if self.caplines:
            return normalize_color(self.caplines[0].get_color())
        return normalize_color(self._properties.get("ecolor", "#1f77b4"))

    def set_ecolor(self, value: str) -> None:
        for collection in self.barlinecols:
            collection.set_color(value)
        for cap in self.caplines:
            cap.set_color(value)
        self._properties["ecolor"] = str(value)

    def get_elinewidth(self) -> float:
        if self.barlinecols:
            widths = self.barlinecols[0].get_linewidths()
            if len(widths):
                return float(widths[0])
        return float(self._properties.get("elinewidth", 1.5))

    def set_elinewidth(self, value: float) -> None:
        for collection in self.barlinecols:
            collection.set_linewidth(float(value))
        self._properties["elinewidth"] = float(value)

    def get_capsize(self) -> float:
        if self.caplines:
            return float(self.caplines[0].get_markersize()) / 2.0
        return float(self._properties.get("capsize", 0.0))

    def set_capsize(self, value: float) -> None:
        for cap in self.caplines:
            cap.set_markersize(float(value) * 2.0)
        self._properties["capsize"] = float(value)

    def get_capthick(self) -> float:
        if self.caplines:
            return float(self.caplines[0].get_markeredgewidth())
        return float(self._properties.get("capthick", 1.0))

    def set_capthick(self, value: float) -> None:
        for cap in self.caplines:
            cap.set_markeredgewidth(float(value))
        self._properties["capthick"] = float(value)

    def get_error_linestyle(self) -> dict[str, Any]:
        return deepcopy(self._properties["error_linestyle"])

    def set_error_linestyle(self, value: dict[str, Any]) -> None:
        pattern = _line_style_value(value)
        for collection in self.barlinecols:
            collection.set_linestyle(pattern)
        self._properties["error_linestyle"] = deepcopy(value)

    def get_error_capstyle(self) -> str | None:
        return self._properties.get("error_capstyle")

    def set_error_capstyle(self, value: str | None) -> None:
        for collection in self.barlinecols:
            if value is None:
                # Mirror the Matplotlib 3.9 unset default exactly as the
                # Scatter controller restores it.
                collection._capstyle = None
                collection.stale = True
            else:
                collection.set_capstyle(str(value))
        self._properties["error_capstyle"] = None if value is None else str(value)

    def get_error_antialiased(self) -> bool:
        return bool(self._properties.get("error_antialiased", True))

    def set_error_antialiased(self, value: bool) -> None:
        for collection in self.barlinecols:
            collection.set_antialiased(bool(value))
        for cap in self.caplines:
            cap.set_antialiased(bool(value))
        self._properties["error_antialiased"] = bool(value)

    def get_errorevery(self) -> dict[str, Any]:
        return deepcopy(self._properties["errorevery"])

    def set_errorevery(self, value: dict[str, Any]) -> None:
        # Structural: keep the live snapshot unchanged until the candidate
        # container swap commits.  This lets rollback distinguish the old
        # structure and restore its exact artist identities.
        del value

    def _get_limit_flag(self, key: str) -> bool:
        return bool(self._properties.get(key, False))

    def _set_limit_flag(self, key: str, value: bool) -> None:
        # Structural: the candidate rebuild owns the live value atomically.
        del key, value

    def get_lolims(self) -> bool:
        return self._get_limit_flag("lolims")

    def set_lolims(self, value: bool) -> None:
        self._set_limit_flag("lolims", value)

    def get_uplims(self) -> bool:
        return self._get_limit_flag("uplims")

    def set_uplims(self, value: bool) -> None:
        self._set_limit_flag("uplims", value)

    def get_xlolims(self) -> bool:
        return self._get_limit_flag("xlolims")

    def set_xlolims(self, value: bool) -> None:
        self._set_limit_flag("xlolims", value)

    def get_xuplims(self) -> bool:
        return self._get_limit_flag("xuplims")

    def set_xuplims(self, value: bool) -> None:
        self._set_limit_flag("xuplims", value)

    def get_barsabove(self) -> bool:
        return bool(self._properties.get("barsabove", False))

    def set_barsabove(self, value: bool) -> None:
        self._properties["barsabove"] = bool(value)
        self._apply_zorders()

    def get_alpha(self) -> float | None:
        return self.data_line.get_alpha()

    def set_alpha(self, value: float | None) -> None:
        for artist in self.iter_artists():
            artist.set_alpha(value)
        self._properties["alpha"] = value

    def get_visible(self) -> bool:
        return bool(self.data_line.get_visible())

    def set_visible(self, value: bool) -> None:
        for artist in self.iter_artists():
            artist.set_visible(bool(value))
        self._properties["visible"] = bool(value)

    def get_zorder(self) -> float:
        return float(self._properties.get("zorder", 2.0))

    def set_zorder(self, value: float) -> None:
        self._properties["zorder"] = float(value)
        self._apply_zorders()

    def get_clip_on(self) -> bool:
        return bool(self.data_line.get_clip_on())

    def set_clip_on(self, value: bool) -> None:
        for artist in self.iter_artists():
            artist.set_clip_on(bool(value))
        self._properties["clip_on"] = bool(value)

    def _apply_zorders(self) -> None:
        base = float(self._properties.get("zorder", 2.0))
        offset = -0.1 if self._properties.get("barsabove") else 0.1
        for collection in self.barlinecols:
            collection.set_zorder(base)
        for cap in self.caplines:
            cap.set_zorder(base)
        self.data_line.set_zorder(base + offset)


def _candidate_artists(container: ErrorbarContainer) -> tuple[Any, ...]:
    """Return every artist a freshly created candidate container owns."""

    return (container[0], *tuple(container[1]), *tuple(container[2]))


def _validate_candidate(
    container: ErrorbarContainer,
    data: ErrorBarData,
) -> None:
    """Verify the candidate container matches the requested drawable data."""

    data_line = container[0]
    if data_line is None:
        raise ValueError("Error Bar candidate is missing its data line.")
    expected = len(np.asarray(data.x))
    if len(data_line.get_xdata()) != expected:
        raise ValueError("Error Bar candidate data length is invalid.")
    expected_bars = (1 if data.xerr is not None else 0) + (
        1 if data.yerr is not None else 0
    )
    if len(tuple(container[2])) != expected_bars:
        raise ValueError("Error Bar candidate error collections are invalid.")


def create_errorbar_container(
    axes: Axes,
    data: ErrorBarData,
    properties: dict[str, Any],
) -> ErrorbarContainer:
    """Create and attach one candidate container, mirroring 3.9 structure.

    This is the single creation entry shared by the Canvas creation stager
    and transactional runtime rebuilds so both produce identical structure,
    including zero-size cap artists whenever either dimension has errors.
    ``markeredgewidth`` is deliberately omitted from the Matplotlib kwargs —
    3.9 forwards it to the caps and would override ``capthick`` — so the data
    marker edge width is applied to the data line after creation instead.
    """

    line_kwargs: dict[str, Any] = {
        "color": properties["color"],
        "linestyle": _line_style_value(properties["linestyle"]),
        "linewidth": float(properties["linewidth"]),
        "marker": marker_value(properties["marker"]),
        "markersize": float(properties["markersize"]),
        "markerfacecolor": properties["markerfacecolor"],
        "markeredgecolor": properties["markeredgecolor"],
        "markerfacecoloralt": str(properties.get("markerfacecoloralt", "none")),
        "fillstyle": str(properties.get("fillstyle", "full")),
        "drawstyle": str(properties.get("drawstyle", "default")),
        "antialiased": bool(properties.get("antialiased", True)),
    }
    alpha = properties.get("alpha")
    errorbar_kwargs: dict[str, Any] = {
        **line_kwargs,
        "ecolor": properties["ecolor"],
        "elinewidth": float(properties["elinewidth"]),
        "capsize": float(properties["capsize"]),
        "capthick": float(properties["capthick"]),
        "errorevery": _error_every_value(properties.get("errorevery")),
        "lolims": bool(properties.get("lolims", False)),
        "uplims": bool(properties.get("uplims", False)),
        "xlolims": bool(properties.get("xlolims", False)),
        "xuplims": bool(properties.get("xuplims", False)),
        "barsabove": bool(properties.get("barsabove", False)),
        "zorder": float(properties.get("zorder", 2.0)),
        "clip_on": bool(properties.get("clip_on", True)),
        "label": str(properties.get("label", "")),
    }
    if alpha is not None:
        errorbar_kwargs["alpha"] = float(alpha)
    # Matplotlib 3.9 errorbar() queues an internal autoscale request, which
    # would later clobber explicit Axes limits (including a just-applied
    # reversed direction).  Restore the pre-call staleness so limit updates
    # stay under the application's own RELIM/AUTOSCALE impacts.
    stale_viewlims_before = dict(getattr(axes, "_stale_viewlims", {}))
    container = axes.errorbar(
        np.asarray(data.x),
        np.asarray(data.y),
        xerr=None if data.xerr is None else np.asarray(data.xerr),
        yerr=None if data.yerr is None else np.asarray(data.yerr),
        **errorbar_kwargs,
    )
    for name, stale in stale_viewlims_before.items():
        axes._stale_viewlims[name] = stale
    visible = bool(properties.get("visible", True))
    for artist in _candidate_artists(container):
        artist.set_visible(visible)
        artist.set_clip_on(bool(properties.get("clip_on", True)))
    container[0].set_markeredgewidth(float(properties["markeredgewidth"]))
    _apply_error_collection_styles(container, properties)
    caplines = tuple(container[1])
    if not caplines and (data.xerr is not None or data.yerr is not None):
        # Matplotlib 3.9 only creates cap artists when capsize > 0.  Keep
        # zero-sized caps so the component structure is independent of the
        # persisted capsize value.
        caplines = _create_zero_size_caps(axes, data, properties)
        owner = axes.containers
        replacement = ErrorbarContainer(
            (container[0], caplines, tuple(container[2])),
            has_xerr=container.has_xerr,
            has_yerr=container.has_yerr,
            label=str(properties.get("label", "")),
        )
        owner[owner.index(container)] = replacement
        container = replacement
    return container


def _error_every_value(spec: Any) -> Any:
    """Convert the tagged errorevery spec into the Matplotlib argument."""

    from mygui.figuremodify.components.property_values import (
        normalize_error_every,
    )

    normalized = normalize_error_every(
        spec if spec is not None else {"kind": "all"}
    )
    if normalized["kind"] == "all":
        return 1
    return (int(normalized["start"]), int(normalized["step"]))


def _apply_error_collection_styles(
    container: ErrorbarContainer,
    properties: dict[str, Any],
) -> None:
    """Apply the error-dimension styles Matplotlib does not accept as kwargs.

    The 3.9 ``errorbar`` bars never inherit the data-line linestyle, and the
    cap style / error antialiasing have no keyword parameters, so they are
    written onto the collections and caps explicitly.
    """

    error_linestyle = _line_style_value(
        properties.get("error_linestyle", {"kind": "preset", "value": "-"})
    )
    error_antialiased = bool(properties.get("error_antialiased", True))
    for collection in tuple(container[2]):
        collection.set_linestyle(error_linestyle)
        collection.set_antialiased(error_antialiased)
        capstyle = properties.get("error_capstyle")
        if capstyle is None:
            # Matplotlib 3.9 rejects set_capstyle(None); the documented
            # default state is the unset private attribute, exactly as the
            # Scatter controller restores it.
            collection._capstyle = None
            collection.stale = True
        else:
            collection.set_capstyle(str(capstyle))
    for cap in tuple(container[1]):
        cap.set_antialiased(error_antialiased)


def _create_zero_size_caps(
    axes: Axes,
    data: ErrorBarData,
    properties: dict[str, Any],
) -> tuple[Line2D, ...]:
    """Create marker-only cap artists matching the 3.9 cap structure."""

    x_values = np.asarray(data.x, dtype=float)
    y_values = np.asarray(data.y, dtype=float)
    every = _error_every_value(properties.get("errorevery"))
    if isinstance(every, tuple):
        start, step = every
    else:
        start, step = 0, int(every)
    selected = np.arange(len(x_values), dtype=int)[start::step]
    x_values = x_values[selected]
    y_values = y_values[selected]
    style = {
        "linestyle": "none",
        "color": properties["ecolor"],
        "markeredgewidth": float(properties["capthick"]),
        "markersize": 0.0,
        "antialiased": bool(properties.get("error_antialiased", True)),
        "zorder": float(properties.get("zorder", 2.0)),
        "clip_on": bool(properties.get("clip_on", True)),
        "visible": bool(properties.get("visible", True)),
    }
    alpha = properties.get("alpha")
    if alpha is not None:
        style["alpha"] = float(alpha)
    caps: list[Line2D] = []
    if data.yerr is not None:
        errors = np.asarray(data.yerr, dtype=float)[..., selected]
        minus = -errors[0] if errors.ndim == 2 else -errors
        plus = errors[1] if errors.ndim == 2 else errors
        for offset in (minus, plus):
            cap = Line2D(x_values, y_values + offset, marker="_", **deepcopy(style))
            axes.add_line(cap)
            caps.append(cap)
    if data.xerr is not None:
        errors = np.asarray(data.xerr, dtype=float)[..., selected]
        minus = -errors[0] if errors.ndim == 2 else -errors
        plus = errors[1] if errors.ndim == 2 else errors
        for offset in (minus, plus):
            cap = Line2D(x_values + offset, y_values, marker="|", **deepcopy(style))
            axes.add_line(cap)
            caps.append(cap)
    return tuple(caps)


def _detach_entries(entries: tuple[_ArtistEntry, ...]) -> None:
    """Remove artists from their owner lists, tolerating prior detachment."""

    for entry in reversed(entries):
        artist = entry.artist
        owner = getattr(
            getattr(artist, "_remove_method", None), "__self__", None
        )
        if isinstance(owner, list) and artist in owner:
            owner.remove(artist)


def _detach_container(axes: Axes, container: ErrorbarContainer) -> None:
    """Remove one container from the Axes container list."""

    owner = axes.containers
    if container in owner:
        owner.remove(container)


def _swap_container(
    axes: Axes,
    old_container: ErrorbarContainer,
    old_entry: _ArtistEntry,
    candidate: ErrorbarContainer,
) -> int:
    """Detach the old container and artists, leaving the candidate live."""

    _detach_entries(
        tuple(
            _artist_entry(artist)
            for artist in _candidate_artists(old_container)
        )
    )
    _detach_container(axes, old_container)
    owner = axes.containers
    return owner.index(candidate)


def _restore_entries(entries: tuple[_ArtistEntry, ...]) -> None:
    """Re-insert detached artists at their recorded positions."""

    for entry in sorted(entries, key=lambda item: item.index):
        artist = entry.artist
        if entry.owner is None or entry.index < 0:
            continue
        if artist not in entry.owner:
            entry.owner.insert(min(entry.index, len(entry.owner)), artist)


def _restore_container(axes: Axes, memento: ErrorBarSwapMemento) -> None:
    """Re-insert the previous container at its recorded position."""

    owner = axes.containers
    if memento.old_container not in owner:
        owner.insert(
            min(memento.old_container_index, len(owner)),
            memento.old_container,
        )


class ErrorBarDataService:
    """Resolve table-driven Error Bar data and refresh components atomically."""

    def __init__(self, repository, registry: ComponentRegistry):
        self.repository = repository
        self.registry = registry
        self._observer_failures: list[ObserverFailure] = []

    def destroy_runtime(self, runtime: Any) -> None:
        """Detach one not-yet-committed runtime during rollback.

        Rollback callbacks must never mask the original transaction failure,
        so best-effort detachment errors are swallowed after logging.
        """

        import logging

        try:
            axes = runtime.axes
            for artist in tuple(runtime.iter_artists()):
                try:
                    artist.remove()
                except (RuntimeError, ValueError):
                    pass
            owner = getattr(axes, "containers", None)
            container = runtime.container
            if isinstance(owner, list) and container in owner:
                owner.remove(container)
        except Exception:
            logging.getLogger(__name__).exception(
                "Error Bar runtime rollback detachment failed"
            )

    def drain_observer_failures(self) -> tuple[ObserverFailure, ...]:
        """Return and clear refresh failures isolated from table commits."""

        failures, self._observer_failures = (
            tuple(self._observer_failures),
            [],
        )
        return failures

    @staticmethod
    def refs_for(controller) -> tuple[ColumnRef, ColumnRef]:
        """Return the X/Y data references stored by an Error Bar."""

        data = controller.state.data
        return (
            _column_ref(data["x_ref"]),
            _column_ref(data["y_ref"]),
        )

    @staticmethod
    def preprocess_for(controller) -> DataPreprocessSpec:
        """Return the persisted preprocessing specification."""

        return DataPreprocessSpec.from_dict(controller.state.data["preprocess"])

    def _resolve(
        self,
        controller: ErrorBarController,
        data: dict[str, Any],
    ) -> ErrorBarData:
        """Resolve drawable arrays for one candidate data record."""

        return resolve_errorbar_data(
            self.repository,
            data["x_ref"],
            data["y_ref"],
            data.get("xerr"),
            data.get("yerr"),
            data.get("preprocess"),
        )

    def configure(
        self,
        component,
        *,
        x_ref: ColumnRef | dict[str, Any],
        y_ref: ColumnRef | dict[str, Any],
        xerr: Any,
        yerr: Any,
        preprocess: DataPreprocessSpec | dict[str, Any] | None = None,
        force_refresh: bool = False,
    ) -> ComponentChange:
        """Atomically update all five data fields and rebuild the runtime."""

        controller = _controller(self.registry, component, ErrorBarController)
        try:
            x_ref = _column_ref(x_ref)
            y_ref = _column_ref(y_ref)
            spec = DataPreprocessSpec.from_dict(
                preprocess
                if preprocess is not None
                else controller.state.data["preprocess"]
            )
            data = deepcopy(controller.state.data)
            data.update(
                x_ref=x_ref.to_dict(),
                y_ref=y_ref.to_dict(),
                xerr=normalize_error_spec(
                    xerr if xerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
                ),
                yerr=normalize_error_spec(
                    yerr if yerr is not None else deepcopy(DEFAULT_ERROR_SPEC)
                ),
                preprocess=spec.to_dict(),
            )
            drawable = self._resolve(controller, data)
        except Exception as exc:
            return _rejected(controller, str(exc))
        if not force_refresh and data == controller.state.data:
            state = controller.state
            return ComponentChange(
                controller.component_id,
                None,
                state,
                state,
                ChangeStatus.NOOP,
            )
        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                data=data,
                runtime_data=drawable,
            )
        )
        return self._with_warnings(change, drawable)

    def refresh(self, component) -> ComponentChange:
        """Refresh the component from its current data references."""

        controller = _controller(self.registry, component, ErrorBarController)
        try:
            x_ref, y_ref = self.refs_for(controller)
        except Exception as exc:
            return _rejected(controller, str(exc))
        data = controller.state.data
        return self.configure(
            controller,
            x_ref=x_ref,
            y_ref=y_ref,
            xerr=data.get("xerr"),
            yerr=data.get("yerr"),
            preprocess=data.get("preprocess"),
            force_refresh=True,
        )

    def refresh_affected(
        self,
        changed_columns: Iterable[ColumnRef],
    ) -> list[ComponentChange]:
        """Refresh Error Bars whose references intersect changed columns."""

        changed = set(changed_columns)
        results: list[ComponentChange] = []
        with self.registry.batch_updates():
            for controller in self.registry.query(
                capabilities={"data_reference", "auto_refresh"}
            ):
                if not isinstance(controller, ErrorBarController):
                    continue
                try:
                    refs = set(self.refs_for(controller))
                    for key in ("xerr", "yerr"):
                        for raw in error_spec_references(
                            controller.state.data.get(key)
                        ):
                            refs.add(_column_ref(raw))
                except Exception as exc:
                    self._observer_failures.append(
                        ObserverFailure(
                            "ErrorBarDataService",
                            "data-reference",
                            exc,
                            component_id=controller.component_id,
                            reference=deepcopy(controller.state.data),
                        )
                    )
                    continue
                if not refs.intersection(changed):
                    continue
                results.append(self.refresh(controller))
        return results

    def apply_state(
        self,
        component,
        state,
    ) -> ComponentChange:
        """Replay one authoritative state through data rebuild and style."""

        controller = _controller(self.registry, component, ErrorBarController)
        data = deepcopy(dict(state.data))
        try:
            drawable = self._resolve(controller, data)
        except Exception as exc:
            return _rejected(controller, str(exc))
        change = controller.apply_mutation(
            ComponentMutation(
                controller.component_id,
                properties=deepcopy(dict(state.properties)),
                data=data,
                runtime_data=drawable,
            )
        )
        return change

    @staticmethod
    def _with_warnings(
        change: ComponentChange,
        drawable: ErrorBarData,
    ) -> ComponentChange:
        """Attach the standard empty-data warning notices."""

        notices = []
        if change.status is ChangeStatus.EMPTY:
            notices.append(
                _warning(
                    "Error Bar has no valid data yet; its editor and style "
                    "were kept."
                )
            )
        return _notices(change, *notices) if notices else change
