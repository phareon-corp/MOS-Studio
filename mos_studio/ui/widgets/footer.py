"""Rodapé: estado dos dois motores e onde ficam projetos e preferências."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget

from .. import theme
from .common import label


class StatusDot(QWidget):
    """Ponto de estado (verde-ish = pronto; acento = com problema)."""

    def __init__(self, ok: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ok = ok
        self.setFixedSize(theme.space("3"), theme.space("3"))

    def set_ok(self, ok: bool) -> None:
        self._ok = ok
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(theme.qcolor("ink-dim" if self._ok else "accent"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self.rect())
        p.end()


class Footer(QWidget):
    """A faixa de 28px do pé da janela."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme.mark(self, surface="chrome")
        self.setFixedHeight(theme.dimension("footer-height"))
        self.setAutoFillBackground(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.space("10"), 0, theme.space("10"), 0)
        lay.setSpacing(theme.space("9"))

        self._dot_sup = StatusDot()
        self._txt_sup = label("", "eyebrow")
        self._dot_mm = StatusDot()
        self._txt_mm = label("", "eyebrow")
        self._direita = label("", "eyebrow")

        for dot, txt in ((self._dot_sup, self._txt_sup), (self._dot_mm, self._txt_mm)):
            lay.addWidget(dot)
            lay.addWidget(txt)
        lay.addStretch(1)
        lay.addWidget(self._direita)

    def set_engines(self, suprem_problems: list[str],
                    minimos_problems: list[str],
                    suprem4_problems: list[str] | None = None) -> None:
        """Atualiza o estado dos motores a partir das listas de problemas.

        Os dois motores de processo aparecem juntos quando ambos estão
        prontos; com problema, o nome do que falhou vem junto da mensagem,
        para não ficar dúvida sobre qual é.
        """
        s4 = list(suprem4_problems or [])
        self._dot_sup.set_ok(not suprem_problems and not s4)
        if suprem_problems:
            texto = "SUPREM-III · " + suprem_problems[0]
        elif s4:
            texto = "SUPREM-IV · " + s4[0]
        else:
            texto = "SUPREM-III e SUPREM-IV prontos"
        self._txt_sup.setText(texto.upper())
        self._dot_mm.set_ok(not minimos_problems)
        self._txt_mm.setText(
            ("MINIMOS pronto" if not minimos_problems
             else "MINIMOS · " + minimos_problems[0]).upper())

    def set_right(self, text: str) -> None:
        """Texto da direita. Não maiusculiza: costuma conter caminho de arquivo."""
        self._direita.setText(text)
