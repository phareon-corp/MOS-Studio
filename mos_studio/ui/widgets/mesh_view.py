"""Pré-visualização da malha 2-D, pintada com QPainter.

Mostra as linhas que o motor vai criar — não as que o usuário pediu. A
diferença é o ponto: cada cartão ``line`` fixa um espaçamento *local*, e entre
dois cartões o motor subdivide por progressão geométrica
(:func:`mos_studio.core.mesh.divide`). Desenhar o que o usuário digitou daria
uma grade regular que o motor nunca gera.

As linhas pedidas aparecem em destaque sobre as geradas, para ficar visível
onde está o refino e onde ele se perdeu.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core import mesh as mesh_mod
from .. import theme

#: Acima disto a grade é desenhada rala: mais que isso não se distingue na
#: tela e o desenho fica lento sem ganho nenhum.
MAX_DRAWN_LINES = 220

#: Margem interna do desenho, em pixels, para os rótulos dos eixos caberem.
MARGIN_LEFT = 46
MARGIN_TOP = 14
MARGIN_RIGHT = 14
MARGIN_BOTTOM = 30


def _decimate(valores: list[float], limite: int) -> list[float]:
    """Mantém as pontas e afina o meio, para a grade não virar borrão."""
    if len(valores) <= limite:
        return valores
    passo = len(valores) / float(limite)
    saida = [valores[int(i * passo)] for i in range(limite)]
    if saida[-1] != valores[-1]:
        saida.append(valores[-1])
    return saida


class MeshView(QWidget):
    """A malha desenhada. Sem malha válida, mostra o motivo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mesh = mesh_mod.Mesh()
        self._stats = mesh_mod.MeshStats()
        self._show_triangles = True
        self.setMinimumHeight(theme.space("24") * 7)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    # ── dados ─────────────────────────────────────────────────────────────

    def set_mesh(self, mesh: mesh_mod.Mesh) -> None:
        self._mesh = mesh
        self._stats = mesh_mod.stats(mesh)
        self.update()

    def stats(self) -> mesh_mod.MeshStats:
        return self._stats

    def set_show_triangles(self, show: bool) -> None:
        self._show_triangles = show
        self.update()

    # ── desenho ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("code-bg"))

        area = QRectF(MARGIN_LEFT, MARGIN_TOP,
                      max(1.0, self.width() - MARGIN_LEFT - MARGIN_RIGHT),
                      max(1.0, self.height() - MARGIN_TOP - MARGIN_BOTTOM))

        if not self._stats.ok:
            p.setPen(theme.qcolor("ink-dim"))
            p.setFont(theme.font("sans", "small"))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter,
                       self._stats.error or "Defina a malha para ver a "
                                            "pré-visualização.")
            p.end()
            return

        xs, ys = self._stats.x_positions, self._stats.y_positions
        x0, x1 = xs[0], xs[-1]
        y0, y1 = ys[0], ys[-1]
        larg = (x1 - x0) or 1.0
        alt = (y1 - y0) or 1.0

        def px(v: float) -> float:
            return area.left() + (v - x0) / larg * area.width()

        def py(v: float) -> float:
            # y cresce para dentro da lâmina, então cresce para baixo na tela.
            return area.top() + (v - y0) / alt * area.height()

        p.fillRect(area, theme.qcolor("bg"))

        dx = _decimate(xs, MAX_DRAWN_LINES)
        dy = _decimate(ys, MAX_DRAWN_LINES)

        if self._show_triangles:
            # A diagonal de cada célula, que é o que torna a malha
            # triangular visível sem desenhar os 816 triângulos um a um.
            caminho = QPainterPath()
            for a, b in zip(dx, dx[1:]):
                for c, d in zip(dy, dy[1:]):
                    caminho.moveTo(px(a), py(d))
                    caminho.lineTo(px(b), py(c))
            p.setPen(QPen(theme.qcolor("line"), 0.5))
            p.drawPath(caminho)

        grade = QPainterPath()
        for v in dx:
            grade.moveTo(px(v), area.top())
            grade.lineTo(px(v), area.bottom())
        for v in dy:
            grade.moveTo(area.left(), py(v))
            grade.lineTo(area.right(), py(v))
        p.setPen(QPen(theme.qcolor("line-strong"), 0.6))
        p.drawPath(grade)

        # As linhas que o usuário pediu, por cima.
        pedidas = QPainterPath()
        for ln in self._mesh.x:
            pedidas.moveTo(px(ln.loc), area.top())
            pedidas.lineTo(px(ln.loc), area.bottom())
        for ln in self._mesh.y:
            pedidas.moveTo(area.left(), py(ln.loc))
            pedidas.lineTo(area.right(), py(ln.loc))
        p.setPen(QPen(theme.qcolor("accent"), 1.2))
        p.drawPath(pedidas)

        p.setPen(QPen(theme.qcolor("ink-dim"), 1.0))
        p.drawRect(area)

        # ── rótulos dos eixos ──
        p.setFont(theme.font("mono", "tiny"))
        p.setPen(theme.qcolor("ink-dim"))
        for ln in self._mesh.x:
            p.drawText(QRectF(px(ln.loc) - 24, area.bottom() + 4, 48, 14),
                       Qt.AlignmentFlag.AlignCenter, f"{ln.loc:g}")
        for ln in self._mesh.y:
            p.drawText(QRectF(2, py(ln.loc) - 7, MARGIN_LEFT - 6, 14),
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter, f"{ln.loc:g}")
        p.drawText(QRectF(area.left(), area.bottom() + 15, area.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, "x lateral (µm)")

        # A superfície exposta, que é por onde o processo entra.
        p.setPen(QPen(theme.qcolor("accent"), 2.0))
        p.drawLine(QPointF(area.left(), py(y0)), QPointF(area.right(), py(y0)))
        p.setFont(theme.font("mono", "tiny"))
        p.setPen(theme.qcolor("accent-ink"))
        p.drawText(QRectF(area.left() + 6, area.top() + 2, 240, 14),
                   Qt.AlignmentFlag.AlignLeft, "superfície exposta")
        p.end()
