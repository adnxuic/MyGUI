"""QSS token expansion binding. Not the ThemeService transaction engine.

Production widgets style through ``ThemeBindingPort.bind_qss(widget, resource)``.
``bind_qss(widget, resource, tokens)`` applies one stylesheet and registers a
weak binding so a later snapshot can replay without cached QSS strings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
import weakref

from PySide6.QtWidgets import QWidget

from mygui.resources import expand_qss_tokens, load_qss_resource, resource_path

from .models import ThemeSnapshot
from .ports import ThemeBindingPort
from .tokens import LIGHT_QSS_TOKENS

APPLICATION_QSS_RESOURCE = "mygui/widgets/mainwindow_init/app_style.qss"
MAINWINDOW_QSS_RESOURCE = "mygui/widgets/mainwindow_init/style.qss"
DIALOG_QSS_RESOURCE = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"


@dataclass(slots=True)
class _QssBinding:
    widget_ref: weakref.ref[QWidget]
    resource: str | None
    inline_template: str | None
    connection: object | None = None


_BINDINGS: dict[int, _QssBinding] = {}
_WATCHERS: dict[int, tuple[weakref.ref[QWidget], Callable[[Mapping[str, str]], None], object]] = {}
_INSTALLED_BINDING: ThemeBindingPort | None = None
_DEFAULT_BINDING: QssThemeBinding | None = None


def _alive_widget(widget_ref: weakref.ref[QWidget]) -> QWidget | None:
    widget = widget_ref()
    if widget is None:
        return None
    try:
        widget.objectName()
    except RuntimeError:
        return None
    return widget


def _forget_binding(key: int, *_args: object) -> None:
    _BINDINGS.pop(key, None)


def _forget_watcher(key: int, *_args: object) -> None:
    _WATCHERS.pop(key, None)


def _apply_stylesheet(
    widget: QWidget,
    *,
    resource: str | None,
    inline: str | None,
    tokens: Mapping[str, object],
) -> None:
    if inline is not None:
        widget.setStyleSheet(expand_qss_tokens(inline, tokens))
        return
    if resource is None:
        raise ValueError("QSS binding requires a resource path or inline template")
    widget.setStyleSheet(load_qss_resource(resource, tokens=tokens))


def _register(
    widget: QWidget,
    *,
    resource: str | None,
    inline: str | None,
) -> None:
    key = id(widget)
    previous = _BINDINGS.get(key)
    if previous is not None and previous.connection is not None:
        try:
            widget.destroyed.disconnect(previous.connection)
        except (RuntimeError, TypeError):
            pass
    connection = widget.destroyed.connect(
        lambda *_args, binding_key=key: _forget_binding(binding_key)
    )
    _BINDINGS[key] = _QssBinding(
        widget_ref=weakref.ref(widget),
        resource=resource,
        inline_template=inline,
        connection=connection,
    )


def bind_qss(widget: QWidget, resource: str, tokens: Mapping[str, object]) -> None:
    """Apply bundled QSS with explicit snapshot tokens and register a weak bind.

    ThemeService replays live bindings via ``apply_stylesheets``. Canvas popouts
    (SubAgent C) should call ``ThemeBindingPort.bind_qss`` on the parentless
    window; this helper is the token-explicit implementation behind that port.
    """

    _apply_stylesheet(widget, resource=resource, inline=None, tokens=tokens)
    _register(widget, resource=str(resource), inline=None)


def bind_qss_text(widget: QWidget, template: str, tokens: Mapping[str, object]) -> None:
    """Apply an inline token template and register it for snapshot replay."""

    _apply_stylesheet(widget, resource=None, inline=template, tokens=tokens)
    _register(widget, resource=None, inline=template)


def rebind_qss_bindings(tokens: Mapping[str, object]) -> None:
    """Replay every live QSS bind with ``tokens``. Does not cache stylesheet strings."""

    snapshot = MappingProxyType({str(name): str(value) for name, value in tokens.items()})
    for key, entry in list(_BINDINGS.items()):
        widget = _alive_widget(entry.widget_ref)
        if widget is None:
            _BINDINGS.pop(key, None)
            continue
        _apply_stylesheet(
            widget,
            resource=entry.resource,
            inline=entry.inline_template,
            tokens=snapshot,
        )
    _notify_token_watchers(snapshot)


def iter_bound_widgets():
    """Yield live QSS-bound widgets. Dead weakrefs are pruned."""

    for key, entry in list(_BINDINGS.items()):
        widget = _alive_widget(entry.widget_ref)
        if widget is None:
            _BINDINGS.pop(key, None)
            continue
        yield widget


def binding_count() -> int:
    """Return live QSS bindings. Tests use this; production does not."""

    live = 0
    for key, entry in list(_BINDINGS.items()):
        if _alive_widget(entry.widget_ref) is None:
            _BINDINGS.pop(key, None)
            continue
        live += 1
    return live


def watch_qss_tokens(
    widget: QWidget,
    callback: Callable[[Mapping[str, str]], None],
) -> None:
    """Invoke ``callback`` now and whenever QSS bindings are rebound."""

    key = id(widget)
    previous = _WATCHERS.get(key)
    if previous is not None and previous[2] is not None:
        try:
            widget.destroyed.disconnect(previous[2])
        except (RuntimeError, TypeError):
            pass
    connection = widget.destroyed.connect(
        lambda *_args, watcher_key=key: _forget_watcher(watcher_key)
    )
    _WATCHERS[key] = (weakref.ref(widget), callback, connection)
    callback(current_qss_tokens())


def _notify_token_watchers(tokens: Mapping[str, str]) -> None:
    for key, (ref, callback, _connection) in list(_WATCHERS.items()):
        widget = _alive_widget(ref)
        if widget is None:
            _WATCHERS.pop(key, None)
            continue
        callback(tokens)


def current_qss_tokens() -> Mapping[str, str]:
    """Return tokens from the current snapshot, installed port, or Light."""

    try:
        from .runtime import current_theme_snapshot
    except ImportError:
        snapshot = None
    else:
        snapshot = current_theme_snapshot()
    if snapshot is not None:
        return MappingProxyType(
            {str(name): str(value) for name, value in snapshot.tokens.items()}
        )
    binding = current_theme_binding()
    tokens = getattr(binding, "tokens", None)
    if tokens is None:
        return LIGHT_QSS_TOKENS
    return MappingProxyType({str(name): str(value) for name, value in tokens.items()})


class QssThemeBinding:
    """``ThemeBindingPort`` that expands bundled QSS from a current token table.

    This is not a font/palette/icon transaction engine. ``apply_tokens`` only
    retokenizes registered stylesheets.
    """

    def __init__(self, tokens: Mapping[str, object] | None = None) -> None:
        source = LIGHT_QSS_TOKENS if tokens is None else tokens
        self._tokens = MappingProxyType(
            {str(name): str(value) for name, value in source.items()}
        )

    @property
    def tokens(self) -> Mapping[str, str]:
        """Return the current token mapping used by ``bind_qss``."""

        return self._tokens

    def bind_qss(self, widget: QWidget, resource: str) -> None:
        """Bind ``resource`` using this port's current snapshot tokens."""

        bind_qss(widget, resource, self._tokens)

    def apply_tokens(self, tokens: Mapping[str, object]) -> None:
        """Replace tokens and replay every live binding. No rollback engine."""

        self._tokens = MappingProxyType(
            {str(name): str(value) for name, value in tokens.items()}
        )
        rebind_qss_bindings(self._tokens)


