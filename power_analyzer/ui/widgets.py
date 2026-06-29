"""Small reusable UI building blocks."""

from __future__ import annotations

from PyQt6 import QtWidgets

from . import theme


class Panel(QtWidgets.QFrame):
    """A titled, bordered panel with a vertical content layout."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._title = QtWidgets.QLabel(title)
        self._title.setObjectName("panelTitle")
        outer.addWidget(self._title)

        self.body = QtWidgets.QWidget()
        self.content = QtWidgets.QVBoxLayout(self.body)
        self.content.setContentsMargins(10, 8, 10, 10)
        self.content.setSpacing(8)
        outer.addWidget(self.body, 1)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def add(self, widget: QtWidgets.QWidget, stretch: int = 0) -> None:
        self.content.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self.content.addLayout(layout)


class FillBar(QtWidgets.QWidget):
    """ADC range-utilisation bar: green fill that turns red on clip."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self._pct = 0.0
        self._clipped = False

    def set_value(self, pct: float, clipped: bool) -> None:
        self._pct = max(0.0, min(pct, 120.0))
        self._clipped = clipped
        self.update()

    def paintEvent(self, _event):  # noqa: N802 (Qt naming)
        from PyQt6 import QtGui, QtCore

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)

        p.setPen(QtGui.QPen(QtGui.QColor(theme.BORDER)))
        p.setBrush(QtGui.QColor(theme.BG_PANEL_2))
        p.drawRoundedRect(r, 4, 4)

        frac = min(self._pct, 100.0) / 100.0
        fill_w = int(r.width() * frac)
        if fill_w > 0:
            grad = QtGui.QLinearGradient(0, 0, r.width(), 0)
            if self._clipped or self._pct > 100.0:
                grad.setColorAt(0.0, QtGui.QColor(theme.AMBER))
                grad.setColorAt(1.0, QtGui.QColor(theme.RED))
            else:
                grad.setColorAt(0.0, QtGui.QColor(theme.BLUE))
                grad.setColorAt(1.0, QtGui.QColor(theme.GREEN))
            fr = QtCore.QRect(r.left(), r.top(), fill_w, r.height())
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            p.drawRoundedRect(fr, 4, 4)

        p.setPen(QtGui.QColor(theme.TEXT))
        label = f"{self._pct:.0f}%  CLIP" if self._clipped else f"{self._pct:.0f}%"
        p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, label)
        p.end()
