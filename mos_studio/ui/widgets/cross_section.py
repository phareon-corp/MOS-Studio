"""A seção transversal do dispositivo, pintada com QPainter.

Esta compilação do SUPREM-IV.GS **não tem camada gráfica**: os ``gpsup/
gpfake.c`` são talões vazios, e ``plot.2d``/``contour`` não produzem desenho
nenhum. Então o desenho não vem do motor — vem dos números dele. A seção é
varrida com N cortes verticais ``print.1d x.value=…`` e tudo aqui sai daí
(:mod:`mos_studio.core.field2d`): as faixas de material, as linhas de nível,
a junção e a superfície.

Isso tem uma consequência boa: o que aparece na tela é a geometria que o motor
construiu — o bico de pássaro da oxidação, o degrau do espaçador, o poli
recortado pela corrosão — e não uma forma desenhada por conta própria.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core import field2d
from .. import theme

#: Cor de fundo de cada material, nos tokens do tema.
#:
#: A pilha 1-D (:mod:`layer_stack`) pinta óxido, nitreto e poli com o mesmo
#: tom, porque lá os rótulos ficam ao lado de cada faixa. Aqui não cabe
#: rótulo dentro de uma camada de 25 nm, e uma porta de poli sobre óxido de
#: porta viraria um bloco só — então cada material tem o seu tom, e a tela
#: põe a legenda ao lado.
FILLS = {
    "silicon": "bg-3",
    "gaas": "bg-3",
    "oxide": "bg-4",
    "oxynitride": "bg-4",
    "nitride": "bg-2",
    "poly": "al",
    "aluminum": "chrome",
    "photoresist": "amber",
}

#: Nome de cada material em português, para a legenda.
LABELS = {
    "silicon": "Silício", "oxide": "Óxido", "nitride": "Nitreto",
    "poly": "Polissilício", "oxynitride": "Oxinitreto",
    "aluminum": "Alumínio", "photoresist": "Fotorresiste", "gaas": "GaAs",
    "gas": "Ambiente",
}

MARGIN_LEFT = 48
MARGIN_TOP = 16
MARGIN_RIGHT = 16
MARGIN_BOTTOM = 30

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def level_label(valor: float) -> str:
    """``1e+18`` como ``10¹⁸``, que é como perfis de dopagem se leem."""
    if valor <= 0:
        return "0"
    expo = int(round(math.log10(valor)))
    return "10" + str(expo).translate(_SUPERSCRIPT)


class CrossSection(QWidget):
    """A seção transversal, com contornos, junção e o cursor de corte.

    Clicar ou arrastar move o corte e emite :attr:`cut_changed`, que é o que
    liga o desenho ao gráfico 1-D ao lado.
    """

    cut_changed = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._field = field2d.Field2D()
        self._levels: list[float] = []
        self._cut = 0.0
        self._show_junction = True
        self._depth_limit = 0.0        # 0 = ajuste automático
        self._empty = "Rode o processo para ver a seção transversal."
        self.setMinimumHeight(theme.space("24") * 7)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ── dados ─────────────────────────────────────────────────────────────

    def set_field(self, fld: field2d.Field2D) -> None:
        self._field = fld
        if fld.ok:
            x0, x1, _, _ = fld.extent()
            self._cut = min(max(self._cut, x0), x1)
        self.update()

    def set_levels(self, levels: list[float]) -> None:
        self._levels = sorted(levels)
        self.update()

    def set_cut(self, x: float) -> None:
        if self._field.ok:
            x0, x1, _, _ = self._field.extent()
            x = min(max(x, x0), x1)
        if abs(x - self._cut) < 1e-9:
            return
        self._cut = x
        self.update()

    def cut(self) -> float:
        return self._cut

    def set_depth_limit(self, depth: float) -> None:
        """Profundidade máxima desenhada, em µm. ``0`` volta ao automático."""
        self._depth_limit = max(0.0, depth)
        self.update()

    def depth_limit(self) -> float:
        return self._depth_limit

    def visible_depth(self) -> float:
        """Profundidade que o desenho realmente mostra.

        No automático, o corte fica logo abaixo da junção mais funda. Sem
        isso, o substrato de 2 µm toma nove décimos da altura e o dispositivo
        inteiro — porta, extensão, fonte/dreno — some numa faixa de poucos
        pixels no topo.
        """
        _, _, y0, y1 = self._field.extent()
        if self._depth_limit > 0:
            return min(max(self._depth_limit, y0 + 0.05), y1)
        fundo = 0.0
        for c in self._field.columns:
            xj = field2d.junction_depth_at(self._field, c.x)
            sup = c.surface()
            if xj is not None and sup is not None:
                fundo = max(fundo, sup + xj)
        if fundo <= 0:
            # Sem junção — é o caso de um perfil químico, que não troca de
            # sinal. Serve de fundo a profundidade em que o valor já caiu
            # quatro décadas abaixo do pico: abaixo disso é substrato.
            fundo = self._decay_depth()
        if fundo <= 0:
            return y1
        return min(y1, max(fundo * 2.5, y0 + 0.3))

    def _decay_depth(self) -> float:
        """Profundidade em que o campo cai a 10⁻⁴ do seu pico."""
        _, alto = self._field.value_range()
        if alto <= 0:
            return 0.0
        alvo = alto * 1e-4
        fundo = 0.0
        for c in self._field.columns:
            for d, v in zip(c.depth, c.value):
                if abs(v) >= alvo:
                    fundo = max(fundo, d)
        return fundo

    def set_show_junction(self, show: bool) -> None:
        self._show_junction = show
        self.update()

    def set_empty_message(self, text: str) -> None:
        self._empty = text
        self.update()

    def materials(self) -> list[str]:
        """Materiais presentes, para a legenda da tela."""
        return sorted(field2d.material_bands(self._field))

    # ── interação ─────────────────────────────────────────────────────────

    def _area(self) -> QRectF:
        return QRectF(MARGIN_LEFT, MARGIN_TOP,
                      max(1.0, self.width() - MARGIN_LEFT - MARGIN_RIGHT),
                      max(1.0, self.height() - MARGIN_TOP - MARGIN_BOTTOM))

    def _x_from_pixel(self, px: float) -> float:
        area = self._area()
        x0, x1, _, _ = self._field.extent()
        t = (px - area.left()) / max(1.0, area.width())
        return x0 + min(max(t, 0.0), 1.0) * (x1 - x0)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._field.ok and event.button() == Qt.MouseButton.LeftButton:
            self.set_cut(self._x_from_pixel(event.position().x()))
            self.cut_changed.emit(self._cut)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._field.ok and event.buttons() & Qt.MouseButton.LeftButton:
            self.set_cut(self._x_from_pixel(event.position().x()))
            self.cut_changed.emit(self._cut)

    # ── desenho ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("code-bg"))
        area = self._area()

        if not self._field.ok:
            p.setPen(theme.qcolor("ink-dim"))
            p.setFont(theme.font("sans", "small"))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, self._empty)
            p.end()
            return

        x0, x1, y0, _ = self._field.extent()
        y1 = self.visible_depth()
        larg = (x1 - x0) or 1.0
        alt = (y1 - y0) or 1.0

        def px(v: float) -> float:
            return area.left() + (v - x0) / larg * area.width()

        def py(v: float) -> float:
            return area.top() + (v - y0) / alt * area.height()

        p.setClipRect(area)

        # ── faixas de material ──
        faixas = field2d.material_bands(self._field)
        xs = self._field.xs
        meia = (larg / max(1, len(xs) - 1)) / 2 if len(xs) > 1 else larg / 2
        for material, lista in faixas.items():
            if material == "gas":
                continue
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor(FILLS.get(material, "bg-3")))
            for x, topo, base in lista:
                esq = px(max(x - meia, x0))
                dir_ = px(min(x + meia, x1))
                p.drawRect(QRectF(esq, py(topo), max(1.0, dir_ - esq),
                                  max(1.0, py(base) - py(topo))))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── contornos de concentração ──
        p.setPen(QPen(theme.qcolor("ink-dim"), 1.0))
        for nivel in self._levels:
            caminho = QPainterPath()
            for linha in field2d.contour(self._field, nivel):
                for i, (x, y) in enumerate(linha):
                    ponto = QPointF(px(x), py(y))
                    caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)
            p.drawPath(caminho)

        # ── junção ──
        if self._show_junction:
            caminho = QPainterPath()
            for linha in field2d.junction(self._field):
                for i, (x, y) in enumerate(linha):
                    ponto = QPointF(px(x), py(y))
                    caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)
            pen = QPen(theme.qcolor("accent"), 1.8)
            pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawPath(caminho)

        # ── superfície do silício ──
        sup = field2d.surface_line(self._field)
        if sup:
            caminho = QPainterPath()
            for i, (x, y) in enumerate(sup):
                ponto = QPointF(px(x), py(y))
                caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)
            p.setPen(QPen(theme.qcolor("ink"), 1.4))
            p.drawPath(caminho)

        p.setClipping(False)
        p.setPen(QPen(theme.qcolor("line-strong"), 1.0))
        p.drawRect(area)

        # ── cursor de corte ──
        cx = px(self._cut)
        pen = QPen(theme.qcolor("accent-ink"), 1.2)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(cx, area.top()), QPointF(cx, area.bottom()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("accent"))
        p.drawEllipse(QPointF(cx, area.top() + 6), 5.0, 5.0)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── eixos ──
        p.setFont(theme.font("mono", "tiny"))
        p.setPen(theme.qcolor("ink-dim"))
        for i in range(5):
            v = x0 + (x1 - x0) * i / 4
            p.drawText(QRectF(px(v) - 26, area.bottom() + 4, 52, 14),
                       Qt.AlignmentFlag.AlignCenter, f"{v:.2f}".rstrip("0")
                       .rstrip(".").replace(".", ","))
        for i in range(4):
            v = y0 + (y1 - y0) * i / 3
            p.drawText(QRectF(2, py(v) - 7, MARGIN_LEFT - 6, 14),
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter,
                       f"{v:.2f}".replace(".", ","))
        p.drawText(QRectF(area.left(), area.bottom() + 15, area.width(), 14),
                   Qt.AlignmentFlag.AlignCenter, "x lateral (µm)")
        p.end()
