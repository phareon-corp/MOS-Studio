"""Área ainda não migrada, com o recado honesto do que falta.

As telas de Dispositivo (MINIMOS) e de Oxidação (Deal-Grove) existem na
navegação porque são do arquivo de design, mas o conteúdo é das etapas
seguintes da migração. O núcleo delas já está extraído e testado
(:mod:`mos_studio.core.minimos` e :mod:`mos_studio.core.oxidation`); o que
falta é a interface.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import theme
from ..widgets.common import eyebrow, label


class PlaceholderScreen(QWidget):
    """Tela de espera de uma área ainda não migrada."""

    def __init__(self, numero: str, titulo: str, descricao: str,
                 nucleo: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.space("24"), theme.space("24"),
                               theme.space("24"), theme.space("24"))
        lay.setSpacing(theme.space("6"))
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        caixa = QWidget()
        cl = QVBoxLayout(caixa)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.space("6"))
        cl.addWidget(eyebrow(f"{numero} · próxima etapa da migração", accent=True))
        cl.addWidget(label(titulo, "display"))
        desc = label(descricao, "dim", wrap=True)
        desc.setMaximumWidth(theme.dimension("detail-max-width"))
        cl.addWidget(desc)
        if nucleo:
            nota = label(nucleo, "hint", wrap=True)
            nota.setMaximumWidth(theme.dimension("detail-max-width"))
            cl.addWidget(nota)
        caixa.setMaximumWidth(theme.dimension("detail-max-width"))
        lay.addWidget(caixa, 0, Qt.AlignmentFlag.AlignCenter)


def device_screen() -> PlaceholderScreen:
    """Tela de Dispositivo (MINIMOS)."""
    return PlaceholderScreen(
        "03", "Dispositivo",
        "A ponte SUPREM-III → MINIMOS leva o perfil de dopagem calculado para "
        "o deck do simulador de dispositivo e devolve a curva I-V.",
        "O motor do MINIMOS já está migrado e coberto por testes "
        "(mos_studio/core/minimos.py): execução com o mecanismo duplo "
        "fort.NN + FORTnn, geração de deck e leitura de .iv e PIF. "
        "Falta a interface.")


def oxidation_screen() -> PlaceholderScreen:
    """Tela de Oxidação (Deal-Grove)."""
    return PlaceholderScreen(
        "04", "Oxidação",
        "A análise varre tempos de oxidação no SUPREM-III e ajusta "
        "Deal-Grove: t/Xo = (1/B)·Xo + A/B.",
        "O ajuste já está migrado e coberto por testes "
        "(mos_studio/core/oxidation.py), junto com a execução síncrona do "
        "motor e a leitura da espessura de óxido. Falta a interface.")