def default_qss_binding() -> QssThemeBinding:
    """Return the process default binding (Light until ThemeService installs)."""

    global _DEFAULT_BINDING
    if _DEFAULT_BINDING is None:
        _DEFAULT_BINDING = QssThemeBinding(LIGHT_QSS_TOKENS)
    return _DEFAULT_BINDING


def current_theme_binding() -> ThemeBindingPort:
    """Return the installed port, or the Light default QSS binding."""

    if _INSTALLED_BINDING is not None:
        return _INSTALLED_BINDING
    return default_qss_binding()


def install_theme_binding(binding: ThemeBindingPort | None) -> None:
    """Install the process ThemeBindingPort. ``None`` restores the Light default."""

    global _INSTALLED_BINDING
    _INSTALLED_BINDING = binding
    tokens = getattr(binding, "tokens", None) if binding is not None else None
    if tokens is not None:
        rebind_qss_bindings(tokens)


def _live_registry() -> ThemeBindingPort | None:
    try:
        from .runtime import default_theme_runtime
    except ImportError:
        return None
    return default_theme_runtime().binding_port


def bind_widget_qss(
    widget: QWidget,
    resource: str,
    *,
    theme_binding: ThemeBindingPort | None = None,
) -> None:
    """Bind bundled QSS through an injected port, or the process default.

    Always expands from current snapshot tokens (never a cached stylesheet
    string). Also registers on ThemeService's weak registry when the runtime
    hub has been wired, so hidden Settings/Style/Inspector/Fit hosts and
    parentless Canvas popouts retokenize on the next apply.
    """

    tokens = current_qss_tokens()
    bind_qss(widget, resource, tokens)
    port = theme_binding if theme_binding is not None else _live_registry()
    if port is None or port is current_theme_binding():
        return
    port.bind_qss(widget, resource)


