"""Positive fixture: QSettings construction outside widgets is still a bypass."""
from PySide6.QtCore import QSettings


def leak_native_store():
    return QSettings("MyGUI", "MyGUI")
