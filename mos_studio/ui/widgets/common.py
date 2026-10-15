"""Peças reutilizadas pela interface: rótulos, divisores, pílulas e o pulso.

Nenhuma cor ou fonte literal: tudo vem de :mod:`mos_studio.ui.theme`.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                               QWidget)

from .. import theme


# ── Rótulos ───────────────────────────────────────────────────────────────

def label(text: str, role: str = "", *, wrap: bool = False,
          parent: QWidget | None = None) -> QLabel:
    """Rótulo com um papel tipográfico do tema."""
    lb = QLabel(text, parent)
    if role:
        theme.mark(lb, role=role)
    lb.setWordWrap(wrap)
    if role in ("eyebrow", "eyebrow-accent"):
        lb.setText(text.upper())   # o Qt não implementa text-transform
        lb.setFont(theme.font("mono", "micro", "medium", "widest"))
    elif role == "mono":
        lb.setFont(theme.font("mono", "small"))
    elif role == "display":
        lb.setFont(theme.font("display", "h1", "medium", "tight"))
    elif role == "title":
        lb.setFont(theme.font("display", "h3", "medium", "tight"))
    elif role == "metric":
        lb.setFont(theme.font("display", "display", "medium", "tighter"))
    elif role == "serif":
        lb.setFont(theme.font("serif", "title", italic=True))
    elif role == "brand":
        lb.setFont(theme.font("display", "lead", "medium", "tight"))
    return lb


def eyebrow(text: str, accent: bool = False) -> QLabel:
    """Rótulo pequeno em versalete monospace, como no design."""
    return label(text, "eyebrow-accent" if accent else "eyebrow")


# ── Divisores e espaçadores ───────────────────────────────────────────────

def hline(strong: bool = False) -> QFrame:
    """Linha horizontal de 1px."""
    f = QFrame()
    theme.mark(f, role="hline-strong" if strong else "hline")
    f.setFixedHeight(theme.dimension("border"))
    return f


def vline() -> QFrame:
    """Linha vertical de 1px."""
    f = QFrame()
    theme.mark(f, role="vline")
    f.setFixedWidth(theme.dimension("border"))
    return f


def stretch() -> QWidget:
    """Espaçador que empurra o resto da linha."""
    w = QWidget()
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return w


def row(*widgets: QWidget, spacing: str = "5",
        margins: tuple[int, int, int, int] | None = None) -> QWidget:
    """Agrupa widgets numa linha horizontal."""
    host = QWidget()
    lay = QHBoxLayout(host)
    lay.setSpacing(theme.space(spacing))
    lay.setContentsMargins(*(margins or (0, 0, 0, 0)))
    for w in widgets:
        lay.addWidget(w)
    return host


def column(*widgets: QWidget, spacing: str = "5",
           margins: tuple[int, int, int, int] | None = None) -> QWidget:
    """Agrupa widgets numa coluna."""
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setSpacing(theme.space(spacing))
    lay.setContentsMargins(*(margins or (0, 0, 0, 0)))
    for w in widgets:
        lay.addWidget(w)
    return host


# ── Botões ────────────────────────────────────────────────────────────────

def button(text: str, variant: str = "", *, tooltip: str = "",
           checkable: bool = False, on_click=None) -> QPushButton:
    """Botão com uma das variantes do tema."""
    b = QPushButton(text)
    if variant:
        theme.mark(b, variant=variant)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setCheckable(checkable)
    if tooltip:
        b.setToolTip(tooltip)
    if on_click is not None:
        b.clicked.connect(on_click)
    if variant == "nav":
        b.setFont(theme.font("sans", "body", "medium"))
    return b


class Segmented(QWidget):
    """Escolha entre poucos valores, no formato de pílulas do design.

    Substitui o combobox para campos de domínio fechado (ambiente, material,
    dopante): o design mostra as opções, não um menu que as esconde.
    """

    def __init__(self, options: list[tuple[str, str]], value: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._options = options
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space("3"))
        for i, (val, lbl) in enumerate(options):
            b = button(lbl, "segment", checkable=True)
            b.setProperty("value", val)
            self._group.addButton(b, i)
            lay.addWidget(b)
        lay.addStretch(1)
        self.set_value(value)

    @property
    def changed(self):
        """Sinal emitido quando a escolha muda (``idClicked`` do grupo)."""
        return self._group.idClicked

    def value(self) -> str:
        b = self._group.checkedButton()
        return "" if b is None else str(b.property("value"))

    def set_value(self, value: str) -> None:
        for b in self._group.buttons():
            b.setChecked(str(b.property("value")) == value)


# ── Pulso do indicador de execução ────────────────────────────────────────

class PulseDot(QWidget):
    """Ponto que pulsa enquanto algo está em curso.

    É a tradução da animação ``@keyframes pulse`` do design: o CSS anima um
    ``box-shadow`` que se expande; aqui pintamos um halo com o mesmo ritmo.
    """

    def __init__(self, size: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dot = size
        self._phase = 0.0
        self.setFixedSize(size * 3, size * 3)
        self._anim = QPropertyAnimation(self, b"phase", self)
        self._anim.setDuration(theme.DURATION["pulse"])
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def get_phase(self) -> float:
        return self._phase

    def set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = Property(float, get_phase, set_phase)

    def start(self) -> None:
        if self._anim.state() != QPropertyAnimation.State.Running:
            self._anim.start()

    def stop(self) -> None:
        self._anim.stop()
        self._phase = 0.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        accent = theme.qcolor("accent")
        # halo: cresce e desaparece, como o box-shadow do design
        if self._anim.state() == QPropertyAnimation.State.Running:
            halo = QColorWithAlpha(accent, int(115 * (1.0 - self._phase)))
            p.setBrush(halo)
            p.setPen(Qt.PenStyle.NoPen)
            r = self._dot / 2 + self._phase * self._dot * 0.9
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.setBrush(accent)
        p.setPen(Qt.PenStyle.NoPen)
        r = self._dot / 2
        p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
        p.end()


# ── Grade que reflui ──────────────────────────────────────────────────────

class ResponsiveGrid(QWidget):
    """Cartões em colunas iguais, tantas quantas couberem.

    É o equivalente em Qt do ``repeat(auto-fit, minmax(min(100%, Npx), 1fr))``
    que o arquivo de design usa nas grades de cartões. Um ``QGridLayout`` com
    número fixo de colunas espreme os cartões até o texto ficar ilegível numa
    janela estreita; aqui as colunas são recalculadas a cada redimensionamento,
    e nunca passam do número de itens.
    """

    def __init__(self, min_item_width: int = 250, spacing: str = "6",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = max(1, int(min_item_width))
        self._items: list[QWidget] = []
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(theme.space(spacing))

    def set_items(self, widgets: list[QWidget]) -> None:
        """Troca o conteúdo da grade."""
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                # Antes do deleteLater: até o laço de eventos rodar, o widget
                # antigo continuaria desenhado por cima do novo.
                w.setParent(None)
                w.deleteLater()
        self._items = list(widgets)
        self._cols = 0
        self._relayout()

    def items(self) -> list[QWidget]:
        return list(self._items)

    def columns(self) -> int:
        """Quantas colunas a grade está usando agora."""
        return self._cols

    def _wanted_columns(self) -> int:
        if not self._items:
            return 0
        vao = self._grid.spacing()
        largura = max(self.width(), 1)
        # Quantos itens de largura mínima cabem, contando os vãos.
        n = max(1, (largura + vao) // (self._min + vao))
        return int(min(n, len(self._items)))

    def _relayout(self) -> None:
        cols = self._wanted_columns()
        if cols == self._cols:
            return
        self._cols = cols
        for w in self._items:
            self._grid.removeWidget(w)
        for c in range(self._grid.columnCount()):
            self._grid.setColumnStretch(c, 0)
        if not cols:
            return
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // cols, i % cols)
            w.show()
        for c in range(cols):
            self._grid.setColumnStretch(c, 1)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().resizeEvent(event)
        self._relayout()


def QColorWithAlpha(base, alpha: int):  # noqa: N802 - fábrica curta
    """Cópia de uma cor com outro alfa."""
    c = base.__class__(base)
    c.setAlpha(max(0, min(255, alpha)))
    return c
