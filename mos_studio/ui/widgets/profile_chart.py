"""Gráfico do perfil de dopagem: profundidade × concentração, eixo Y logarítmico.

Pintado com QPainter a partir dos tokens do tema — sem matplotlib. O desenho
segue o arquivo de design: grade fina, rótulos em monospace com expoentes
sobrescritos, curva do perfil em destaque e a linha tracejada da junção.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")

#: Quantas décadas o eixo logarítmico mostra, no máximo. Oito cobrem de um
#: pico de 10²⁰ cm⁻³ até 10¹² — abaixo disso um perfil de dopagem não diz mais
#: nada, e o que há é zero numérico do motor.
MAX_DECADES = 8


def nice_step(span: float, alvo: int = 5) -> float:
    """Passo de grade legível (1, 2 ou 5 × 10ⁿ) para cobrir ``span``.

    Sem isso o eixo ganha marcas como 0,29 e 0,39, que parecem defeito.
    """
    if span <= 0:
        return 1.0
    bruto = span / max(1, alvo)
    potencia = 10.0 ** math.floor(math.log10(bruto))
    for mult in (1.0, 2.0, 5.0, 10.0):
        if bruto <= mult * potencia:
            return mult * potencia
    return 10.0 * potencia


@dataclass
class Series:
    """Uma curva do gráfico."""

    label: str
    points: list[tuple[float, float]]
    color: str = "ink"          # chave de token
    dashed: bool = False
    width: float = 2.0
    sublabel: str = ""


@dataclass
class ChartData:
    """Tudo que o gráfico precisa desenhar."""

    series: list[Series] = field(default_factory=list)
    junctions: list[float] = field(default_factory=list)
    x_label: str = "profundidade (µm)"
    y_label: str = "concentração (cm⁻³)"


class ProfileChart(QWidget):
    """O gráfico do perfil. Sem dados, mostra o estado vazio."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = ChartData()
        self._colors: dict[str, str] = {}
        self._compact = False
        self._empty = "Rode a receita para ver o perfil de dopagem."
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(theme.space("24") * 6)

    def set_data(self, data: ChartData) -> None:
        self._data = data
        self.update()

    def set_empty_message(self, text: str) -> None:
        self._empty = text
        self.update()

    def set_color_map(self, mapping: dict[str, str]) -> None:
        """Troca tokens de cor (ex.: desenhar sobre o herói escuro)."""
        self._colors = dict(mapping)
        self.update()

    def set_compact(self, compact: bool) -> None:
        """Modo reduzido: sem títulos de eixo, margens menores."""
        self._compact = compact
        self.update()

    def _c(self, token: str):
        """Cor de um token, respeitando o mapa em vigor."""
        return theme.qcolor(self._colors.get(token, token))

    def clear(self) -> None:
        self._data = ChartData()
        self.update()

    @property
    def has_data(self) -> bool:
        return any(s.points for s in self._data.series)

    # ── escala ────────────────────────────────────────────────────────────

    def _bounds(self) -> tuple[float, float, float]:
        """``(x_max, log_min, log_max)`` arredondados para décadas inteiras.

        O piso do eixo é limitado a :data:`MAX_DECADES` abaixo do pico. Sem
        isso, um perfil por espécie — em que o dopante cai a valores como
        10⁻²⁸ cm⁻³ longe da superfície, que é zero numérico — abria quarenta e
        oito décadas e espremia toda a parte útil da curva numa faixa de
        poucos pixels no topo.
        """
        xs = [x for s in self._data.series for x, _ in s.points]
        ys = [abs(y) for s in self._data.series for _, y in s.points if y]
        x_max = max(xs) if xs else 1.0
        if not ys:
            return x_max or 1.0, 14.0, 20.0
        hi = math.ceil(math.log10(max(ys)))
        lo = math.floor(math.log10(max(min(ys), 1e-30)))
        lo = max(lo, hi - MAX_DECADES)
        if hi - lo < 2:
            hi = lo + 2
        return (x_max or 1.0), float(lo), float(hi)

    # ── pintura ───────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self._c("bg"))

        if not self.has_data:
            p.setPen(self._c("ink-dim"))
            p.setFont(theme.font("sans", "base"))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._empty)
            p.end()
            return

        esq = theme.space("24") + theme.space("8")
        dir_ = theme.space("12")
        topo = theme.space("8")
        base = theme.space("20") + theme.space("6")
        plot = QRectF(esq, topo, max(1, self.width() - esq - dir_),
                      max(1, self.height() - topo - base))

        x_max, lo, hi = self._bounds()

        def px(x: float) -> float:
            return plot.left() + (x / x_max) * plot.width()

        def py(c: float) -> float:
            v = math.log10(max(abs(c), 10.0 ** lo))
            return plot.bottom() - ((v - lo) / (hi - lo)) * plot.height()

        # grade e eixos
        p.setFont(theme.font("mono", "micro"))
        p.setPen(QPen(self._c("line"), theme.dimension("border")))
        decadas = [lo + i for i in range(int(hi - lo) + 1)]
        for d in decadas:
            y = py(10.0 ** d)
            p.setPen(QPen(self._c("line"), theme.dimension("border")))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(self._c("ink-dim"))
            p.drawText(QRect(0, int(y - theme.space("5")), int(esq - theme.space("5")),
                             theme.space("10")),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       "10" + str(int(d)).translate(_SUPERSCRIPT))

        passo = nice_step(x_max)
        casas = max(0, -int(math.floor(math.log10(passo))))
        x = 0.0
        while x <= x_max + passo * 1e-6:
            p.setPen(QPen(self._c("line"), theme.dimension("border")))
            p.drawLine(QPointF(px(x), plot.top()), QPointF(px(x), plot.bottom()))
            p.setPen(self._c("ink-dim"))
            p.drawText(QRect(int(px(x) - theme.space("12")),
                             int(plot.bottom() + theme.space("3")),
                             theme.space("12") * 2, theme.space("9")),
                       int(Qt.AlignmentFlag.AlignCenter),
                       f"{x:.{casas}f}".replace(".", ","))
            x += passo

        p.setPen(QPen(self._c("line-strong"), theme.dimension("border")))
        p.drawLine(QPointF(plot.left(), plot.top()), QPointF(plot.left(), plot.bottom()))
        p.drawLine(QPointF(plot.left(), plot.bottom()),
                   QPointF(plot.right(), plot.bottom()))

        # junções
        for xj in self._data.junctions:
            if xj <= x_max:
                pen = QPen(self._c("ink-dim"), theme.dimension("border"))
                pen.setDashPattern([2, 4])
                p.setPen(pen)
                p.drawLine(QPointF(px(xj), plot.top()), QPointF(px(xj), plot.bottom()))
                p.setPen(self._c("ink"))
                p.setFont(theme.font("mono", "micro"))
                p.drawText(QPointF(px(xj) + theme.space("3"),
                                   plot.top() + theme.space("9")),
                           f"xj = {xj:.3f} µm".replace(".", ","))

        # curvas
        for s in self._data.series:
            if len(s.points) < 2:
                continue
            caminho = QPainterPath()
            for i, (x, c) in enumerate(s.points):
                ponto = QPointF(px(x), py(c))
                caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)
            pen = QPen(theme.qcolor(s.color), s.width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            if s.dashed:
                pen.setDashPattern([5, 5])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(caminho)

        # títulos dos eixos
        p.setPen(self._c("ink-dim"))
        p.setFont(theme.font("sans", "tiny"))
        p.drawText(QRect(int(plot.left()), self.height() - theme.space("10"),
                         int(plot.width()), theme.space("9")),
                   int(Qt.AlignmentFlag.AlignCenter), self._data.x_label)
        p.save()
        p.translate(theme.space("4"), plot.center().y())
        p.rotate(-90)
        p.drawText(QRect(-theme.space("24") * 3, 0, theme.space("24") * 6,
                         theme.space("9")),
                   int(Qt.AlignmentFlag.AlignCenter), self._data.y_label)
        p.restore()
        p.end()


class ChartLegend(QWidget):
    """Legenda do gráfico, montada a partir das mesmas séries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[Series] = []
        self._colors: dict[str, str] = {}
        self.setFixedHeight(theme.space("10"))

    def set_series(self, series: list[Series]) -> None:
        self._series = [s for s in series if s.points]
        self.update()

    def set_color_map(self, mapping: dict[str, str]) -> None:
        self._colors = dict(mapping)
        self.update()

    def _c(self, token: str):
        return theme.qcolor(self._colors.get(token, token))

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = 0
        p.setFont(theme.font("sans", "small"))
        for s in self._series:
            pen = QPen(theme.qcolor(s.color), 2)
            if s.dashed:
                pen.setDashPattern([3, 3])
            p.setPen(pen)
            meio = self.height() / 2
            p.drawLine(QPointF(x, meio), QPointF(x + theme.space("9"), meio))
            x += theme.space("9") + theme.space("4")
            p.setPen(self._c("ink"))
            largura = p.fontMetrics().horizontalAdvance(s.label)
            p.drawText(QRect(int(x), 0, largura + theme.space("2"), self.height()),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                       s.label)
            x += largura + theme.space("5")
            if s.sublabel:
                p.setPen(self._c("ink-dim"))
                sub_w = p.fontMetrics().horizontalAdvance(s.sublabel)
                p.drawText(QRect(int(x), 0, sub_w + theme.space("2"), self.height()),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                           s.sublabel)
                x += sub_w + theme.space("5")
            x += theme.space("8")
        p.end()
