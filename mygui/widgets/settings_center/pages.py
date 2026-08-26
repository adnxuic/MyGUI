"""Settings Center page registry. Field keywords come from SettingsRegistry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mygui.application_settings.keys import (
    PAGE_APPEARANCE,
    PAGE_EXPORT,
    PAGE_IDS,
    PAGE_INTEGRATIONS,
    PAGE_MAINTENANCE,
    PAGE_NEW_FIGURE,
    PAGE_WORKSPACE,
)
from mygui.application_settings.registry import SettingsRegistry, production_settings_registry


@runtime_checkable
class SettingsPageHost(Protocol):
    """Narrow host injected into page factories. Pages do not own the session."""

    def draft_value(self, key: str) -> Any:
        """Return the committed value with the session dirty patch applied."""

    def stage_value(self, key: str, value: Any) -> None:
        """Stage one persisted key on the open session and preview LIVE keys."""

    def request_immediate_command(
        self,
        command_id: str,
        *,
        title: str,
        text: str,
        handler: Callable[[], None],
        confirm: bool = True,
    ) -> None:
        """Run a confirmed command that must not ride the Apply patch."""

    def emit_message(self, text: str, level: str = "info") -> None:
        """Forward at most one Message Bar result for the current user action."""

    def bind_draft_reloaded(self, callback: Callable[[], None]) -> None:
        """Register a reload hook for the page currently being constructed."""

    def reset_all_preferences(self) -> None:
        """Stage built-in defaults once and reload every created page."""

    def apply_storage_reset(self) -> None:
        """Apply committed appearance and reload pages after storage reset."""


PageFactory = Callable[[SettingsPageHost], QWidget]


@dataclass(frozen=True, slots=True)
class SettingsCenterPageSpec:
    """One Settings Center page. ``factory`` is called once on first visit."""

    page_id: str
    title: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    factory: PageFactory | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "page_id", str(self.page_id).strip())
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(
            self,
            "keywords",
            tuple(str(item) for item in self.keywords if str(item).strip()),
        )
        if not self.page_id:
            raise ValueError("SettingsCenterPageSpec.page_id must be non-empty.")
        if not self.title.strip():
            raise ValueError("SettingsCenterPageSpec.title must be non-empty.")


SHELL_PAGE_ORDER = (
    PAGE_APPEARANCE,
    PAGE_WORKSPACE,
    PAGE_NEW_FIGURE,
    PAGE_EXPORT,
    PAGE_INTEGRATIONS,
    PAGE_MAINTENANCE,
)

SHELL_PAGE_METADATA: Mapping[str, SettingsCenterPageSpec] = {
    PAGE_APPEARANCE: SettingsCenterPageSpec(
        page_id=PAGE_APPEARANCE,
        title="Appearance",
        description="Theme, UI font size, and density.",
    ),
    PAGE_WORKSPACE: SettingsCenterPageSpec(
        page_id=PAGE_WORKSPACE,
        title="Workspace",
        description="Remember workspace layout and Explorer restore.",
    ),
    PAGE_NEW_FIGURE: SettingsCenterPageSpec(
        page_id=PAGE_NEW_FIGURE,
        title="New Figure",
        description="Default Figure size and document DPI.",
    ),
    PAGE_EXPORT: SettingsCenterPageSpec(
        page_id=PAGE_EXPORT,
        title="Export",
        description="Default export format, DPI, and encoding.",
    ),
    PAGE_INTEGRATIONS: SettingsCenterPageSpec(
        page_id=PAGE_INTEGRATIONS,
        title="Integrations",
        description="TeX and MATLAB availability and session actions.",
        keywords=("TeX", "MATLAB"),
    ),
    PAGE_MAINTENANCE: SettingsCenterPageSpec(
        page_id=PAGE_MAINTENANCE,
        title="Maintenance",
        description="Storage health and confirmed maintenance commands.",
    ),
}


def standard_page_spec(
    page_id: str,
    factory: PageFactory | None = None,
    *,
    title: str | None = None,
    description: str | None = None,
    keywords: tuple[str, ...] | None = None,
) -> SettingsCenterPageSpec:
    """Build a page spec using the shell's English titles when present."""

    base = SHELL_PAGE_METADATA.get(page_id)
    if base is None:
        return SettingsCenterPageSpec(
            page_id=page_id,
            title=title or page_id.replace("_", " ").title(),
            description=description or "",
            keywords=keywords or (),
            factory=factory,
        )
    return SettingsCenterPageSpec(
        page_id=base.page_id,
        title=title if title is not None else base.title,
        description=description if description is not None else base.description,
        keywords=keywords if keywords is not None else base.keywords,
        factory=factory,
    )


