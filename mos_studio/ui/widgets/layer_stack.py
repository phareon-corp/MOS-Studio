"""Pilha de camadas: a lâmina vista de lado, na vertical.

Representação 1-D — as camadas empilhadas ao longo da profundidade. A largura
não tem significado físico, e a legenda diz isso.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...core.recipe import MATERIAL_LABELS
from .. import theme

#: Token de cor de cada material.
FILLS = {"ALUMINUM": "al", "OXIDE": "bg-4", "NITRIDE": "bg-4",
         "POLYSILI": "bg-4", "SILICON": "bg-3"}


class LayerStack(QWidget):
    """Desenha as camadas e, quando há junção, a região de tipo n."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layers: list[tuple[str, float]] = []
        self._junction: float | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(theme.space("24") * 6)

    def set_layers(self, camadas: list[tuple[str, float]],
                   junction: float | None = None) -> None:
        self._layers = list(camadas)
        self._junction = junction
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("bg"))
        if not self._layers:
            p.setPen(theme.qcolor("ink-dim"))
            p.setFont(theme.font("sans", "base"))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                       "Adicione uma etapa PRINT com a tabela “Camadas”.")
            p.end()
            return

        margem = theme.space("12")
        largura = theme.space("24") * 4
        total = sum(e for _m, e in self._layers) or 1.0
        altura = self.height() - margem * 2
        x = margem
        y = float(margem)

        p.setFont(theme.font("sans", "base"))
        profundidade = 0.0
        for material, espessura in self._layers:
            h = max(theme.space("12"), espessura / total * altura)
            caixa = QRect(x, int(y), largura, int(h))
            p.fillRect(caixa, theme.qcolor(FILLS.get(material, "bg-3")))
            p.setPen(QPen(theme.qcolor("line-strong"), theme.dimension("border")))
            p.drawRect(caixa)

            # região tipo n dentro do silício, quando houver junção
            if (material == "SILICON" and self._junction
                    and self._junction < espessura):
                parte = int(h * (self._junction / espessura))
                p.fillRect(QRect(x, int(y), largura, parte),
                           theme.qcolor("nfill"))
                p.setPen(QPen(theme.qcolor("ink-dim"), theme.dimension("border")))
                p.drawLine(x, int(y) + parte, x + largura, int(y) + parte)

            texto_x = x + largura + theme.space("8")
            p.setPen(theme.qcolor("ink"))
            p.setFont(theme.font("sans", "base", "medium"))
            p.drawText(texto_x, int(y) + theme.space("9"),
                       MATERIAL_LABELS.get(material, material.capitalize()))
            p.setPen(theme.qcolor("ink-dim"))
            p.setFont(theme.font("mono", "small"))
            faixa = (f"{profundidade:.4f} – {profundidade + espessura:.4f} µm"
                     .replace(".", ","))
            p.drawText(texto_x, int(y) + theme.space("16"), faixa)
            profundidade += espessura
            y += h

        p.setPen(theme.qcolor("ink-dim"))
        p.setFont(theme.font("sans", "small"))
        p.drawText(QRect(margem, int(y) + theme.space("6"),
                         self.width() - margem * 2, theme.space("16")),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                   "Representação 1-D: camadas empilhadas ao longo da "
                   "profundidade. A largura não tem significado físico.")
        p.end()
