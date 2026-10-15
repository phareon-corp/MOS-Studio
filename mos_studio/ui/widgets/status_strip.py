"""Faixa de estado da execução, acima do rodapé.

Mostra o motor, a etapa em curso, o tempo decorrido e a ação cabível:
cancelar enquanto roda, ver o resultado quando termina, fechar depois.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget

from ..run_controller import format_elapsed
from .. import theme
from .common import PulseDot, button, eyebrow, label


class StatusStrip(QWidget):
    """A faixa. Fica escondida quando não há execução para relatar."""

    cancel_requested = Signal()
    result_requested = Signal()
    dismiss_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme.mark(self, surface="raised")
        self.setFixedHeight(theme.dimension("strip-height"))
        self._progress = 0.0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.space("10"), 0, theme.space("10"), 0)
        lay.setSpacing(theme.space("7"))

        self._dot = PulseDot()
        self._engine = eyebrow("suprem-iii")
        self._text = label("", "base")
        self._time = label("", "mono")
        self._b_cancel = button("Cancelar", "small",
                                on_click=self.cancel_requested.emit)
        self._b_result = button("Ver resultado", "small",
                                on_click=self.result_requested.emit)
        self._b_close = button("×", "small", tooltip="Fechar",
                               on_click=self.dismiss_requested.emit)

        lay.addWidget(self._dot)
        lay.addWidget(self._engine)
        lay.addWidget(self._text)
        lay.addStretch(1)
        lay.addWidget(self._time)
        lay.addWidget(self._b_cancel)
        lay.addWidget(self._b_result)
        lay.addWidget(self._b_close)
        self.hide()

    # ── estados ───────────────────────────────────────────────────────────

    def set_engine(self, name: str) -> None:
        """Nome do motor que esta execução usou.

        Era fixo em SUPREM-III; com os dois motores, uma execução 2-D
        concluída ficava assinada pelo motor errado.
        """
        self._engine.setText(name.upper())

    def show_running(self, text: str, elapsed: float, progress: float) -> None:
        self._dot.show()
        self._dot.start()
        self._text.setText(text)
        self._time.setText(format_elapsed(elapsed))
        self._progress = max(0.0, min(1.0, progress))
        self._b_cancel.show()
        self._b_result.hide()
        self._b_close.hide()
        self.show()
        self.update()

    def show_done(self, text: str, elapsed: float, *,
                  offer_result: bool = True) -> None:
        self._dot.stop()
        self._dot.hide()
        self._text.setText(text)
        self._time.setText("em " + format_elapsed(elapsed))
        self._progress = 1.0
        self._b_cancel.hide()
        self._b_result.setVisible(offer_result)
        self._b_close.show()
        self.show()
        self.update()

    def show_stopped(self, text: str, elapsed: float) -> None:
        self._dot.stop()
        self._dot.hide()
        self._text.setText(text)
        self._time.setText("em " + format_elapsed(elapsed))
        self._progress = 0.0
        self._b_cancel.hide()
        self._b_result.hide()
        self._b_close.show()
        self.show()
        self.update()

    def dismiss(self) -> None:
        self._dot.stop()
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qcolor("bg-2"))
        p.fillRect(0, 0, self.width(), theme.dimension("border"),
                   theme.qcolor("line-strong"))
        if self._progress > 0:
            p.fillRect(0, 0, int(self.width() * self._progress), 2,
                       theme.qcolor("accent"))
        p.end()