def try_render_bound_resource(
    resource: str,
    tokens: Mapping[str, object] | None = None,
) -> str | None:
    """Return expanded QSS for an existing bundled resource, else ``None``."""

    try:
        resource_path(resource)
    except (FileNotFoundError, ValueError):
        return None
    mapping = current_qss_tokens() if tokens is None else tokens
    return load_qss_resource(resource, tokens=mapping)


def render_application_stylesheet(snapshot: ThemeSnapshot) -> str:
    """Pre-render application QSS. Prefix keeps ThemeService apply markers."""

    marker = f"/* mygui-theme:{snapshot.scheme.value} */\n"
    return marker + load_qss_resource(
        APPLICATION_QSS_RESOURCE,
        tokens=snapshot.tokens,
    )


def render_resource_stylesheet(resource: str, snapshot: ThemeSnapshot) -> str:
    """Pre-render one bundled QSS document, or a marker if the file is absent."""

    marker = f"/* mygui-theme-resource:{resource}:{snapshot.scheme.value} */\n"
    rendered = try_render_bound_resource(resource, snapshot.tokens)
    if rendered is None:
        from .chrome import render_placeholder_resource_qss

        return render_placeholder_resource_qss(resource, snapshot)
    return marker + rendered


class BundledQssRenderer:
    """Expand bundled QSS from ``ThemeSnapshot`` tokens with no widget side effects."""

    def render_application(self, snapshot: ThemeSnapshot) -> str:
        return render_application_stylesheet(snapshot)

    def render_resource(self, resource: str, snapshot: ThemeSnapshot) -> str:
        if resource == MAINWINDOW_QSS_RESOURCE:
            from mygui.widgets.mainwindow_init.basic_setting import (
                render_mainwindow_stylesheet,
            )

            marker = (
                f"/* mygui-theme-resource:{resource}:{snapshot.scheme.value} */\n"
            )
            return marker + render_mainwindow_stylesheet(snapshot=snapshot)
        return render_resource_stylesheet(resource, snapshot)


def reset_qss_bindings_for_tests() -> None:
    """Drop live binds and restore the Light default. Tests only."""

    global _INSTALLED_BINDING, _DEFAULT_BINDING
    _BINDINGS.clear()
    _WATCHERS.clear()
    _INSTALLED_BINDING = None
    _DEFAULT_BINDING = QssThemeBinding(LIGHT_QSS_TOKENS)
