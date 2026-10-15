"""Lista ordenada das etapas da receita, com reordenação por arrastar.

A ordem das etapas é a ordem física do processo, então arrastar uma etapa é
uma edição de verdade: a lista avisa o dono quando a ordem muda.

A linha é pintada por um delegate (número, tipo, resumo, marca de estado) em
vez de montada com widgets dentro dos itens — assim o arrastar do próprio
QListWidget continua funcionando e a rolagem por roda do mouse vem do Qt, sem
nenhum tratamento manual de evento.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QListWidget, QListWidgetItem,
                               QStyle, QStyledItemDelegate)

from ...core.recipe import Step
from .. import theme

ROLE_UID = int(Qt.ItemDataRole.UserRole)
ROLE_TYPE = ROLE_UID + 1
ROLE_SUMMARY = ROLE_UID + 2
ROLE_NUMBER = ROLE_UID + 3
ROLE_MARK = ROLE_UID + 4          # "", "!", "●", "✓"


class StepDelegate(QStyledItemDelegate):
    """Desenha a linha de uma etapa como no arquivo de design."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 - API do Qt
        return QSize(0, theme.space("16") + theme.space("12"))

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        mark = index.data(ROLE_MARK) or ""
        radius = theme.radius("md")
        rect = option.rect.adjusted(0, 0, -1, -theme.space("1"))

        if selected:
            painter.setBrush(theme.qcolor("bg-3"))
            painter.setPen(QPen(theme.qcolor("line-strong"), theme.dimension("border")))
        elif hovered:
            painter.setBrush(theme.qcolor("bg-2"))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(Qt.PenStyle.NoPen)
        if selected or hovered:
            painter.drawRoundedRect(rect, radius, radius)

        pad = theme.space("5")
        x = rect.left() + pad
        erro = mark == "!"

        # alça de arrastar
        painter.setPen(theme.qcolor("ink-faint"))
        painter.setFont(theme.font("sans", "tiny"))
        painter.drawText(QRect(x, rect.top(), theme.space("6"), rect.height()),
                         int(Qt.AlignmentFlag.AlignCenter), "⋮⋮")
        x += theme.space("6") + theme.space("4")

        # número da etapa
        painter.setPen(theme.qcolor("accent-ink") if erro else theme.qcolor("ink-dim"))
        painter.setFont(theme.font("mono", "small"))
        num_w = theme.space("11")
        painter.drawText(QRect(x, rect.top(), num_w, rect.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         str(index.data(ROLE_NUMBER) or ""))
        x += num_w + theme.space("4")

        mark_w = theme.space("8")
        text_w = rect.right() - x - mark_w - pad
        meio = rect.top() + rect.height() // 2

        # tipo (versalete monospace) e resumo
        painter.setPen(theme.qcolor("ink-dim"))
        painter.setFont(theme.font("mono", "micro", "regular", "wider"))
        painter.drawText(QRect(x, rect.top() + theme.space("3"), text_w, meio - rect.top()),
                         int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft),
                         str(index.data(ROLE_TYPE) or "").upper())

        painter.setPen(theme.qcolor("ink"))
        painter.setFont(theme.font("sans", "base"))
        resumo = str(index.data(ROLE_SUMMARY) or "")
        metrics = painter.fontMetrics()
        painter.drawText(
            QRect(x, meio - theme.space("2"), text_w, rect.bottom() - meio),
            int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft),
            metrics.elidedText(resumo, Qt.TextElideMode.ElideRight, text_w))

        # marca de estado
        if mark:
            cor = "accent-ink" if mark in ("!", "●") else "ink-dim"
            painter.setPen(theme.qcolor(cor))
            painter.setFont(theme.font("mono", "small", "semibold"))
            painter.drawText(
                QRect(rect.right() - mark_w - pad, rect.top(), mark_w, rect.height()),
                int(Qt.AlignmentFlag.AlignCenter), mark)

        painter.restore()


class StepList(QListWidget):
    """A lista de etapas. Emite ``reordered`` quando o usuário arrasta."""

    reordered = Signal(int, int)        # de, para
    step_selected = Signal(int)         # uid

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setItemDelegate(StepDelegate(self))
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self._drag_from = -1
        self.currentItemChanged.connect(self._on_current)

    # ── preenchimento ─────────────────────────────────────────────────────

    def populate(self, steps: list[Step], *, selected_uid: int | None = None,
                 issues: set[int] | None = None,
                 running_index: int = -1, done_before: int = -1) -> None:
        """Refaz a lista a partir da receita.

        ``issues`` são índices com problema, ``running_index`` é a etapa em
        curso e ``done_before`` o limite das já concluídas.
        """
        issues = issues or set()
        self.blockSignals(True)
        self.clear()
        for i, step in enumerate(steps):
            if i in issues:
                mark = "!"
            elif i == running_index:
                mark = "●"
            elif 0 <= i < done_before:
                mark = "✓"
            else:
                mark = ""
            item = QListWidgetItem()
            item.setData(ROLE_UID, step.uid)
            item.setData(ROLE_TYPE, step.type)
            item.setData(ROLE_SUMMARY, step.summary())
            item.setData(ROLE_NUMBER, f"{i + 1:02d}")
            item.setData(ROLE_MARK, mark)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
            self.addItem(item)
            if selected_uid is not None and step.uid == selected_uid:
                self.setCurrentItem(item)
        self.blockSignals(False)

    def selected_uid(self) -> int | None:
        item = self.currentItem()
        return None if item is None else int(item.data(ROLE_UID))

    # ── arrastar ──────────────────────────────────────────────────────────

    def startDrag(self, actions) -> None:  # noqa: N802 - API do Qt
        self._drag_from = self.currentRow()
        super().startDrag(actions)

    def dropEvent(self, event) -> None:  # noqa: N802 - API do Qt
        origem = self._drag_from
        super().dropEvent(event)
        destino = self.currentRow()
        self._drag_from = -1
        if origem >= 0 and destino >= 0 and origem != destino:
            self.reordered.emit(origem, destino)

    def _on_current(self, current, _previous) -> None:
        if current is not None:
            self.step_selected.emit(int(current.data(ROLE_UID)))
