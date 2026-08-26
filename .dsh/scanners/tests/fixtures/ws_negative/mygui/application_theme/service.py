"""Negative fixture: ThemeService may publish application font, palette, and QSS."""


class ThemeService:
    def apply(self, font, palette, qss):
        self._app.setFont(font)
        self._app.setPalette(palette)
        self._app.setStyleSheet(qss)
        self.app.setFont(font)