def empty_page_factory(_host: SettingsPageHost) -> QWidget:
    """Placeholder used until B/C register a real page factory."""

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel("This page has no settings yet.")
    label.setWordWrap(True)
    label.setObjectName("settings_page_placeholder")
    layout.addWidget(label)
    layout.addStretch(1)
    return widget


def persisted_page_ids() -> frozenset[str]:
    """Pages whose Restore page defaults path may call ``reset_section``."""

    return frozenset(PAGE_IDS)


def registry_field_keywords(
    settings_registry: SettingsRegistry,
    page_id: str,
) -> tuple[str, ...]:
    """Return SettingSpec key/label/tooltip text. Do not invent a second catalog."""

    parts: list[str] = []
    for spec in settings_registry.persistent_specs():
        if spec.page_id != page_id:
            continue
        parts.append(spec.key)
        if spec.label:
            parts.append(spec.label)
        if spec.tooltip:
            parts.append(spec.tooltip)
        if spec.choices:
            for choice in spec.choices:
                parts.append(str(getattr(choice, "value", choice)))
                name = getattr(choice, "name", None)
                if name:
                    parts.append(str(name))
    return tuple(parts)


def page_search_haystack(
    spec: SettingsCenterPageSpec,
    settings_registry: SettingsRegistry,
) -> str:
    """Lowercased search text: page fields plus SettingsRegistry spec keywords."""

    chunks = [
        spec.page_id,
        spec.title,
        spec.description,
        *spec.keywords,
        *registry_field_keywords(settings_registry, spec.page_id),
    ]
    return " ".join(str(item) for item in chunks if item).casefold()


def page_matches(
    spec: SettingsCenterPageSpec,
    query: str,
    settings_registry: SettingsRegistry | None = None,
) -> bool:
    """Return whether ``query`` matches the page or its registered field keywords."""

    needle = query.strip().casefold()
    if not needle:
        return True
    registry = settings_registry or production_settings_registry()
    return needle in page_search_haystack(spec, registry)


class SettingsPageRegistry:
    """Ordered UI page catalog. Replacing a spec before first visit swaps the factory."""

    def __init__(self) -> None:
        self._specs: dict[str, SettingsCenterPageSpec] = {}
        self._order: list[str] = []

    def register_page(self, spec: SettingsCenterPageSpec) -> None:
        """Register or replace a page. Duplicate ids update in place."""

        if not isinstance(spec, SettingsCenterPageSpec):
            raise TypeError("spec must be a SettingsCenterPageSpec.")
        if spec.page_id in self._specs:
            self._specs[spec.page_id] = spec
            return
        self._specs[spec.page_id] = spec
        self._order.append(spec.page_id)

    def get(self, page_id: str) -> SettingsCenterPageSpec:
        try:
            return self._specs[page_id]
        except KeyError as exc:
            raise KeyError(f"Unknown settings page {page_id!r}.") from exc

    def pages(self) -> tuple[SettingsCenterPageSpec, ...]:
        return tuple(self._specs[page_id] for page_id in self._order)

    def page_ids(self) -> tuple[str, ...]:
        return tuple(self._order)

    def __contains__(self, page_id: object) -> bool:
        return page_id in self._specs

    def __len__(self) -> int:
        return len(self._order)

    def with_factory(
        self,
        page_id: str,
        factory: PageFactory,
    ) -> SettingsCenterPageSpec:
        """Replace only the factory for an already registered page."""

        current = self.get(page_id)
        updated = replace(current, factory=factory)
        self._specs[page_id] = updated
        return updated
