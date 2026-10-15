"""Painel de erro do motor, no rodapé da área de trabalho.

O arquivo de design mostra a falha do SUPREM-III como uma faixa dentro da
própria tela — não como uma caixa de diálogo. Além de ser o desenho pedido, é
o que mantém a mensagem à vista enquanto o usuário corrige o deck, e o que
deixa a interface testável sem alguém para clicar “OK”.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from .. import theme
from .common import button, eyebrow, hline, label, row, stretch


class EngineErrorPanel(QWidget):
    """Explica a falha, oferece tentar de novo e mostra a mensagem original."""

    retry_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme.mark(self, surface="raised")
        self._raw = ""

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(hline(strong=True))

        corpo = QWidget()
        lay = QHBoxLayout(corpo)
        lay.setContentsMargins(theme.space("16"), theme.space("11"),
                               theme.space("16"), theme.space("12"))
        lay.setSpacing(theme.space("20"))

        esquerda = QVBoxLayout()
        esquerda.setSpacing(theme.space("5"))
        self._eyebrow = eyebrow("erro do motor · suprem-iii", accent=True)
        self._titulo = label("", "title")
        self._explicacao = label("", "dim", wrap=True)
        self._explicacao.setMaximumWidth(theme.dimension("detail-max-width"))
        esquerda.addWidget(self._eyebrow)
        esquerda.addWidget(self._titulo)
        esquerda.addWidget(self._explicacao)

        self._b_bruto = button("▸ Mostrar a mensagem original do motor", "link",
                               on_click=self._toggle_raw)
        esquerda.addWidget(row(self._b_bruto, stretch(), spacing="0"))

        self._bruto = QPlainTextEdit()
        self._bruto.setReadOnly(True)
        self._bruto.setFont(theme.font("mono", "small"))
        theme.mark(self._bruto, surface="code", role="mono")
        self._bruto.setFixedHeight(theme.space("24") * 2)
        self._bruto.hide()
        esquerda.addWidget(self._bruto)
        lay.addLayout(esquerda, 1)

        acoes = QVBoxLayout()
        acoes.setSpacing(theme.space("4"))
        acoes.addWidget(button("Tentar de novo", "primary",
                               on_click=self.retry_requested.emit))
        acoes.addWidget(button("Fechar", "small", on_click=self._close))
        acoes.addStretch(1)
        lay.addLayout(acoes, 0)

        raiz.addWidget(corpo)
        self.hide()

    # ── conteúdo ──────────────────────────────────────────────────────────

    def show_error(self, title: str, explanation: str, raw: str,
                   engine: str = "SUPREM-III", *, can_retry: bool = True) -> None:
        """Mostra uma falha do motor."""
        self._eyebrow.setText(f"ERRO DO MOTOR · {engine}".upper())
        self._titulo.setText(title)
        self._explicacao.setText(explanation)
        self._raw = raw.strip()
        self._bruto.setPlainText(self._raw)
        self._bruto.hide()
        self._b_bruto.setText("▸ Mostrar a mensagem original do motor")
        self._b_bruto.setVisible(bool(self._raw))
        self.show()

    @property
    def raw(self) -> str:
        return self._raw

    def _toggle_raw(self) -> None:
        visivel = not self._bruto.isVisible()
        self._bruto.setVisible(visivel)
        self._b_bruto.setText(
            ("▾ Ocultar" if visivel else "▸ Mostrar")
            + " a mensagem original do motor")

    def _close(self) -> None:
        self.hide()
        self.dismissed.emit()
