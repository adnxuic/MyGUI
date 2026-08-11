"""Display persistent application state in the bottom bar."""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel


StateListener = Callable[[bool], None]


@dataclass(frozen=True)
class FeatureIndicator:
    """Describes one feature whose enabled state is shown in the State Bar.

    Adding a new feature only requires providing another FeatureIndicator:
    a display label, a getter for the current state, and functions to
    register/unregister a state-change listener.
    """

    name: str
    label: str
    is_enabled: Callable[[], bool]
    register_listener: Callable[[StateListener], None]
    unregister_listener: Callable[[StateListener], None]


class PyStateBar(QFrame):
    # Emitted from any thread when a listener fires; delivered to the GUI
    # thread (queued when cross-thread) so labels are only touched there.
    """Provide the py state bar Qt widget."""

    state_changed = Signal(str, bool)

    def __init__(self, indicators=(), parent=None):
        super().__init__(parent)

        self.setObjectName("state_bar")
        self.setAccessibleName("Optional integrations status")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(12)

        self._labels: dict[str, QLabel] = {}
        self._listeners: list[tuple[FeatureIndicator, StateListener]] = []

        self.state_changed.connect(self._apply_state)

        for indicator in indicators:
            self._add_indicator(indicator)

    def _add_indicator(self, indicator: FeatureIndicator):
        label = QLabel()
        label.setObjectName("state_bar_indicator")
        label.setProperty("featureLabel", indicator.label)
        label.setTextFormat(Qt.PlainText)
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.layout.addWidget(label)
        self._labels[indicator.name] = label

        def listener(enabled, name=indicator.name):
            self.state_changed.emit(name, bool(enabled))

        indicator.register_listener(listener)
        self._listeners.append((indicator, listener))

        self._set_label_state(label, indicator.is_enabled())

    @Slot(str, bool)
    def _apply_state(self, name: str, enabled: bool):
        label = self._labels.get(name)
        if label is not None:
            self._set_label_state(label, enabled)

    @staticmethod
    def _set_label_state(label: QLabel, enabled: bool):
        state = "on" if enabled else "off"
        state_label = "On" if enabled else "Off"
        symbol = "\u25cf" if enabled else "\u25cb"
        feature_label = str(label.property("featureLabel") or "Feature")

        label.setProperty("state", state)
        label.setText(f"{symbol} {feature_label} {state_label}")
        label.setAccessibleName(f"{feature_label}: {state_label}")
        label.setToolTip(f"{feature_label} is {state_label.lower()}")
        label.style().unpolish(label)
        label.style().polish(label)

    def cleanup(self):
        """Release resources and detach registered callbacks."""

        for indicator, listener in self._listeners:
            indicator.unregister_listener(listener)
        self._listeners.clear()
