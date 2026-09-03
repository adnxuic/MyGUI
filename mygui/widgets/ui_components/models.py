"""Closed semantic values for workbench chrome controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UiRole(StrEnum):
    """Closed control roles understood by component QSS."""

    BUTTON = "button"
    ICON_BUTTON = "icon-button"
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    NUMBER = "number"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TABS = "tabs"
    CARD = "card"
    ALERT = "alert"
    BADGE = "badge"
    EMPTY_STATE = "empty-state"
    TREE = "tree"
    TABLE = "table"
    SECTION = "section"
    STATUS = "status"
    PROGRESS = "progress"


class UiVariant(StrEnum):
    """Closed visual variants. Default button appearance is outline."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    OUTLINE = "outline"
    GHOST = "ghost"
    DESTRUCTIVE = "destructive"


class UiSize(StrEnum):
    """Closed control sizes derived from DensityMetrics."""

    SMALL = "small"
    DEFAULT = "default"
    LARGE = "large"
    ICON = "icon"


class UiTone(StrEnum):
    """Closed status tones for alerts, badges, and empty states."""

    NEUTRAL = "neutral"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class UiTextRole(StrEnum):
    """Closed typography roles. Sizes come from ThemeService tokens."""

    PAGE_TITLE = "page-title"
    SECTION_TITLE = "section-title"
    LABEL = "label"
    BODY = "body"
    MUTED = "muted"
    CAPTION = "caption"
    VALUE = "value"


@dataclass(frozen=True, slots=True)
class UiComponentSpec:
    """Validated semantic annotation for one native Qt widget."""

    role: UiRole
    variant: UiVariant = UiVariant.OUTLINE
    size: UiSize = UiSize.DEFAULT
    tone: UiTone = UiTone.NEUTRAL
    invalid: bool = False


PROPERTY_ROLE = "uiRole"
PROPERTY_VARIANT = "uiVariant"
PROPERTY_SIZE = "uiSize"
PROPERTY_TONE = "uiTone"
PROPERTY_INVALID = "uiInvalid"
PROPERTY_TEXT_ROLE = "uiTextRole"
PROPERTY_BUSY = "uiBusy"
