"""Negative fixture: the storage adapter may construct and mutate QSettings."""
from PySide6.QtCore import QSettings


class SettingsBackend:
    def open(self):
        return QSettings(self.file_name, QSettings.Format.IniFormat)

    def commit(self):
        self._store.setValue(self.key, self.encoded)
        self._store.beginGroup("applicationSettings")
        self._store.endGroup()
        self._store.sync()
