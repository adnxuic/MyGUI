"""ThemeService: sole publisher of application font, palette, QSS, and density."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QFont, QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication

from .chrome import build_font, build_palette
from .errors import ThemeApplyError, ThemeRollbackError, ThemeValidationError
from .metrics import build_density_metrics
from .models import (
    APPLY_STEPS,
    AppearancePreferences,
    EffectiveScheme,
    ThemeHealth,
    ThemeMode,
    ThemeSnapshot,
)
from .ports import (
    MetricsBindingPort,
    NullThemeIconProvider,
    PlaceholderQssRenderer,
    QssDocumentRenderer,
    ThemeBindingPort,
    ThemeBindingRegistry,
    ThemeIconProvider,
    binding_apply,
    binding_capture,
    binding_iter,
    binding_restore,
)
from .system import resolve_effective_scheme, scheme_from_palette
from .tokens import ICON_ROLES, build_tokens

ThemeListener = Callable[[ThemeSnapshot, ThemeSnapshot], None]


@dataclass
class ThemeFaultHooks:
    """Test-only stepwise fault injection. Production leaves this unset."""

    fail_apply_step: str | None = None
    fail_rollback_step: str | None = None
    fail_prerender: bool = False


@dataclass
class _PreparedTheme:
    snapshot: ThemeSnapshot
    app_qss: str
    local_qss: dict[str, str]
    icons: object


@dataclass
class _ChromeMemento:
    font: QFont
    palette: QPalette
    stylesheet: str
    local_styles: dict[int, str] = field(default_factory=dict)
    metrics: object = None
    icons: object = None
    qss_tokens: dict[str, str] = field(default_factory=dict)
    hub_snapshot: ThemeSnapshot | None = None


class ThemeService(QObject):
    """Apply, preview, and roll back application chrome on the GUI thread."""

    themeChanged = Signal(object, object)

    def __init__(
        self,
        application: QApplication,
        *,
        style_hints: Any | None = None,
        native_palette: QPalette | None = None,
        binding_port: ThemeBindingPort | None = None,
        icon_provider: ThemeIconProvider | None = None,
        qss_renderer: QssDocumentRenderer | None = None,
        metrics_port: MetricsBindingPort | None = None,
        initial: AppearancePreferences | None = None,
        fault_hooks: ThemeFaultHooks | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(application if parent is None else parent)
        if application is None:
            raise ThemeValidationError("ThemeService requires a QApplication.")
        self._app = application
        self._native_palette = QPalette(
            native_palette if native_palette is not None else application.palette()
        )
        self._unknown_fallback = scheme_from_palette(self._native_palette)
        self._hints = (
            style_hints if style_hints is not None else application.styleHints()
        )
        self._bindings: ThemeBindingPort = (
            binding_port if binding_port is not None else ThemeBindingRegistry()
        )
        self._icons: ThemeIconProvider = (
            icon_provider if icon_provider is not None else NullThemeIconProvider()
        )
        self._qss: QssDocumentRenderer = (
            qss_renderer if qss_renderer is not None else PlaceholderQssRenderer()
        )
        self._metrics_port = metrics_port
        self._fault_hooks = fault_hooks
        self._health = ThemeHealth.OK
        self._published = False
        self._in_preview = False
        self._in_transaction = False
        self._session_memento: _ChromeMemento | None = None
        self._session_snapshot: ThemeSnapshot | None = None
        self._snapshot = self._compose_snapshot(
            initial if initial is not None else AppearancePreferences()
        )
        self._connect_runtime_hub()
        self._scheme_connection = None
        changed = getattr(self._hints, "colorSchemeChanged", None)
        if changed is not None:
            self._scheme_connection = changed.connect(self._on_system_scheme_changed)

    @property
    def bindings(self) -> ThemeBindingPort:
        """Registry used by B (QSS) and C (hidden widgets / popouts)."""

        return self._bindings

    def health(self) -> ThemeHealth:
        return self._health

    def snapshot(self) -> ThemeSnapshot:
        """Return the currently applied (or last composed) snapshot."""

        return self._snapshot

    def resolve_effective_scheme(
        self,
        mode: ThemeMode | None = None,
    ) -> EffectiveScheme:
        """Resolve Light/Dark, using startup native luminance for Unknown."""

        prefs_mode = self._snapshot.preferences.mode if mode is None else mode
        color_scheme = self._hints.colorScheme()
        return resolve_effective_scheme(
            ThemeMode(prefs_mode),
            color_scheme,
            self._unknown_fallback,
        )

    def subscribe(self, callback: ThemeListener) -> Callable[[], None]:
        """Register ``themeChanged(old, new)``. Successful apply emits once."""

        self.themeChanged.connect(callback)

        def unsubscribe() -> None:
            try:
                self.themeChanged.disconnect(callback)
            except RuntimeError:
                return

        return unsubscribe

    def preview(self, preferences: AppearancePreferences) -> None:
        """Apply chrome reversibly without writing settings storage."""

        prepared = self._prepare(preferences)
        entering = not self._in_preview
        if entering:
            self._session_memento = self._capture()
            self._session_snapshot = self._snapshot
            self._in_preview = True
        try:
            self._apply_prepared(prepared)
        except ThemeRollbackError:
            if entering:
                self._in_preview = False
                self._session_memento = None
                self._session_snapshot = None
            raise
        except Exception as exc:
            if entering:
                self._in_preview = False
                self._session_memento = None
                self._session_snapshot = None
            raise ThemeApplyError(str(exc)) from exc
        self._snapshot = prepared.snapshot
        self._publish_hub_snapshot()

    def cancel_preview(self) -> None:
        """Restore the exact chrome captured when preview began."""

        if not self._in_preview:
            return
        memento = self._session_memento
        origin = self._session_snapshot
        try:
            if memento is not None:
                self._restore(memento)
        except Exception as exc:
            self._health = ThemeHealth.UNCERTAIN
            raise ThemeRollbackError((exc,)) from exc
        if origin is not None:
            self._snapshot = origin
        self._in_preview = False
        self._session_memento = None
        self._session_snapshot = None
        self._publish_hub_snapshot()

    def rollback(self) -> None:
        """Settings Center / binder alias for ``cancel_preview``."""

        self.cancel_preview()

    def restore_pre_session_appearance(self) -> None:
        """Phase-4 hook: Cancel, Esc, close, or storage failure."""

        self.cancel_preview()

    def apply_committed(self, preferences: AppearancePreferences) -> None:
        """Confirm chrome after a successful settings document commit."""

        prepared = self._prepare(preferences)
        old = self._session_snapshot if self._in_preview else self._snapshot
        already_applied = self._in_preview and _same_chrome(
            self._snapshot, prepared.snapshot
        )
        if not already_applied:
            try:
                self._apply_prepared(prepared)
            except ThemeRollbackError:
                raise
            except Exception as exc:
                raise ThemeApplyError(str(exc)) from exc
            self._snapshot = prepared.snapshot
        new = self._snapshot
        self._in_preview = False
        self._session_memento = None
        self._session_snapshot = None
        self._published = True
        self._health = ThemeHealth.OK
        self._publish_hub_snapshot()
        self.themeChanged.emit(old, new)

    def _connect_runtime_hub(self) -> None:
        """Attach C's window/icon hub and use it as the default step-4 ports."""

        try:
            from .ports import NullThemeIconProvider
            from .runtime import default_theme_runtime
        except ImportError:
            return
        hub = default_theme_runtime()
        if self._metrics_port is None:
            self._metrics_port = hub.metrics_applier
        if isinstance(self._icons, NullThemeIconProvider):
            self._icons = hub.icon_provider
        hub.snapshot = self._snapshot
        if hub.binding_port is None:
            hub.binding_port = self._bindings
        attach = getattr(hub, "attach_publisher", None)
        if callable(attach):
            attach(self)

    def _publish_hub_snapshot(self) -> None:
        self._set_hub_snapshot(self._snapshot)

    def _set_hub_snapshot(self, snapshot: ThemeSnapshot | None) -> None:
        try:
            from .runtime import default_theme_runtime
        except ImportError:
            return
        default_theme_runtime().snapshot = snapshot

    def shutdown(self) -> None:
        """Disconnect System listening. Safe to call more than once."""

        connection = self._scheme_connection
        self._scheme_connection = None
        if connection is None or isinstance(connection, bool):
            return
        try:
            QObject.disconnect(connection)
        except (RuntimeError, TypeError):
            return

    def _on_system_scheme_changed(self, _scheme: object = None) -> None:
        if self._in_transaction or self._health is ThemeHealth.UNCERTAIN:
            return
        if self._snapshot.preferences.mode is not ThemeMode.SYSTEM:
            return
        if not self._published and not self._in_preview:
            return
        preferences = self._snapshot.preferences
        if self._in_preview:
            self.preview(preferences)
            return
        self.apply_committed(preferences)

    def _prepare(self, preferences: AppearancePreferences) -> _PreparedTheme:
        if not isinstance(preferences, AppearancePreferences):
            raise ThemeValidationError("preferences must be AppearancePreferences.")
        snapshot = self._compose_snapshot(preferences)
        hooks = self._fault_hooks
        if hooks is not None and hooks.fail_prerender:
            raise ThemeApplyError("theme prerender failed")
        app_qss = self._qss.render_application(snapshot)
        local_qss: dict[str, str] = {}
        for _widget, resource in binding_iter(self._bindings):
            if resource not in local_qss:
                local_qss[resource] = self._qss.render_resource(resource, snapshot)
        icons = self._icons.prerender(snapshot)
        return _PreparedTheme(
            snapshot=snapshot,
            app_qss=app_qss,
            local_qss=local_qss,
            icons=icons,
        )

    def _compose_snapshot(self, preferences: AppearancePreferences) -> ThemeSnapshot:
        scheme = self.resolve_effective_scheme(preferences.mode)
        font = build_font(preferences.font_pt)
        font_height = QFontMetrics(font).height()
        metrics = build_density_metrics(preferences.density, font_height)
        tokens = build_tokens(scheme, metrics, preferences)
        palette = build_palette(tokens)
        return ThemeSnapshot(
            scheme=scheme,
            preferences=preferences,
            palette=palette,
            font=font,
            metrics=metrics,
            tokens=tokens,
            icon_roles=dict(ICON_ROLES),
        )

    def _capture(self) -> _ChromeMemento:
        metrics_memento = None
        if self._metrics_port is not None:
            metrics_memento = self._metrics_port.capture()
        qss_tokens: dict[str, str] = {}
        try:
            from .qss import current_qss_tokens

            qss_tokens = dict(current_qss_tokens())
        except ImportError:
            pass
        hub_snapshot = None
        try:
            from .runtime import current_theme_snapshot

            hub_snapshot = current_theme_snapshot()
        except ImportError:
            pass
        return _ChromeMemento(
            font=QFont(self._app.font()),
            palette=QPalette(self._app.palette()),
            stylesheet=self._app.styleSheet(),
            local_styles=binding_capture(self._bindings),
            metrics=metrics_memento,
            icons=self._icons.capture(),
            qss_tokens=qss_tokens,
            hub_snapshot=hub_snapshot,
        )

    def _apply_prepared(self, prepared: _PreparedTheme) -> None:
        self._ensure_gui_thread()
        memento = self._capture()
        self._in_transaction = True
        applied: list[str] = []
        try:
            self._set_hub_snapshot(prepared.snapshot)
            for step in APPLY_STEPS:
                self._maybe_fail_apply(step)
                self._run_apply_step(step, prepared)
                applied.append(step)
        except Exception as exc:
            self._rollback_applied(applied, memento, primary=exc)
            raise
        finally:
            self._in_transaction = False

    def _rollback_applied(
        self,
        applied: list[str],
        memento: _ChromeMemento,
        *,
        primary: BaseException,
    ) -> None:
        self._set_hub_snapshot(memento.hub_snapshot)
        errors: list[BaseException] = []
        while applied:
            step = applied.pop()
            try:
                self._maybe_fail_rollback(step)
                self._restore_step(step, memento)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        if errors:
            self._health = ThemeHealth.UNCERTAIN
            raise ThemeRollbackError(tuple(errors), primary=primary)

    def _run_apply_step(self, step: str, prepared: _PreparedTheme) -> None:
        snapshot = prepared.snapshot
        if step == "font":
            self._app.setFont(QFont(snapshot.font))
            return
        if step == "palette":
            self._app.setPalette(QPalette(snapshot.palette))
            try:
                from .windows import default_window_registry

                default_window_registry().apply_palette(snapshot.palette)
            except ImportError:
                pass
            return
        if step == "qss":
            self._app.setStyleSheet(prepared.app_qss)
            binding_apply(self._bindings, prepared.local_qss)
            try:
                from .qss import default_qss_binding

                default_qss_binding().apply_tokens(snapshot.tokens)
            except ImportError:
                pass
            try:
                from .windows import refresh_chrome_style

                refresh_chrome_style()
            except ImportError:
                pass
            return
        if step == "metrics":
            if self._metrics_port is not None:
                self._metrics_port.apply(snapshot.metrics)
            return
        if step == "icons":
            self._icons.apply(prepared.icons)
            return
        raise ThemeApplyError(f"Unknown theme apply step {step!r}.")

    def _restore_step(self, step: str, memento: _ChromeMemento) -> None:
        if step == "icons":
            self._icons.restore(memento.icons)
            return
        if step == "metrics":
            if self._metrics_port is not None:
                self._metrics_port.restore(memento.metrics)
            return
        if step == "qss":
            self._app.setStyleSheet(memento.stylesheet)
            binding_restore(self._bindings, memento.local_styles)
            try:
                from .qss import default_qss_binding

                if memento.qss_tokens:
                    default_qss_binding().apply_tokens(memento.qss_tokens)
            except ImportError:
                pass
            try:
                from .windows import refresh_chrome_style

                refresh_chrome_style()
            except ImportError:
                pass
            return
        if step == "palette":
            self._app.setPalette(QPalette(memento.palette))
            try:
                from .windows import default_window_registry

                default_window_registry().apply_palette(memento.palette)
            except ImportError:
                pass
            return
        if step == "font":
            self._app.setFont(QFont(memento.font))
            return
        raise ThemeApplyError(f"Unknown theme restore step {step!r}.")

    def _restore(self, memento: _ChromeMemento) -> None:
        self._ensure_gui_thread()
        self._set_hub_snapshot(memento.hub_snapshot)
        for step in reversed(APPLY_STEPS):
            self._restore_step(step, memento)

    def _maybe_fail_apply(self, step: str) -> None:
        hooks = self._fault_hooks
        if hooks is not None and hooks.fail_apply_step == step:
            raise RuntimeError(f"theme {step} apply failed")

    def _maybe_fail_rollback(self, step: str) -> None:
        hooks = self._fault_hooks
        if hooks is not None and hooks.fail_rollback_step == step:
            raise RuntimeError(f"theme {step} rollback failed")

    def _ensure_gui_thread(self) -> None:
        if QThread.currentThread() is not self._app.thread():
            raise ThemeApplyError("Theme apply must run on the GUI thread.")


def _same_chrome(left: ThemeSnapshot, right: ThemeSnapshot) -> bool:
    return (
        left.scheme is right.scheme
        and left.preferences == right.preferences
        and dict(left.tokens) == dict(right.tokens)
    )
