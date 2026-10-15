"""Lista de execuções, com marcação para comparar."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem,
                               QStyle, QStyledItemDelegate)

from ...core.workspace import RunRecord
from .. import theme

ROLE_PATH = int(Qt.ItemDataRole.UserRole)
ROLE_NAME = ROLE_PATH + 1
ROLE_WHEN = ROLE_PATH + 2
ROLE_STATUS = ROLE_PATH + 3
ROLE_CHECK = ROLE_PATH + 4
ROLE_NUMBER = ROLE_PATH + 5

STATUS_MARKS = {"ok": "✓", "parcial": "parcial", "erro": "erro",
                "cancelada": "cancelada"}


class RunDelegate(QStyledItemDelegate):
    """Uma linha: marca de comparação, número, nome, data e estado."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 - API do Qt
        return QSize(0, theme.space("16") + theme.space("14"))

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        selecionado = bool(option.state & QStyle.StateFlag.State_Selected)
        marcado = bool(index.data(ROLE_CHECK))
        estado = index.data(ROLE_STATUS) or "ok"
        rect = option.rect.adjusted(0, 0, -1, -theme.space("1"))

        if selecionado or marcado:
            painter.setBrush(theme.qcolor("bg-3"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, theme.radius("md"), theme.radius("md"))

        pad = theme.space("5")
        caixa = QRect(rect.left() + pad, rect.center().y() - theme.space("4"),
                      theme.space("8"), theme.space("8"))
        if marcado:
            painter.setBrush(theme.qcolor("accent"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(caixa, theme.radius("xs"), theme.radius("xs"))
            painter.setPen(theme.qcolor("bg"))
            painter.setFont(theme.font("sans", "tiny", "bold"))
            painter.drawText(caixa, int(Qt.AlignmentFlag.AlignCenter), "✓")
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(theme.qcolor("line-strong"))
            painter.drawRoundedRect(caixa, theme.radius("xs"), theme.radius("xs"))

        x = caixa.right() + theme.space("5")
        estado_txt = STATUS_MARKS.get(estado, estado)
        painter.setFont(theme.font("mono", "micro", "regular", "wide"))
        largura_estado = painter.fontMetrics().horizontalAdvance(estado_txt) + pad
        texto_w = rect.right() - x - largura_estado - pad

        painter.setPen(theme.qcolor("ink-dim"))
        painter.setFont(theme.font("mono", "tiny"))
        numero = f"#{index.data(ROLE_NUMBER)}"
        num_w = painter.fontMetrics().horizontalAdvance(numero) + theme.space("3")
        painter.drawText(QRect(x, rect.top() + theme.space("5"), num_w,
                               theme.space("10")),
                         int(Qt.AlignmentFlag.AlignLeft), numero)

        painter.setPen(theme.qcolor("ink"))
        painter.setFont(theme.font("sans", "base"))
        nome = painter.fontMetrics().elidedText(
            str(index.data(ROLE_NAME) or ""), Qt.TextElideMode.ElideRight,
            texto_w - num_w)
        painter.drawText(QRect(x + num_w, rect.top() + theme.space("5"),
                               texto_w - num_w, theme.space("10")),
                         int(Qt.AlignmentFlag.AlignLeft), nome)

        painter.setPen(theme.qcolor("ink-dim"))
        painter.setFont(theme.font("sans", "tiny"))
        painter.drawText(QRect(x, rect.top() + theme.space("14"), texto_w,
                               theme.space("10")),
                         int(Qt.AlignmentFlag.AlignLeft),
                         str(index.data(ROLE_WHEN) or ""))

        painter.setPen(theme.qcolor(
            "accent-ink" if estado in ("erro", "parcial") else "ink-dim"))
        painter.setFont(theme.font("mono", "micro", "regular", "wide"))
        painter.drawText(QRect(rect.right() - largura_estado - pad, rect.top(),
                               largura_estado, rect.height()),
                         int(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter), estado_txt)
        painter.restore()


class RunList(QListWidget):
    """A lista. Clique escolhe; clique na caixinha marca para comparar."""

    selected = Signal(object)        # RunRecord
    toggled = Signal(object)         # RunRecord

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(RunDelegate(self))
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setMouseTracking(True)
        self._records: list[RunRecord] = []
        self.itemClicked.connect(self._on_click)
        self._last_x = 0

    def populate(self, registros: list[RunRecord], *,
                 selected: RunRecord | None = None,
                 compared: set[str] | None = None) -> None:
        comparados = compared or set()
        self._records = registros
        self.blockSignals(True)
        self.clear()
        for r in registros:
            item = QListWidgetItem()
            item.setData(ROLE_PATH, str(r.path))
            item.setData(ROLE_NAME, r.name)
            item.setData(ROLE_WHEN, r.when_text)
            item.setData(ROLE_STATUS, r.status)
            item.setData(ROLE_NUMBER, r.number)
            item.setData(ROLE_CHECK, str(r.path) in comparados)
            self.addItem(item)
            if selected is not None and r.path == selected.path:
                self.setCurrentItem(item)
        self.blockSignals(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        self._last_x = int(event.position().x())
        super().mousePressEvent(event)

    def _on_click(self, item: QListWidgetItem) -> None:
        indice = self.row(item)
        if not (0 <= indice < len(self._records)):
            return
        registro = self._records[indice]
        if self._last_x <= theme.space("5") + theme.space("10"):
            self.toggled.emit(registro)
        else:
            self.selected.emit(registro)
