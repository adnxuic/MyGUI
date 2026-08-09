"""Shared runtime context for Controller-backed component editors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import weakref

from Qt_core import QTimer

from code import status_messages
from code.figuremodify.components import (
    ChangeStatus,
    ComponentBatchChange,
    ComponentChange,
    ComponentEvent,
    ComponentEventKind,
    ComponentKind,
    ComponentRegistry,
    MessageLevel,
)
from code.widgets.common_widget.min_widget.color_library import ColorLibrary


class MessagePresenter:
    """Route component outcomes to the application Message Bar once."""

    _NOTICE_PRIORITY = {
        MessageLevel.INFO: 0,
        MessageLevel.SUCCESS: 1,
        MessageLevel.WARNING: 2,
        MessageLevel.ERROR: 3,
    }

    def __init__(
        self,
        registry: ComponentRegistry | None = None,
    ) -> None:
        self.registry: ComponentRegistry | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._pending_changes: list[ComponentChange] = []
        self._consumed_changes: list[ComponentChange] = []
        self._flush_timer = QTimer()
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_pending)
        if registry is not None:
            self.bind_registry(registry)

    def bind_registry(self, registry: ComponentRegistry) -> None:
        """Show a fallback message for committed, otherwise unpresented changes."""

        if registry is self.registry and self._unsubscribe is not None:
            return
        self._detach_registry()
        self.registry = registry
        self._unsubscribe = registry.subscribe(
            self._component_event,
            kinds=(ComponentEventKind.CHANGED,),
        )

    def _detach_registry(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
        self._unsubscribe = None
        self.registry = None
        self._flush_timer.stop()
        self._pending_changes.clear()
        self._consumed_changes.clear()

    def _component_event(self, event: ComponentEvent) -> None:
        change = event.change
        if (
            event.kind is not ComponentEventKind.CHANGED
            or change is None
            or not change.ok
            or change.status is ChangeStatus.NOOP
        ):
            return
        if any(item is change for item in self._pending_changes):
            return
        self._pending_changes.append(change)
        if not self._flush_timer.isActive():
            self._flush_timer.start(0)

    def _consume(self, changes: tuple[ComponentChange, ...]) -> None:
        for change in changes:
            if not any(item is change for item in self._pending_changes):
                continue
            if any(item is change for item in self._consumed_changes):
                continue
            self._consumed_changes.append(change)

    @staticmethod
    def _change_state(change: ComponentChange):
        return change.after if change.after is not None else change.before

    @classmethod
    def _coalesce_key(cls, change: ComponentChange):
        state = cls._change_state(change)
        parent_id = (
            getattr(state, "parent_id", None)
            if state is not None
            else None
        )
        if parent_id is None or change.property_key is None:
            return ("component", id(change))
        return (
            "property",
            parent_id,
            change.property_key,
            change.status,
        )

    @classmethod
    def _fallback_success(
        cls,
        changes: tuple[ComponentChange, ...],
    ) -> str:
        if not changes or any(change.message for change in changes):
            return ""
        for change in changes:
            state = cls._change_state(change)
            if (
                state is not None
                and getattr(state, "kind", None) is ComponentKind.SPINE
            ):
                selector = getattr(state, "selector", {})
                side = selector.get("name", selector.get("side"))
                if side and change.property_key == "visible":
                    label = str(side).replace("_", " ").title()
                    return f"{label} spine visibility updated."
        change = changes[0]
        if change.status is not ChangeStatus.APPLIED:
            return ""
        if change.property_key:
            label = change.property_key.replace("_", " ").title()
        else:
            state = cls._change_state(change)
            role = getattr(state, "role", None)
            label = str(getattr(role, "value", role or "Component"))
            label = label.replace("_", " ").title()
        return f"{label} updated."

    def _flush_pending(self) -> None:
        pending = tuple(
            change
            for change in self._pending_changes
            if not any(
                consumed is change
                for consumed in self._consumed_changes
            )
        )
        self._pending_changes.clear()
        self._consumed_changes.clear()
        grouped: dict[tuple, list[ComponentChange]] = {}
        for change in pending:
            grouped.setdefault(
                self._coalesce_key(change),
                [],
            ).append(change)
        for group in grouped.values():
            changes = tuple(group)
            result = (
                changes[0]
                if len(changes) == 1
                else ComponentBatchChange(changes, True)
            )
            self.present(
                result,
                success=self._fallback_success(changes),
            )

    def present(self, result, *, success: str = "") -> bool:
        """Show this Inspector and synchronize it from controller state."""

        if isinstance(result, ComponentBatchChange):
            ok = result.ok
            changes = result.changes
            notices = result.notices + tuple(
                notice
                for change in changes
                for notice in change.notices
            )
            message = result.message
            status = (
                ChangeStatus.REJECTED
                if not result.committed
                else next(
                    (
                        change.status
                        for change in changes
                        if change.status is ChangeStatus.EMPTY
                    ),
                    ChangeStatus.APPLIED
                    if any(change.changed for change in changes)
                    else ChangeStatus.NOOP,
                )
            )
        elif isinstance(result, ComponentChange):
            ok = result.ok
            changes = (result,)
            notices = result.notices
            message = result.message
            status = result.status
        else:
            raw_ok = getattr(result, "ok", result)
            ok = bool(raw_ok() if callable(raw_ok) else raw_ok)
            changes = ()
            notices = ()
            message = str(getattr(result, "message", "") or "")
            status = ChangeStatus.APPLIED if ok else ChangeStatus.REJECTED

        self._consume(tuple(changes))
        if not ok or status is ChangeStatus.REJECTED:
            status_messages.show_error(message or "Component update failed.")
            return False
        if notices:
            notice = max(
                notices,
                key=lambda item: self._NOTICE_PRIORITY[item.level],
            )
            if notice.level is MessageLevel.ERROR:
                status_messages.show_error(notice.message)
            elif notice.level is MessageLevel.WARNING:
                status_messages.show_warning(notice.message)
            elif notice.level is MessageLevel.SUCCESS:
                status_messages.show_success(notice.message)
            else:
                status_messages.show_message(notice.message, "info")
            return True
        if status is ChangeStatus.EMPTY:
            status_messages.show_warning(
                message or "Component has no drawable data."
            )
        elif status is ChangeStatus.DELETED:
            status_messages.show_success(
                success or "Component deleted."
            )
        elif status is ChangeStatus.APPLIED and (success or message):
            status_messages.show_success(success or message)
        return True

    def close(self) -> None:
        """Close the editor context and detach its callbacks."""

        self._detach_registry()

    def discard_pending(self) -> None:
        """Discard fallback messages already covered by a compound action."""

        self._flush_timer.stop()
        self._pending_changes.clear()
        self._consumed_changes.clear()


class ComponentEditorManager:
    """Create, synchronize, and dispose visible component Editors."""

    def __init__(self, registry: ComponentRegistry, editor_registry):
        self.registry = registry
        self.editor_registry = editor_registry
        self._editors: dict[
            str,
            list[tuple[weakref.ReferenceType, Callable | None]],
        ] = {}
        self._unsubscribe = registry.subscribe(self._component_event)
        self._closed = False

    def create(
        self,
        component_or_id,
        *,
        context,
        parent=None,
        remover: Callable | None = None,
    ):
        """Create and return a new instance."""

        if self._closed:
            raise RuntimeError("ComponentEditorManager is closed.")
        component_id = (
            component_or_id
            if isinstance(component_or_id, str)
            else getattr(component_or_id, "component_id", None)
        )
        controller = self.registry.get(component_id)
        editor = self.editor_registry.create(
            controller,
            context=context,
            parent=parent,
        )
        self._track(component_id, editor, remover=remover)
        return editor

    def _track(
        self,
        component_id: str,
        editor,
        *,
        remover: Callable | None = None,
    ) -> None:
        editor_ref = weakref.ref(editor)
        self._editors.setdefault(component_id, []).append(
            (editor_ref, remover)
        )
        editor.destroyed.connect(
            lambda *_args, target=component_id, reference=editor_ref:
            self._remove_registration(target, reference)
        )

    def _remove_registration(
        self,
        component_id: str,
        editor_ref: weakref.ReferenceType,
    ) -> None:
        registrations = self._editors.get(component_id, [])
        registrations[:] = [
            registration
            for registration in registrations
            if registration[0] is not editor_ref
        ]
        if not registrations:
            self._editors.pop(component_id, None)

    def release(self, editor) -> None:
        """Release exactly one Editor without affecting sibling views."""

        for component_id, registrations in tuple(self._editors.items()):
            registrations[:] = [
                registration
                for registration in registrations
                if registration[0]() is not editor
            ]
            if not registrations:
                self._editors.pop(component_id, None)

    def editor(self, component_id: str):
        """Return the editor widget used for the property."""

        registrations = self._editors.get(component_id, [])
        for editor_ref, _remover in registrations:
            editor = editor_ref()
            if editor is not None:
                return editor
        return None

    @staticmethod
    def _dispose_editor(editor) -> None:
        dispose = getattr(editor, "dispose", None)
        if callable(dispose):
            dispose()

    def _component_event(self, event: ComponentEvent) -> None:
        registrations = list(
            self._editors.get(event.component_id, [])
        )
        if not registrations:
            return
        if event.kind is ComponentEventKind.REMOVED:
            self._editors.pop(event.component_id, None)
            for editor_ref, remover in registrations:
                editor = editor_ref()
                if editor is None:
                    continue
                try:
                    self._dispose_editor(editor)
                    if remover is not None:
                        remover(editor)
                    else:
                        editor.setEnabled(False)
                        editor.deleteLater()
                except Exception:
                    pass
            return
        if event.kind is ComponentEventKind.CHANGED:
            for editor_ref, _remover in registrations:
                editor = editor_ref()
                if editor is None:
                    continue
                sync = getattr(
                    editor,
                    "sync_from_controller",
                    getattr(editor, "sync_from_state", None),
                )
                if callable(sync):
                    sync()

    def close(self) -> None:
        """Close the editor context and detach its callbacks."""

        if self._closed:
            return
        self._closed = True
        self._unsubscribe()
        registrations = tuple(
            registration
            for entries in self._editors.values()
            for registration in entries
        )
        self._editors.clear()
        for editor_ref, _remover in registrations:
            editor = editor_ref()
            if editor is None:
                continue
            try:
                self._dispose_editor(editor)
            except Exception:
                pass


@dataclass(slots=True)
class EditorContext:
    """Represent the application's editor context."""

    registry: ComponentRegistry
    color_library: ColorLibrary
    messages: MessagePresenter
    editor_manager: ComponentEditorManager
    axes_commands: object
    function_curves: object
    chart_data: object
    interpolation: object
    fitting: object
    text_rendering: object
    in_axes: object | None = None
    dependency_service: object | None = None
    delete_command: Callable[..., bool] | None = None

    @property
    def repository(self):
        """Return the repository."""

        return self.chart_data.repository
