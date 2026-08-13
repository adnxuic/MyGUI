"""Generic transactional controller for Matplotlib figure components."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar

from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.figure import Figure

from .errors import (
    ComponentDeletedError,
    ComponentNotFoundError,
    ComponentValidationError,
)
from .locator import ComponentLocator
from .matplotlib_removal import MATPLOTLIB_REMOVAL, RemovalHandle
from .models import (
    ChangeStatus,
    ComponentChange,
    ComponentKind,
    ComponentMutation,
    ComponentRole,
    ComponentState,
    DeletionPolicy,
    KEEP_RUNTIME_DATA,
    PropertySpec,
    RestorePhase,
    UpdateImpact,
)

if TYPE_CHECKING:
    from .registry import ComponentRegistry


T = TypeVar("T")


def _values_equal(left: Any, right: Any) -> bool:
    """Compare scalar or array-like Matplotlib property values safely."""

    try:
        result = left == right
    except (TypeError, ValueError):
        return False
    all_values = getattr(result, "all", None)
    if callable(all_values):
        try:
            return bool(all_values())
        except (TypeError, ValueError):
            return False
    try:
        return bool(result)
    except (TypeError, ValueError):
        return False


def _refresh_legend(axes: Axes) -> None:
    """Rebuild an axes legend while retaining its user-visible state."""

    owner = getattr(axes, "_mygui_merged_legend_owner", None)
    if isinstance(owner, Axes):
        axes = owner
    legend = axes.get_legend()
    if legend is None:
        return
    visible = legend.get_visible()
    location = getattr(legend, "_loc", "best")
    ncols = getattr(legend, "_ncols", 1)
    frameon = legend.get_frame_on()
    frame = legend.get_frame()
    facecolor = frame.get_facecolor()
    edgecolor = frame.get_edgecolor()
    alpha = frame.get_alpha()
    title = legend.get_title().get_text()
    title_size = legend.get_title().get_fontsize()
    text_sizes = [text.get_fontsize() for text in legend.get_texts()]
    text_size = float(
        getattr(
            legend,
            "_mygui_fontsize",
            text_sizes[0] if text_sizes else 10.0,
        )
    )
    handles, labels = axes.get_legend_handles_labels()
    peer = getattr(axes, "_mygui_merged_legend_peer", None)
    if isinstance(peer, Axes) and peer in axes.figure.axes:
        peer_handles, peer_labels = peer.get_legend_handles_labels()
        handles = [*handles, *peer_handles]
        labels = [*labels, *peer_labels]
    legend.remove()
    if not handles:
        return
    try:
        rebuilt = axes.legend(
            handles,
            labels,
            loc=location,
            ncols=ncols,
            frameon=frameon,
        )
    except (TypeError, ValueError):
        rebuilt = axes.legend(
            handles,
            labels,
            loc="best",
            ncols=ncols,
            frameon=frameon,
        )
    rebuilt.set_visible(visible)
    rebuilt.get_frame().set_facecolor(facecolor)
    rebuilt.get_frame().set_edgecolor(edgecolor)
    rebuilt.get_frame().set_alpha(alpha)
    rebuilt.set_title(title, prop={"size": title_size})
    rebuilt._mygui_fontsize = text_size
    for text in rebuilt.get_texts():
        text.set_fontsize(text_size)


def update_subject_for(target: Any) -> Axes | Figure | None:
    """Update subject for."""

    if isinstance(target, Axes):
        return target
    if isinstance(target, Figure):
        return target
    if isinstance(target, Axis):
        return target.axes
    axes = getattr(target, "axes", None)
    if isinstance(axes, Axes):
        return axes
    figure = getattr(target, "figure", None)
    return figure if isinstance(figure, Figure) else None


def apply_update_impacts(
    subject: Axes | Figure | None, impacts: UpdateImpact
) -> None:
    """Apply update impacts."""

    if subject is None or impacts == UpdateImpact.NONE:
        return
    figure: Figure
    if isinstance(subject, Axes):
        if UpdateImpact.RELIM in impacts:
            subject.relim()
        if UpdateImpact.AUTOSCALE in impacts:
            subject.autoscale_view()
        if UpdateImpact.LEGEND in impacts:
            _refresh_legend(subject)
        figure = subject.figure
    else:
        figure = subject
    if UpdateImpact.REDRAW in impacts and figure.canvas is not None:
        figure.canvas.draw_idle()


class ComponentController(Generic[T]):
    """Base class for a live Matplotlib component.

    Subclasses describe properties with :class:`PropertySpec`.  Mutations use
    a validate/apply/commit transaction, and restore the previous artist state
    when a setter fails.
    """

    KIND: ClassVar[ComponentKind | None] = None
    ROLES: ClassVar[frozenset[ComponentRole]] = frozenset()
    PROPERTY_SPECS: ClassVar[tuple[PropertySpec, ...]] = ()
    CAPABILITIES: ClassVar[frozenset[str]] = frozenset()
    DELETION_POLICY: ClassVar[DeletionPolicy] = DeletionPolicy.FORBID
    DELETE_IMPACTS: ClassVar[UpdateImpact] = UpdateImpact.REDRAW
    RESTORE_PHASE: ClassVar[RestorePhase | None] = None

    def __init__(
        self,
        state: ComponentState,
        *,
        target: T | None = None,
        locator: ComponentLocator | None = None,
        registry: ComponentRegistry | None = None,
    ) -> None:
        specs = self.property_specs()
        unknown = set(state.properties) - set(specs)
        if unknown:
            raise ComponentValidationError(
                f"Unknown component properties: {sorted(unknown)!r}."
            )
        properties = self.default_properties()
        properties.update(state.properties)
        for key, spec in specs.items():
            if key in properties:
                properties[key] = spec.normalize(properties[key])
        self._state = state.clone(properties=properties)
        self._registry = registry
        self._locator = (
            registry.locator
            if registry is not None
            else locator or ComponentLocator()
        )
        self._deleted = False
        self._validate_controller_state(self._state)
        if target is not None:
            self._locator.bind(self._state.id, target)

    @property
    def component_id(self) -> str:
        """Return the stable component identifier."""

        return self._state.id

    @property
    def state(self) -> ComponentState:
        """Return an independent copy of the component state."""

        return self._state.clone()

    @property
    def deleted(self) -> bool:
        """Return whether this Controller has been deleted."""

        return self._deleted

    @classmethod
    def property_specs(cls) -> dict[str, PropertySpec]:
        """Return property specifications keyed by persistent field name."""

        return {spec.key: spec for spec in cls.PROPERTY_SPECS}

    @classmethod
    def default_properties(cls) -> dict[str, Any]:
        """Return the default properties."""

        return {
            spec.key: deepcopy(spec.default)
            for spec in cls.PROPERTY_SPECS
            if spec.persistent
        }

    @classmethod
    def capabilities(cls) -> frozenset[str]:
        """Return the capabilities."""

        return cls.CAPABILITIES | frozenset(cls.property_specs())

    def attach(
        self,
        registry: ComponentRegistry,
        locator: ComponentLocator,
    ) -> None:
        """Attach the controller to its registry and target locator."""

        self._registry = registry
        self._locator = locator

    def resolve_target(self) -> T:
        """Resolve the live Matplotlib target for a component."""

        if self._deleted:
            raise ComponentDeletedError(
                f"Component {self.component_id!r} has been deleted."
            )
        return self._locator.require(self._state)

    def read_state(self, *, strict: bool = False) -> ComponentState:
        """Read state."""

        target = self.resolve_target()
        properties = deepcopy(self._state.properties)
        for spec in self.PROPERTY_SPECS:
            if not spec.persistent:
                continue
            try:
                properties[spec.key] = spec.normalize(
                    self._read_property(target, spec)
                )
            except Exception:
                if strict:
                    raise
        return self._state.clone(properties=properties)

    def snapshot(self) -> ComponentState:
        """Return a serializable snapshot of the current state."""

        return self.read_state()

    def sync_from_target(self, *, strict: bool = False) -> ComponentState:
        """Commit the currently resolved artist properties as Controller state."""

        state = self.read_state(strict=strict)
        self._validate_controller_state(state)
        self._state = state.clone()
        return self.state

    def apply_mutation(
        self,
        mutation: ComponentMutation,
    ) -> ComponentChange:
        """Apply a property/data/drawable change as one transaction.

        Role services use this operation when serialized component data and
        transient Matplotlib data must never diverge.  ``set_property`` and
        ``apply_state`` remain convenient public operations for their narrower
        use cases.
        """

        before = self._safe_snapshot()
        if mutation.component_id != self.component_id:
            return self._rejected(
                None,
                before,
                "Component mutation id does not match the Controller.",
            )
        if self._deleted:
            return self._rejected(
                None,
                before,
                f"Component {self.component_id!r} is deleted.",
            )

        target: T | None = None
        applied: list[tuple[PropertySpec, Any]] = []
        runtime_snapshot: Any = KEEP_RUNTIME_DATA
        impacts = UpdateImpact.NONE
        property_key = None
        try:
            properties = deepcopy(
                before.properties
                if before is not None
                else self._state.properties
            )
            property_patch = dict(mutation.properties or {})
            if len(property_patch) == 1:
                property_key = next(iter(property_patch))
            specs = self.property_specs()
            unknown = set(property_patch) - set(specs)
            if unknown:
                raise ComponentValidationError(
                    f"Unknown component properties: {sorted(unknown)!r}."
                )
            for key, value in property_patch.items():
                properties[key] = specs[key].normalize(value)
            data = (
                deepcopy(dict(mutation.data))
                if mutation.data is not None
                else deepcopy(self._state.data)
            )
            candidate = self._state.clone(
                properties=properties,
                data=data,
            )
            self._validate_replacement(candidate)
            target = self.resolve_target()

            if mutation.runtime_data is not KEEP_RUNTIME_DATA:
                self._validate_runtime_data(
                    target,
                    mutation.runtime_data,
                    candidate,
                )
                runtime_snapshot = self._capture_runtime_data(target)

            for key in property_patch:
                spec = specs[key]
                previous = self._read_property(target, spec)
                value = properties[key]
                if _values_equal(previous, value):
                    continue
                self._write_property(target, spec, value)
                applied.append((spec, previous))
                impacts |= spec.impact

            if mutation.runtime_data is not KEEP_RUNTIME_DATA:
                self._apply_runtime_data(
                    target,
                    mutation.runtime_data,
                    candidate,
                )
                impacts |= self._runtime_data_impacts(
                    mutation.runtime_data,
                    candidate,
                )
            elif mutation.data is not None:
                self._apply_data(target, candidate)
                impacts |= self._data_impacts(before, candidate)

            self._state = candidate
            actual = deepcopy(candidate.properties)
            for spec, _previous in applied:
                try:
                    actual[spec.key] = spec.normalize(
                        self._read_property(target, spec)
                    )
                except Exception:
                    pass
            self._state = candidate.clone(properties=actual)
        except Exception as exc:
            if target is not None:
                for spec, previous in reversed(applied):
                    try:
                        self._write_property(target, spec, previous)
                    except Exception:
                        pass
                if runtime_snapshot is not KEEP_RUNTIME_DATA:
                    try:
                        self._restore_runtime_data(
                            target,
                            runtime_snapshot,
                        )
                    except Exception:
                        pass
            if before is not None:
                self._state = before.clone()
            self._request_updates(UpdateImpact.REDRAW, target)
            return self._rejected(property_key, before, str(exc))

        if (
            not applied
            and mutation.data is None
            and mutation.runtime_data is KEEP_RUNTIME_DATA
        ):
            return ComponentChange(
                self.component_id,
                property_key,
                before,
                self.state,
                ChangeStatus.NOOP,
            )

        try:
            self._request_updates(impacts, target)
        except Exception as exc:
            for spec, previous in reversed(applied):
                try:
                    self._write_property(target, spec, previous)
                except Exception:
                    pass
            if runtime_snapshot is not KEEP_RUNTIME_DATA:
                try:
                    self._restore_runtime_data(target, runtime_snapshot)
                except Exception:
                    pass
            if before is not None:
                self._state = before.clone()
            return self._rejected(property_key, before, str(exc))

        empty = (
            mutation.runtime_data is not KEEP_RUNTIME_DATA
            and self._runtime_data_is_empty(
                target,
                mutation.runtime_data,
                self._state,
            )
        )
        change = ComponentChange(
            self.component_id,
            property_key,
            before,
            self.state,
            ChangeStatus.EMPTY if empty else ChangeStatus.APPLIED,
            impacts,
            "Component has no drawable data." if empty else "",
        )
        self._publish_change(change)
        return change

    def set_property(self, key: str, value: Any) -> ComponentChange:
        """Set property."""

        before = self._safe_snapshot()
        if self._deleted:
            return self._rejected(
                key, before, f"Component {self.component_id!r} is deleted."
            )
        spec = self.property_specs().get(key)
        if spec is None:
            return self._rejected(
                key, before, f"Unknown property {key!r}."
            )

        target: T | None = None
        try:
            normalized = spec.normalize(value)
            candidate_properties = deepcopy(
                before.properties if before is not None else self._state.properties
            )
            candidate_properties[key] = deepcopy(normalized)
            candidate = self._state.clone(properties=candidate_properties)
            self._validate_candidate(candidate)
            target = self.resolve_target()
            old_value = self._read_property(target, spec)
            if _values_equal(old_value, normalized):
                self._state = candidate
                return ComponentChange(
                    self.component_id,
                    key,
                    before,
                    self.state,
                    ChangeStatus.NOOP,
                )
            self._write_property(target, spec, normalized)
            try:
                candidate_properties[key] = spec.normalize(
                    self._read_property(target, spec)
                )
            except Exception:
                candidate_properties[key] = deepcopy(normalized)
            self._state = candidate.clone(properties=candidate_properties)
        except Exception as exc:
            if target is not None and "old_value" in locals():
                try:
                    self._write_property(target, spec, old_value)
                except Exception:
                    pass
            if before is not None:
                self._state = before.clone()
            self._request_updates(UpdateImpact.REDRAW, target)
            return self._rejected(key, before, str(exc))

        try:
            self._request_updates(spec.impact, target)
        except Exception as exc:
            try:
                self._write_property(target, spec, old_value)
            except Exception:
                pass
            if before is not None:
                self._state = before.clone()
            return self._rejected(key, before, str(exc))
        change = ComponentChange(
            self.component_id,
            key,
            before,
            self.state,
            ChangeStatus.APPLIED,
            spec.impact,
        )
        self._publish_change(change)
        return change

    def apply_state(self, state: ComponentState) -> ComponentChange:
        """Apply state."""

        before = self._safe_snapshot()
        target: T | None = None
        applied: list[tuple[PropertySpec, Any]] = []
        impacts = UpdateImpact.NONE
        try:
            self._validate_replacement(state)
            specs = self.property_specs()
            normalized_properties = deepcopy(state.properties)
            for key, value in state.properties.items():
                spec = specs.get(key)
                if spec is not None:
                    normalized_properties[key] = spec.normalize(value)
            candidate = state.clone(properties=normalized_properties)
            self._validate_candidate(candidate)
            target = self.resolve_target()
            for spec in self.PROPERTY_SPECS:
                if spec.key not in normalized_properties:
                    continue
                previous = self._read_property(target, spec)
                value = normalized_properties[spec.key]
                if _values_equal(previous, value):
                    continue
                self._write_property(target, spec, value)
                applied.append((spec, previous))
                impacts |= spec.impact
            self._apply_data(target, candidate)
            impacts |= self._data_impacts(before, candidate)
            self._state = candidate
            actual = deepcopy(candidate.properties)
            for spec, _previous in applied:
                try:
                    actual[spec.key] = spec.normalize(
                        self._read_property(target, spec)
                    )
                except Exception:
                    pass
            self._state = candidate.clone(properties=actual)
        except Exception as exc:
            if target is not None:
                for spec, previous in reversed(applied):
                    try:
                        self._write_property(target, spec, previous)
                    except Exception:
                        pass
                if before is not None:
                    try:
                        self._apply_data(target, before)
                    except Exception:
                        pass
            if before is not None:
                self._state = before.clone()
            self._request_updates(UpdateImpact.REDRAW, target)
            return self._rejected(None, before, str(exc))

        status = (
            ChangeStatus.EMPTY
            if self._is_empty(target, self._state)
            else ChangeStatus.APPLIED
        )
        message = (
            "Component has no drawable data."
            if status is ChangeStatus.EMPTY
            else ""
        )
        try:
            self._request_updates(impacts, target)
        except Exception as exc:
            if target is not None:
                for spec, previous in reversed(applied):
                    try:
                        self._write_property(target, spec, previous)
                    except Exception:
                        pass
                if before is not None:
                    try:
                        self._apply_data(target, before)
                    except Exception:
                        pass
            if before is not None:
                self._state = before.clone()
            return self._rejected(None, before, str(exc))
        change = ComponentChange(
            self.component_id,
            None,
            before,
            self.state,
            status,
            impacts,
            message,
        )
        self._publish_change(change)
        return change

    def restore(self, snapshot: ComponentState) -> ComponentChange:
        """Restore the previously captured state."""

        return self.apply_state(snapshot)

    def _delete_component(self) -> ComponentChange:
        """Package-internal primitive used by deletion transactions/tests."""

        before = self._safe_snapshot()
        if self._deleted:
            return ComponentChange(
                self.component_id,
                None,
                before,
                None,
                ChangeStatus.NOOP,
            )
        if self.DELETION_POLICY is DeletionPolicy.FORBID:
            return self._rejected(
                None,
                before,
                f"{self.state.kind.value} components cannot be removed.",
            )
        if self.DELETION_POLICY is DeletionPolicy.HIDE:
            return self._hide_for_delete()
        if self._registry is not None:
            result = self._registry.delete_transaction((self.component_id,))
            if result.changes:
                return result.changes[-1]
            return ComponentChange(
                self.component_id,
                None,
                before,
                before,
                ChangeStatus.NOOP,
            )

        handle: RemovalHandle | None = None
        try:
            handle = self.prepare_remove()
            self.commit_remove(handle)
            self._deleted = True
            self._locator.unbind(self.component_id)
            self._finalize_remove(handle)
            apply_update_impacts(handle.subject, self.DELETE_IMPACTS)
        except Exception as exc:
            if handle is not None:
                self.rollback_remove(handle)
                self._locator.bind(self.component_id, handle.target)
            self._deleted = False
            return self._rejected(None, before, str(exc))
        return ComponentChange(
            self.component_id,
            None,
            before,
            None,
            ChangeStatus.DELETED,
            self.DELETE_IMPACTS,
        )

    def prepare_remove(self) -> RemovalHandle:
        """Capture everything required to detach and restore the same target."""

        if self.DELETION_POLICY is not DeletionPolicy.REMOVE:
            raise ComponentValidationError(
                f"{type(self).__name__} does not support physical removal."
            )
        target = self.resolve_target()
        return MATPLOTLIB_REMOVAL.prepare_artist(
            target,
            subject=update_subject_for(target),
        )

    def commit_remove(self, handle: RemovalHandle) -> None:
        """Reversibly detach a prepared target without lifecycle effects."""

        MATPLOTLIB_REMOVAL.commit(handle)

    def rollback_remove(self, handle: RemovalHandle) -> None:
        """Idempotently restore the exact target at its original position."""

        MATPLOTLIB_REMOVAL.rollback(handle)

    def _finalize_remove(self, handle: RemovalHandle) -> None:
        """Complete non-reversible Matplotlib cleanup after Registry commit."""

        MATPLOTLIB_REMOVAL.finalize(handle)

    def _hide_for_delete(self) -> ComponentChange:
        """Hide a fixed semantic component while retaining its tree identity."""

        return self.set_property("visible", False)

    def _safe_snapshot(self) -> ComponentState | None:
        try:
            return self.snapshot()
        except (ComponentDeletedError, ComponentNotFoundError):
            return self._state.clone()

    def _transaction_snapshot(
        self,
    ) -> tuple[ComponentState, Any, dict[str, Any]]:
        """Capture persistent and transient state for Registry rollback."""

        # Preserve the authoritative Controller value byte-for-byte.  Calling
        # ``snapshot()`` here would re-read incidental Matplotlib state and
        # could make a failed transaction dirty even though no user change
        # committed.
        state = self._state.clone()
        target = self.resolve_target()
        target_properties: dict[str, Any] = {}
        for spec in self.PROPERTY_SPECS:
            try:
                target_properties[spec.key] = deepcopy(
                    self._read_property(target, spec)
                )
            except Exception:
                continue
        return (
            state,
            self._capture_runtime_data(target),
            target_properties,
        )

    def _restore_transaction_snapshot(
        self,
        snapshot: tuple[ComponentState, Any, dict[str, Any]],
    ) -> None:
        """Restore a snapshot without publishing intermediate events."""

        state, runtime_data, target_properties = snapshot
        target = self.resolve_target()
        specs = self.property_specs()
        self._apply_data(target, state)
        self._restore_runtime_data(target, runtime_data)
        for key, value in target_properties.items():
            spec = specs.get(key)
            if spec is not None:
                self._write_property(target, spec, deepcopy(value))
        self._state = state.clone()

    def _validate_controller_state(self, state: ComponentState) -> None:
        if self.KIND is not None and state.kind is not self.KIND:
            raise ComponentValidationError(
                f"{type(self).__name__} requires kind {self.KIND.value!r}, "
                f"got {state.kind.value!r}."
            )
        if self.ROLES and state.role not in self.ROLES:
            values = sorted(role.value for role in self.ROLES)
            raise ComponentValidationError(
                f"{type(self).__name__} requires one of roles {values!r}, "
                f"got {state.role.value!r}."
            )
        self._validate_candidate(state)
        self._validate_data(state)

    def _validate_replacement(self, state: ComponentState) -> None:
        if state.id != self.component_id:
            raise ComponentValidationError("Cannot replace a component's id.")
        if state.kind is not self._state.kind or state.role is not self._state.role:
            raise ComponentValidationError(
                "Cannot replace a component's kind or role."
            )
        expected = {
            spec.key for spec in self.PROPERTY_SPECS if spec.persistent
        }
        actual = set(state.properties)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            details = []
            if missing:
                details.append(f"missing {missing!r}")
            if unknown:
                details.append(f"unknown {unknown!r}")
            raise ComponentValidationError(
                "Component property keys are invalid: "
                + ", ".join(details)
            )
        self._validate_controller_state(state)

    def _validate_candidate(self, state: ComponentState) -> None:
        """Hook for selector and cross-property validation."""

    def _validate_data(self, state: ComponentState) -> None:
        """Validate that style-only components do not carry opaque data."""

        if state.data:
            raise ComponentValidationError(
                f"{state.role.value} components do not accept data fields."
            )

    def _read_property(self, target: T, spec: PropertySpec) -> Any:
        getter = spec.getter
        if callable(getter):
            return getter(target)
        name = getter if isinstance(getter, str) else f"get_{spec.key}"
        accessor = getattr(target, name)
        return accessor() if callable(accessor) else accessor

    def _write_property(
        self, target: T, spec: PropertySpec, value: Any
    ) -> None:
        setter = spec.setter
        if callable(setter):
            setter(target, value)
            return
        name = setter if isinstance(setter, str) else f"set_{spec.key}"
        getattr(target, name)(value)

    def _apply_data(self, target: T, state: ComponentState) -> None:
        """Apply role-specific data.  Style-only controllers need no hook."""

    def _validate_runtime_data(
        self,
        target: T,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        raise ComponentValidationError(
            f"{state.role.value} components do not accept runtime data."
        )

    def _capture_runtime_data(self, target: T) -> Any:
        return None

    def _apply_runtime_data(
        self,
        target: T,
        runtime_data: Any,
        state: ComponentState,
    ) -> None:
        self._validate_runtime_data(target, runtime_data, state)

    def _restore_runtime_data(self, target: T, runtime_data: Any) -> None:
        del target, runtime_data

    def _runtime_data_impacts(
        self,
        runtime_data: Any,
        state: ComponentState,
    ) -> UpdateImpact:
        del runtime_data, state
        return UpdateImpact.NONE

    def _runtime_data_is_empty(
        self,
        target: T,
        runtime_data: Any,
        state: ComponentState,
    ) -> bool:
        del runtime_data
        return self._is_empty(target, state)

    def _is_empty(self, target: T, state: ComponentState) -> bool:
        return False

    def _data_impacts(
        self,
        before: ComponentState | None,
        after: ComponentState,
    ) -> UpdateImpact:
        return UpdateImpact.NONE

    def _delete_target(self, target: T) -> None:
        remove = getattr(target, "remove", None)
        if callable(remove):
            remove()
            return
        set_visible = getattr(target, "set_visible", None)
        if callable(set_visible):
            set_visible(False)
            return
        raise ComponentValidationError(
            f"{type(target).__name__} cannot be deleted or hidden."
        )

    def _request_updates(
        self, impacts: UpdateImpact, target: Any | None = None
    ) -> None:
        if impacts == UpdateImpact.NONE:
            return
        if target is None:
            try:
                target = self.resolve_target()
            except (ComponentDeletedError, ComponentNotFoundError):
                target = None
        subject = update_subject_for(target)
        if self._registry is not None:
            self._registry.request_update(subject, impacts)
        else:
            apply_update_impacts(subject, impacts)

    def _publish_change(self, change: ComponentChange) -> None:
        if self._registry is not None and change.changed:
            self._registry._record_change(change)

    def _rejected(
        self,
        key: str | None,
        before: ComponentState | None,
        message: str,
    ) -> ComponentChange:
        return ComponentChange(
            self.component_id,
            key,
            before,
            before.clone() if before is not None else None,
            ChangeStatus.REJECTED,
            UpdateImpact.NONE,
            message,
        )
