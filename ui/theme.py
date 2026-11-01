"""Светлая и тёмная темы (Fusion + QPalette)."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {"light": "Светлая", "dark": "Тёмная"}


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(32, 34, 40))
    p.setColor(QPalette.WindowText, QColor(228, 230, 235))
    p.setColor(QPalette.Base, QColor(24, 26, 31))
    p.setColor(QPalette.AlternateBase, QColor(40, 43, 50))
    p.setColor(QPalette.ToolTipBase, QColor(50, 53, 62))
    p.setColor(QPalette.ToolTipText, QColor(228, 230, 235))
    p.setColor(QPalette.Text, QColor(228, 230, 235))
    p.setColor(QPalette.Button, QColor(45, 48, 56))
    p.setColor(QPalette.ButtonText, QColor(228, 230, 235))
    p.setColor(QPalette.BrightText, QColor(255, 90, 90))
    p.setColor(QPalette.Link, QColor(110, 170, 255))
    p.setColor(QPalette.Highlight, QColor(70, 120, 200))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 122, 128))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 122, 128))
    return p


def apply_theme(app: QApplication, name: str) -> str:
    """Применяет тему и возвращает фактически применённое имя."""
    app.setStyle("Fusion")
    if name == "light":
        app.setPalette(app.style().standardPalette())
    else:
        name = "dark"
        app.setPalette(_dark_palette())
    return name


def is_dark(app: QApplication) -> bool:
    return app.palette().color(QPalette.Window).lightness() < 128
