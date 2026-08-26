"""Positive fixture: application chrome published outside ThemeService."""
from PySide6.QtWidgets import QApplication


class ThemeBypassPanel:
    def publish(self, app, font, palette):
        app.setFont(font)
        app.setPalette(palette)
        app.setStyleSheet("QWidget { color: red; }")
        QApplication.setFont(font)

    def publish_via_instance(self, font):
        QApplication.instance().setFont(font)
        QApplication.instance().setPalette(font)
        QApplication.instance().setStyleSheet("QWidget { color: red; }")

    def local_widget_font_ok(self, title, font):
        title.setFont(font)
