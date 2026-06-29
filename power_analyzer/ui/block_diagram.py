"""Compact static block diagram of the DSP signal chain.

Mirrors the flow-chart on page 2 of ``TP4_ASSD.pdf`` so the user always has,
at a glance, the map of what every scope probe and measurement corresponds to.
Drawn in the bottom-left of the window where there is spare vertical room.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from . import theme

# (title, subtitle, accent color) -- colours echo the PDF flow-chart.
_STAGES = [
    ("Filtro Anti-Alias", "Pasa-bajos · 2 kHz", theme.BLUE),
    ("ADC / Decimación", "fs = 5 kHz · 16 bit", theme.BLUE),
    ("Filtro Pasa-altos", "Digital 1 Hz · quita DC", theme.BLUE),
    ("Cruce por Cero", "bloques de 10 ciclos · f_est", theme.AMBER),
]
_SPLIT = [
    ("Goertzel · Hann", "Vf, If, φ, THD", theme.CYAN),
    ("Cálculo Temporal", "Vrms, Irms, P, S", theme.RED),
]
_OUTPUT = ("Promediado y Salida", "promedia N bloques", theme.GREEN)

_ALIGN_C = (QtCore.Qt.AlignmentFlag.AlignHCenter
            | QtCore.Qt.AlignmentFlag.AlignVCenter)


class BlockDiagram(QtWidgets.QWidget):
    """Static, painted vertical flow-chart of the processing chain."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(210, 300)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Expanding)

    def sizeHint(self):  # noqa: N802 (Qt naming)
        return QtCore.QSize(340, 360)

    # -- drawing helpers --
    def _box(self, p, rect, title, sub, color):
        c = QtGui.QColor(color)
        fill = QtGui.QColor(color)
        fill.setAlpha(30)
        p.setPen(QtGui.QPen(c, 1.4))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 6, 6)

        f = p.font()
        f.setBold(True)
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(c)
        tr = QtCore.QRectF(rect.x() + 3, rect.y() + 3,
                           rect.width() - 6, rect.height() * 0.52)
        p.drawText(tr, _ALIGN_C, title)

        f.setBold(False)
        f.setPixelSize(8)
        p.setFont(f)
        p.setPen(QtGui.QColor(theme.TEXT_DIM))
        sr = QtCore.QRectF(rect.x() + 3, rect.y() + rect.height() * 0.50,
                           rect.width() - 6, rect.height() * 0.50 - 3)
        p.drawText(sr, _ALIGN_C, sub)

    def _line(self, p, x1, y1, x2, y2):
        p.setPen(QtGui.QPen(QtGui.QColor(theme.TEXT_DIM), 1.3))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

    def _arrow_down(self, p, x1, y1, x2, y2):
        """Connector ending in a downward arrowhead at (x2, y2)."""
        self._line(p, x1, y1, x2, y2)
        a = 4.0
        head = QtGui.QPolygonF([
            QtCore.QPointF(x2, y2),
            QtCore.QPointF(x2 - a, y2 - 1.7 * a),
            QtCore.QPointF(x2 + a, y2 - 1.7 * a),
        ])
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(theme.TEXT_DIM))
        p.drawPolygon(head)

    def paintEvent(self, _ev):  # noqa: N802 (Qt naming)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        W, H = float(self.width()), float(self.height())
        mx = 6.0
        box_w = W - 2 * mx
        cx = W / 2.0

        label_h = 22.0
        gap = 8.0
        n_boxes = len(_STAGES) + 2  # stage boxes + split row + output
        box_h = (H - label_h - (n_boxes + 1) * gap) / n_boxes
        box_h = max(26.0, min(box_h, 50.0))

        used = label_h + (n_boxes + 1) * gap + n_boxes * box_h
        y = max(0.0, (H - used) / 2.0)

        # input label
        p.setPen(QtGui.QColor(theme.TEXT))
        f = p.font()
        f.setBold(True)
        f.setPixelSize(10)
        p.setFont(f)
        p.drawText(QtCore.QRectF(mx, y, box_w, label_h), _ALIGN_C,
                   "Señales analógicas  v(t), i(t)")
        prev_x, prev_y = cx, y + label_h
        y += label_h + gap

        # single-column stage boxes
        for title, sub, color in _STAGES:
            rect = QtCore.QRectF(mx, y, box_w, box_h)
            self._arrow_down(p, prev_x, prev_y, cx, y)
            self._box(p, rect, title, sub, color)
            prev_x, prev_y = cx, y + box_h
            y += box_h + gap

        # branch into the two parallel analysis paths
        sw = box_w * 0.47
        left_rect = QtCore.QRectF(mx, y, sw, box_h)
        right_rect = QtCore.QRectF(W - mx - sw, y, sw, box_h)
        lc, rc = left_rect.center().x(), right_rect.center().x()
        branch_y = prev_y + gap / 2.0
        self._line(p, prev_x, prev_y, cx, branch_y)
        self._line(p, lc, branch_y, rc, branch_y)
        self._arrow_down(p, lc, branch_y, lc, y)
        self._arrow_down(p, rc, branch_y, rc, y)
        self._box(p, left_rect, *_SPLIT[0])
        self._box(p, right_rect, *_SPLIT[1])
        split_bottom = y + box_h
        y += box_h + gap

        # merge back into the output box
        out_rect = QtCore.QRectF(mx, y, box_w, box_h)
        merge_y = split_bottom + gap / 2.0
        self._line(p, lc, split_bottom, lc, merge_y)
        self._line(p, rc, split_bottom, rc, merge_y)
        self._line(p, lc, merge_y, rc, merge_y)
        self._arrow_down(p, cx, merge_y, cx, y)
        self._box(p, out_rect, *_OUTPUT)
        p.end()
