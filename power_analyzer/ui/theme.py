"""Oscilloscope / instrument visual theme: palette, QSS, and pyqtgraph pens."""

from __future__ import annotations

import pyqtgraph as pg
from PyQt6 import QtGui

# --- Palette ---------------------------------------------------------------
BG_DEEP = "#05080d"        # window background (near black, slight blue)
BG_PANEL = "#0b121c"       # panel background
BG_PANEL_2 = "#101a28"     # alternate / header
GRID = "#16324a"           # scope grid lines
GRID_FINE = "#0d2030"
BORDER = "#1d3a5c"

CYAN = "#19f0d8"           # voltage / primary neon
GREEN = "#39ff88"          # current / secondary neon
BLUE = "#2f8fff"           # accents
AMBER = "#ffb13b"          # warnings / highlights
RED = "#ff4d5e"            # clipping / errors
TEXT = "#cfe6f5"           # primary text
TEXT_DIM = "#6f8aa3"       # secondary text

# Channel colors keyed by stage tap.
V_COLOR = CYAN
I_COLOR = GREEN

# --- pyqtgraph global config ----------------------------------------------
pg.setConfigOptions(antialias=True, background=BG_DEEP, foreground=TEXT_DIM)


def trace_pen(color: str, width: float = 2.0) -> pg.mkPen:
    return pg.mkPen(color=color, width=width)


def faint_pen(color: str, width: float = 1.0) -> pg.mkPen:
    c = QtGui.QColor(color)
    c.setAlpha(110)
    return pg.mkPen(color=c, width=width)


def fill_brush(color: str, alpha: int = 45) -> QtGui.QBrush:
    c = QtGui.QColor(color)
    c.setAlpha(alpha)
    return QtGui.QBrush(c)


# --- Application stylesheet -------------------------------------------------
STYLESHEET = f"""
* {{
    font-family: "DejaVu Sans Mono", "Consolas", monospace;
    font-size: 12px;
    color: {TEXT};
}}
QMainWindow, QWidget#root {{
    background-color: {BG_DEEP};
}}
QFrame#panel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QLabel#panelTitle {{
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 1px;
    color: {CYAN};
    padding: 6px 10px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BG_PANEL_2}, stop:1 rgba(25,240,216,15));
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
QLabel#sectionTitle {{
    color: {BLUE};
    font-weight: bold;
    letter-spacing: 1px;
    padding-top: 4px;
}}
QLabel#metricLabel {{ color: {TEXT_DIM}; }}
QLabel#metricValue {{ color: {CYAN}; font-weight: bold; }}
QLabel#dimText {{ color: {TEXT_DIM}; }}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {BG_PANEL_2};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 3px 6px;
    selection-background-color: {BLUE};
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border: 1px solid {CYAN};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL_2};
    border: 1px solid {BORDER};
    selection-background-color: {BLUE};
}}

QSlider::groove:horizontal {{
    height: 4px; background: {BG_PANEL_2};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px; margin: -6px 0;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        stop:0 {CYAN}, stop:1 {BLUE});
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {BLUE}, stop:1 {CYAN});
    border-radius: 2px;
}}

QPushButton {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 {BG_PANEL_2}, stop:1 {BG_PANEL});
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 12px;
}}
QPushButton:hover {{ border: 1px solid {CYAN}; color: {CYAN}; }}
QPushButton:checked {{
    border: 1px solid {CYAN};
    color: {CYAN};
    background: rgba(25,240,216,20);
}}

QTableWidget {{
    background-color: {BG_PANEL};
    gridline-color: {GRID_FINE};
    border: none;
}}
QHeaderView::section {{
    background-color: {BG_PANEL_2};
    color: {BLUE};
    border: none;
    padding: 4px;
    font-weight: bold;
}}
QTableWidget::item {{ padding: 2px 6px; }}

QScrollBar:vertical {{ background: {BG_PANEL}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 1px solid {BORDER}; border-radius: 3px;
    background: {BG_PANEL_2};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {CYAN}; border: 1px solid {CYAN};
}}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; }}
QTabBar::tab {{
    background: {BG_PANEL}; padding: 6px 14px;
    border: 1px solid {BORDER}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ color: {CYAN}; background: {BG_PANEL_2}; }}
"""
