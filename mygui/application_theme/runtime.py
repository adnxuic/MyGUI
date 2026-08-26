"""Injectable step-4 chrome applier and process-wide runtime hub.

ThemeService owns the transaction state machine. This module only applies
palette (to subscribed windows), metrics, and icons after font/QSS.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QFontMetrics, QPalette
from PySide6.QtWidgets import QApplication

from mygui.application_settings.models import Density

from .chrome import build_font, build_palette
from .icons import CachingThemeIconProvider
from .metrics import build_density_metrics
from .models import AppearancePreferences, EffectiveScheme, ThemeSnapshot
from .participants import ThemeMetricsApplier
from .ports import ThemeBindingPort, binding_apply
from .tokens import ICON_ROLES, build_tokens
from .windows import ThemeWindowRegistry, default_window_registry, reset_window_registry_for_tests


def compose_theme_snapshot(
    scheme: EffectiveScheme,
    preferences: AppearancePreferences | None = None,
    *,
    font_height: int | None = None,
) -> ThemeSnapshot:
    """Pre-render palette, font, metrics, and tokens with no widget side effects."""

    prefs = preferences if preferences is not None else AppearancePreferences()
    font = build_font(prefs.font_pt)
    height = int(font_height) if font_height is not None else int(QFontMetrics(font).height())
    metrics = build_density_metrics(prefs.density, height)
    tokens = build_tokens(scheme, metrics, prefs)
    palette = build_palette(tokens)
    return ThemeSnapshot(
        scheme=scheme,
        preferences=prefs,
        palette=palette,
        font=font,
        metrics=metrics,
        tokens=tokens,
        icon_roles=ICON_ROLES,
    )


class ThemeChromeRuntime:
    """Process hub: current snapshot, window registry, metrics and icon ports."""

    def __init__(
        self,
        *,
        registry: ThemeWindowRegistry | None = None,
        icon_provider: CachingThemeIconProvider | None = None,
        metrics_applier: ThemeMetricsApplier | None = None,
        binding_port: ThemeBindingPort | None = None,
    ) -> None:
        self.registry = registry if registry is not None else default_window_registry()
        self.icon_provider = (
            icon_provider if icon_provider is not None else CachingThemeIconProvider()
        )
        self.metrics_applier = (
            metrics_applier
            if metrics_applier is not None
            else ThemeMetricsApplier(self.registry)
        )
        self.binding_port = binding_port
        self.snapshot: ThemeSnapshot | None = None
        self._publisher: Any = None
        self._publisher_slot: Any = None

    def apply_palette(
        self,
        snapshot: ThemeSnapshot,
        *,
        application: QApplication | None = None,
    ) -> None:
        """Apply the prerendered QPalette to the app (optional) and subscribers."""

        palette = QPalette(snapshot.palette)
        if application is not None:
            application.setPalette(palette)
        self.registry.apply_palette(palette)

    def apply_metrics(self, snapshot: ThemeSnapshot) -> None:
        """Apply density metrics (ThemeService step 4, after QSS)."""

        self.metrics_applier.apply(snapshot.metrics)

    def apply_icons(self, snapshot: ThemeSnapshot) -> None:
        """Pre-render then apply chrome icons (ThemeService step 4, last)."""

        rendered = self.icon_provider.prerender(snapshot)
        self.icon_provider.apply(rendered)

    def apply_step4_chrome(
        self,
        snapshot: ThemeSnapshot,
        *,
        application: QApplication | None = None,
        rendered_qss: dict[str, str] | None = None,
    ) -> None:
        """Apply palette, optional local QSS, metrics, then icons.

        Call after ThemeService has applied font and application QSS. Do not
        use this to rewrite the transaction state machine.
        """

        self.apply_palette(snapshot, application=application)
        if rendered_qss is not None:
            binding_apply(self.binding_port, rendered_qss)
        self.apply_metrics(snapshot)
        self.apply_icons(snapshot)
        self.snapshot = snapshot

    def attach_publisher(self, publisher: Any) -> None:
        """Connect ``themeChanged(old, new)`` if ThemeService exposes it."""

        signal = getattr(publisher, "themeChanged", None)
        if signal is None:
            return
        if self._publisher is publisher and self._publisher_slot is not None:
            return
        self.detach_publisher()

        def _on_changed(_old: object, new: object, runtime: ThemeChromeRuntime = self) -> None:
            if isinstance(new, ThemeSnapshot):
                runtime.snapshot = new

        signal.connect(_on_changed)
        self._publisher = publisher
        self._publisher_slot = _on_changed

    def detach_publisher(self) -> None:
        """Disconnect a previously attached ThemeService publisher."""

        signal = getattr(self._publisher, "themeChanged", None) if self._publisher else None
        if signal is not None and self._publisher_slot is not None:
            try:
                signal.disconnect(self._publisher_slot)
            except (RuntimeError, TypeError):
                pass
        self._publisher = None
        self._publisher_slot = None


_RUNTIME: ThemeChromeRuntime | None = None


def default_theme_runtime() -> ThemeChromeRuntime:
    """Return the process-wide chrome runtime used by widgets and ThemeService."""

    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = ThemeChromeRuntime()
    return _RUNTIME


def reset_theme_runtime_for_tests() -> ThemeChromeRuntime:
    """Replace runtime and window registry so tests do not share cache or slots."""

    global _RUNTIME
    reset_window_registry_for_tests()
    _RUNTIME = ThemeChromeRuntime()
    return _RUNTIME


def current_theme_snapshot() -> ThemeSnapshot | None:
    """Return the last applied snapshot, if ThemeService or tests published one."""

    return default_theme_runtime().snapshot


def current_density_metrics():
    """Return applied metrics, or Standard × 9 pt when no snapshot exists yet."""

    snapshot = current_theme_snapshot()
    if snapshot is not None:
        return snapshot.metrics
    font = build_font(AppearancePreferences().font_pt)
    return build_density_metrics(Density.STANDARD, int(QFontMetrics(font).height()))


def apply_theme_chrome(
    snapshot: ThemeSnapshot,
    *,
    application: QApplication | None = None,
) -> None:
    """Public step-4 entry ThemeService should call after font and QSS."""

    default_theme_runtime().apply_step4_chrome(snapshot, application=application)


def compose_theme_service(
    application: QApplication,
    *,
    style_hints: Any | None = None,
    native_palette: QPalette | None = None,
    initial: AppearancePreferences | None = None,
):
    """Create ThemeService on the process chrome runtime.

    Shares icon/metrics ports with ``default_theme_runtime()`` so widgets and
    the appearance engine do not keep a second hub. Call after settings exist
    and before any ``QWidget``.
    """

    from .qss import BundledQssRenderer
    from .service import ThemeService

    runtime = default_theme_runtime()
    return ThemeService(
        application,
        style_hints=style_hints,
        native_palette=native_palette,
        icon_provider=runtime.icon_provider,
        metrics_port=runtime.metrics_applier,
        qss_renderer=BundledQssRenderer(),
        binding_port=runtime.binding_port,
        initial=initial,
    )


def try_attach_theme_service(service: Any | None = None) -> bool:
    """Attach ThemeService.themeChanged when the appearance engine exists."""

    publisher = service
    if publisher is None:
        try:
            from .service import ThemeService
        except ImportError:
            return False
        current = getattr(ThemeService, "current", None)
        publisher = current() if callable(current) else None
        if publisher is None:
            return False
    default_theme_runtime().attach_publisher(publisher)
    return True
