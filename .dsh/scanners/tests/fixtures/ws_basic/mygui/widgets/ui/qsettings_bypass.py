"""Positive fixture: QSettings constructed and mutated outside the storage adapter."""
from PySide6.QtCore import QSettings


class SettingsBypassPanel:
    def open_private_store(self):
        store = QSettings()
        store.beginGroup("workspaceLayout")
        store.setValue("version", 2)
        store.endGroup()

    def type_annotation_ok(self, settings: QSettings | None = None):
        return settings

    def alias_construction(self):
        QS = QSettings
        return QS()

    def alias_set_value(self, settings):
        prefs = settings
        prefs.setValue("version", 2)
