"""Shared Inspector form wrapping and expanding-field policies."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from mygui.application_theme import current_density_metrics

# Qt treats minimumWidth 0 as "use sizeHint". A 1px floor lets layouts shrink.
SAFE_MIN_WIDTH = 1
_COMBO_MIN_CONTENTS = 6


class CurrentPageStackedWidget(QStackedWidget):
    """Size to the visible page instead of the widest hidden Inspector page."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.currentChanged.connect(self._page_changed)

    def _page_changed(self, _index: int) -> None:
        del _index
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        current = self.currentWidget()
        if current is None:
            return super().minimumSizeHint()
        return current.minimumSizeHint()


def configure_inspector_form(form: QFormLayout) -> None:
    """Wrap long labels and let non-fixed fields shrink with the Inspector."""

    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    metrics = current_density_metrics()
    form.setHorizontalSpacing(metrics.spacing_sm)
    form.setVerticalSpacing(metrics.spacing_xs)
    form.setContentsMargins(0, 0, 0, 0)


def apply_expanding_field(widget: QWidget) -> None:
    """Allow Inspector editors to shrink to the panel width."""

    widget.setMinimumWidth(SAFE_MIN_WIDTH)
    if isinstance(widget, QComboBox):
        widget.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        widget.setMinimumContentsLength(_COMBO_MIN_CONTENTS)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return
    if isinstance(widget, (QLineEdit, QAbstractSpinBox)):
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return
    policy = widget.sizePolicy()
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, policy.verticalPolicy())


def labeled_form_row(text: str, *, tooltip: str = "") -> QLabel:
    """Return a wrapping form label with an optional full-description tooltip."""

    label = QLabel(text)
    label.setWordWrap(True)
    label.setMinimumWidth(SAFE_MIN_WIDTH)
    if tooltip:
        label.setToolTip(tooltip)
    return label
