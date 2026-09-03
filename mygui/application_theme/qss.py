"""QSS token expansion binding. Not the ThemeService transaction engine.

Production widgets style through ``ThemeBindingPort.bind_qss(widget, resource)``.
``bind_qss(widget, resource, tokens)`` applies one stylesheet and registers a
weak binding so a later snapshot can replay without cached QSS strings.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
from types import MappingProxyType
import weakref

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QWidget

from mygui.resources import expand_qss_tokens, load_qss_resource, resource_path

from .models import ThemeSnapshot
from .ports import ThemeBindingPort
from .tokens import LIGHT_QSS_TOKENS

APPLICATION_QSS_RESOURCE = "mygui/widgets/mainwindow_init/app_style.qss"
COMPONENT_QSS_RESOURCE = "mygui/widgets/ui_components/style.qss"
MAINWINDOW_QSS_RESOURCE = "mygui/widgets/mainwindow_init/style.qss"
DIALOG_QSS_RESOURCE = "mygui/widgets/title_bar/titlebar_dialog/dialog_style.qss"
QSS_BUNDLE_SEPARATOR = "\x1e"


@dataclass(frozen=True, slots=True)
class QssResourceBundle:
    """Ordered bundled QSS documents applied as one local stylesheet.

    The original resource paths stay the owners of the rule text. Callers bind
    the bundle once; they do not copy QSS contents.
    """

    resources: tuple[str, ...]

    def __post_init__(self) -> None:
        paths = tuple(str(item) for item in self.resources if str(item))
        if not paths:
            raise ValueError("QssResourceBundle requires at least one resource.")
        object.__setattr__(self, "resources", paths)

    @property
    def key(self) -> str:
        return QSS_BUNDLE_SEPARATOR.join(self.resources)


def qss_bind_key(resource: str | QssResourceBundle) -> str:
    """Return the ThemeBindingRegistry key for a resource or bundle."""

    if isinstance(resource, QssResourceBundle):
        return resource.key
    return str(resource)


def split_qss_resource_key(resource: str) -> tuple[str, ...]:
    """Split a bind key into ordered bundled resource paths."""

    if QSS_BUNDLE_SEPARATOR in resource:
        return tuple(part for part in resource.split(QSS_BUNDLE_SEPARATOR) if part)
    return (str(resource),)


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
_QSS_DOC_CACHE_MAX = 48
_COMPONENT_QSS_CACHE: OrderedDict[str, str] = OrderedDict()
_QSS_DOC_CACHE: OrderedDict[tuple[str, str], str] = OrderedDict()


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


@dataclass(slots=True)
class _ComboState:
    combo: QComboBox
    index: int
    checks: tuple[object, ...]


def _combo_is_checkable(combo: QComboBox) -> bool:
    model = combo.model()
    if model is None or model.rowCount() <= 0:
        return False
    sample = model.data(
        model.index(0, combo.modelColumn()),
        Qt.ItemDataRole.CheckStateRole,
    )
    return sample is not None


def _combo_states(root: QWidget) -> list[_ComboState]:
    combos = list(root.findChildren(QComboBox))
    if isinstance(root, QComboBox):
        combos.insert(0, root)
    states: list[_ComboState] = []
    for combo in combos:
        try:
            if not combo.isVisible():
                continue
        except RuntimeError:
            continue
        if not _combo_is_checkable(combo):
            continue
        model = combo.model()
        checks: tuple[object, ...] = ()
        if model is not None and model.rowCount() > 0:
            column = combo.modelColumn()
            checks = tuple(
                model.data(
                    model.index(row, column),
                    Qt.ItemDataRole.CheckStateRole,
                )
                for row in range(model.rowCount())
            )
        states.append(_ComboState(combo, combo.currentIndex(), checks))
    return states


def _restore_combo_states(states: list[_ComboState]) -> None:
    for state in states:
        combo = state.combo
        try:
            combo.objectName()
        except RuntimeError:
            continue
        blocker = QSignalBlocker(combo)
        model = combo.model()
        if model is not None and state.checks:
            model_blocker = QSignalBlocker(model)
            column = combo.modelColumn()
            for row, check in enumerate(state.checks):
                current = model.data(
                    model.index(row, column),
                    Qt.ItemDataRole.CheckStateRole,
                )
                if check is not None and current != check:
                    model.setData(
                        model.index(row, column),
                        check,
                        Qt.ItemDataRole.CheckStateRole,
                    )
            del model_blocker
        if combo.currentIndex() != state.index:
            combo.setCurrentIndex(state.index)
        del blocker


MATPLOTLIB_CANVAS_ISOLATION_QSS = "/* matplotlib figure; not workbench chrome */"


def isolate_matplotlib_canvas(widget: QWidget) -> None:
    """Keep workbench QSS from becoming Matplotlib Figure style.

    The isolation sheet is token-free and is not a ThemeBindingRegistry
    participant, so later theme transactions do not rewrite it or polish
    Figure pixels.
    """

    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
    if widget.styleSheet() != MATPLOTLIB_CANVAS_ISOLATION_QSS:
        widget.setStyleSheet(MATPLOTLIB_CANVAS_ISOLATION_QSS)


def apply_widget_stylesheet(widget: QWidget, stylesheet: str) -> None:
    """Apply a local stylesheet without resetting combo selection state."""

    if widget.styleSheet() == stylesheet:
        return
    states = _combo_states(widget)
    widget.setStyleSheet(stylesheet)
    _restore_combo_states(states)


def apply_application_stylesheet(app: QApplication, stylesheet: str) -> None:
    """Apply the process stylesheet without resetting live combo state."""

    if app.styleSheet() == stylesheet:
        return
    states: list[_ComboState] = []
    for widget in app.topLevelWidgets():
        states.extend(_combo_states(widget))
    app.setStyleSheet(stylesheet)
    _restore_combo_states(states)


def qss_token_fingerprint(tokens: Mapping[str, object]) -> str:
    """Return a CWD-independent fingerprint of a token mapping."""

    payload = "\0".join(
        f"{name}={value}"
        for name, value in sorted(
            (str(key), str(item)) for key, item in tokens.items()
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_put(cache: OrderedDict, key, value, *, maxsize: int = _QSS_DOC_CACHE_MAX):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > maxsize:
        cache.popitem(last=False)
    return value


def _component_qss_for_tokens(tokens: Mapping[str, object]) -> str:
    fingerprint = qss_token_fingerprint(tokens)
    cached = _COMPONENT_QSS_CACHE.get(fingerprint)
    if cached is not None:
        _COMPONENT_QSS_CACHE.move_to_end(fingerprint)
        return cached
    rendered = load_qss_resource(COMPONENT_QSS_RESOURCE, tokens=tokens)
    return _cache_put(_COMPONENT_QSS_CACHE, fingerprint, rendered)


def _cached_resource_document(
    resource: str,
    tokens: Mapping[str, object],
    factory,
) -> str:
    key = (qss_token_fingerprint(tokens), str(resource))
    cached = _QSS_DOC_CACHE.get(key)
    if cached is not None:
        _QSS_DOC_CACHE.move_to_end(key)
        return cached
    return _cache_put(_QSS_DOC_CACHE, key, factory())


def clear_qss_document_cache_for_tests() -> None:
    """Drop expanded QSS caches. Tests only."""

    _COMPONENT_QSS_CACHE.clear()
    _QSS_DOC_CACHE.clear()


def _apply_stylesheet(
    widget: QWidget,
    *,
    resource: str | None,
    inline: str | None,
    tokens: Mapping[str, object],
) -> None:
    if inline is not None:
        apply_widget_stylesheet(widget, expand_qss_tokens(inline, tokens))
        return
    if resource is None:
        raise ValueError("QSS binding requires a resource path or inline template")
    apply_widget_stylesheet(
        widget,
        compose_component_stylesheet(resource, tokens),
    )


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
    should call ``ThemeBindingPort.bind_qss`` on the parentless window; this
    helper is the token-explicit implementation behind that port.
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

    def publish_tokens(self, tokens: Mapping[str, object]) -> None:
        """Replace the token table without replaying bound stylesheets."""

        self._tokens = MappingProxyType(
            {str(name): str(value) for name, value in tokens.items()}
        )

    def apply_tokens(self, tokens: Mapping[str, object]) -> None:
        """Replace tokens and replay every live binding. No rollback engine."""

        self.publish_tokens(tokens)
        rebind_qss_bindings(self._tokens)


def publish_qss_tokens(tokens: Mapping[str, object]) -> None:
    """Update token tables and watchers without calling ``setStyleSheet``.

    ThemeService uses this after the single application sheet and each changed
    regional root have been applied. It is not a second stylesheet publisher.
    """

    snapshot = MappingProxyType(
        {str(name): str(value) for name, value in tokens.items()}
    )
    default_qss_binding().publish_tokens(snapshot)
    _notify_token_watchers(snapshot)


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
    resource: str | QssResourceBundle,
    *,
    theme_binding: ThemeBindingPort | None = None,
) -> None:
    """Bind bundled QSS through one registry and apply the sheet once.

    When ThemeService has wired ``ThemeBindingRegistry``, that registry is the
    only bind table. Otherwise the module-level fallback records the widget so
    tests and pre-service hosts can still retokenize.
    """

    path = qss_bind_key(resource)
    port = theme_binding if theme_binding is not None else _live_registry()
    if port is not None:
        port.bind_qss(widget, path)
        return
    bind_qss(widget, path, current_qss_tokens())


def compose_component_stylesheet(
    resource: str,
    tokens: Mapping[str, object],
    *,
    regional: str | None = None,
) -> str:
    """Prefix shared component QSS so local sheets keep control semantics.

    Qt local stylesheets isolate a widget from the application sheet, so every
    regional ``bind_qss`` document includes the component rules. Shared
    component QSS expands once per token fingerprint; regional documents are
    cached by fingerprint plus resource and never resolve from CWD.
    """

    component = _component_qss_for_tokens(tokens)
    resources = split_qss_resource_key(resource)
    if resources == (COMPONENT_QSS_RESOURCE,):
        return component
    if regional is not None:
        return f"{component}\n{regional}"

    def _compose() -> str:
        bodies = [
            load_qss_resource(path, tokens=tokens)
            for path in resources
            if path != COMPONENT_QSS_RESOURCE
        ]
        return f"{component}\n" + "\n".join(bodies)

    return _cached_resource_document(resource, tokens, _compose)


def try_render_bound_resource(
    resource: str,
    tokens: Mapping[str, object] | None = None,
) -> str | None:
    """Return expanded QSS for an existing bundled resource, else ``None``."""

    paths = split_qss_resource_key(resource)
    try:
        for path in paths:
            resource_path(path)
    except (FileNotFoundError, ValueError):
        return None
    mapping = current_qss_tokens() if tokens is None else tokens
    return compose_component_stylesheet(resource, mapping)


def render_application_stylesheet(snapshot: ThemeSnapshot) -> str:
    """Pre-render the small process-global popup and message-box stylesheet.

    Shared control rules stay on regional ``bind_qss`` documents. Qt local
    stylesheets isolate those subtrees, so repeating the component document on
    ``QApplication`` would polish the workbench twice.
    """

    def _compose() -> str:
        marker = "/* mygui-theme-app */\n"
        return marker + load_qss_resource(
            APPLICATION_QSS_RESOURCE,
            tokens=snapshot.tokens,
        )

    return _cached_resource_document(
        f"theme-doc:{APPLICATION_QSS_RESOURCE}",
        snapshot.tokens,
        _compose,
    )


def render_resource_stylesheet(resource: str, snapshot: ThemeSnapshot) -> str:
    """Pre-render one bundled QSS document, or a marker if the file is absent."""

    paths = split_qss_resource_key(resource)

    def _compose() -> str:
        marker = f"/* mygui-theme-resource:{resource}:{snapshot.scheme.value} */\n"
        try:
            for path in paths:
                resource_path(path)
        except (FileNotFoundError, ValueError):
            from .chrome import render_placeholder_resource_qss

            return render_placeholder_resource_qss(resource, snapshot)
        return marker + compose_component_stylesheet(resource, snapshot.tokens)

    return _cached_resource_document(
        f"theme-doc:{resource}",
        snapshot.tokens,
        _compose,
    )


class BundledQssRenderer:
    """Expand bundled QSS from ``ThemeSnapshot`` tokens with no widget side effects."""

    def render_application(self, snapshot: ThemeSnapshot) -> str:
        return render_application_stylesheet(snapshot)

    def render_resource(self, resource: str, snapshot: ThemeSnapshot) -> str:
        if resource == MAINWINDOW_QSS_RESOURCE:

            def _compose() -> str:
                from mygui.widgets.mainwindow_init.basic_setting import (
                    render_mainwindow_stylesheet,
                )

                marker = (
                    f"/* mygui-theme-resource:{resource}:{snapshot.scheme.value} */\n"
                )
                return marker + compose_component_stylesheet(
                    resource,
                    snapshot.tokens,
                    regional=render_mainwindow_stylesheet(snapshot=snapshot),
                )

            return _cached_resource_document(
                f"theme-doc:{resource}",
                snapshot.tokens,
                _compose,
            )
        return render_resource_stylesheet(resource, snapshot)


def reset_qss_bindings_for_tests() -> None:
    """Drop live binds and restore the Light default. Tests only."""

    global _INSTALLED_BINDING, _DEFAULT_BINDING
    _BINDINGS.clear()
    _WATCHERS.clear()
    _INSTALLED_BINDING = None
    _DEFAULT_BINDING = QssThemeBinding(LIGHT_QSS_TOKENS)
    clear_qss_document_cache_for_tests()
    try:
        from .runtime import default_theme_runtime

        default_theme_runtime().binding_port = None
    except ImportError:
        pass
