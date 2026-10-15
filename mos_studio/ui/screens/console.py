"""Tela de Console: conversar com o shell do SUPREM-IV.

O motor é um shell de verdade: lê cartões da entrada padrão e guarda estado
entre eles. Esta tela mantém **um** processo vivo
(:class:`mos_studio.core.shell4.Shell4`), de modo que montar a malha, rodar
uma difusão e pedir um ``print.1d`` sejam três comandos de uma mesma sessão,
como no terminal.

Duas coisas que a tela precisa proteger, ambas conferidas no binário:

* **cabeçalho desconhecido vira comando do sistema.** O shell entrega ao
  ``/bin/sh`` o que não reconhece como cartão nem embutido — um ``rm -rf``
  digitado aqui executaria de verdade. O :class:`Shell4` barra antes de
  mandar, e a tela mostra a recusa.
* **``define`` contamina o resto da sessão.** Depois de ``define temp 1000``,
  todo comando com a palavra ``temp`` é reescrito: ``diffuse temp=950`` chega
  ao motor como ``diffuse 1000=950`` e é recusado. E não há volta — ``undef
  temp`` falha com "can not find macro 1000", porque o próprio argumento é
  substituído antes. Daí o botão de reiniciar a sessão ser proeminente.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ...core import shell4
from .. import theme
from ..widgets.common import button, eyebrow, hline, label

#: Comandos de exemplo, todos conferidos contra o binário. Os do mockup
#: usavam ``set temp 1000`` (``set`` só liga e desliga interactive, noexecute,
#: echo e prompt), ``$t`` em vez de ``${t}``, ``diffuse … inert`` (não existe:
#: o inerte é ``nitrogen`` ou ``argon``) e um ``foreach`` de uma linha só.
SNIPPETS: tuple[tuple[str, str], ...] = (
    ("help diffuse",
     "A gramática do cartão, com tipo e unidade de cada parâmetro."),
    ("mode two.dim",
     "Entra no modo bidimensional antes de definir a malha."),
    ("line y loc=0 spac=0.02 tag=topo",
     "Uma linha da malha. A tag serve ao region e ao boundary."),
    ("initialize boron conc=1e15 orient=100 line.data",
     "Cria a estrutura e lista as posições que a malha gerou."),
    ("select z=doping",
     "Escolhe a grandeza antes de imprimir; sem isso vem “Z variable is "
     "out of date”."),
    ("print.1d x.value=0.5 layers",
     "A pilha de camadas naquele corte. Sem o x.value em 2-D, as espessuras "
     "saem zeradas."),
    ("foreach O (100 110 111)",
     "Abre um laço; o corpo vem nas linhas seguintes e termina em “end”."),
    ("source receita.in",
     "Roda um deck inteiro sem perder a sessão."),
)

#: Quanto da conversa fica na tela. Uma varredura longa gera milhares de
#: linhas e não adianta guardar todas.
MAX_LINES = 4000


class ConsoleScreen(QWidget):
    """A tela inteira de Console."""

    #: Pede à janela o deck da receita atual, para o botão "enviar a receita".
    deck_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shell: shell4.Shell4 | None = None
        self._history: list[str] = []
        self._pos = 0

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(divisor)
        divisor.addWidget(self._build_console())
        divisor.addWidget(self._build_aside())
        divisor.setSizes([900, theme.dimension("sidebar-width")])
        divisor.setStretchFactor(0, 1)

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_console(self) -> QWidget:
        host = QWidget()
        theme.mark(host, surface="code")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        barra = QWidget()
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(theme.space("9"), theme.space("5"),
                              theme.space("9"), theme.space("5"))
        bl.setSpacing(theme.space("6"))
        bl.addWidget(eyebrow("shell suprem-iv"))
        self._pasta = label("—", "mono")
        bl.addWidget(self._pasta)
        bl.addStretch(1)
        self._estado = label("desligado", "mono")
        bl.addWidget(self._estado)
        bl.addWidget(button("Limpar", "small", on_click=self.clear))
        bl.addWidget(button("Reiniciar a sessão", "small",
                            tooltip="Sobe o motor de novo, zerando malha, "
                                    "soluções e variáveis",
                            on_click=self.restart))
        lay.addWidget(barra)
        lay.addWidget(hline())

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(theme.font("mono", "small", spacing="normal"))
        self.view.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        self.view.setMaximumBlockCount(MAX_LINES)
        lay.addWidget(self.view, 1)

        entrada = QWidget()
        el = QHBoxLayout(entrada)
        el.setContentsMargins(theme.space("9"), theme.space("5"),
                              theme.space("9"), theme.space("7"))
        el.setSpacing(theme.space("5"))
        el.addWidget(label("SUPREM-IV>", "mono"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("digite help")
        self.input.setFont(theme.font("mono", "small", spacing="normal"))
        theme.mark(self.input, role="mono")
        self.input.returnPressed.connect(self._submit)
        self.input.installEventFilter(self)
        el.addWidget(self.input, 1)
        lay.addWidget(entrada)
        return host

    def _build_aside(self) -> QWidget:
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setMinimumWidth(theme.dimension("sidebar-width"))
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("8"), theme.space("9"),
                               theme.space("8"), theme.space("9"))
        lay.setSpacing(theme.space("6"))

        lay.addWidget(eyebrow("experimente"))
        for cmd, desc in SNIPPETS:
            b = button("", "small", on_click=lambda _c=False, c=cmd: self.run(c))
            b.setText(cmd)
            b.setToolTip(desc)
            b.setFont(theme.font("mono", "small", spacing="normal"))
            b.setMinimumHeight(theme.space("12"))
            lay.addWidget(b)
            d = label(desc, "hint", wrap=True)
            d.setContentsMargins(theme.space("4"), 0, 0, theme.space("2"))
            lay.addWidget(d)

        lay.addWidget(hline())
        lay.addWidget(eyebrow("enviar a receita"))
        lay.addWidget(button("Rodar a receita nesta sessão", "small",
                             on_click=self.deck_requested.emit))
        lay.addWidget(label(
            "Grava o deck na pasta da sessão e manda um source. O estado "
            "fica na memória depois, para você continuar perguntando.",
            "hint", wrap=True))

        lay.addWidget(hline())
        lay.addWidget(eyebrow("cuidado com define"))
        lay.addWidget(label(
            "define temp 1000 reescreve a palavra temp em todo comando "
            "seguinte: diffuse temp=950 chega ao motor como diffuse "
            "1000=950. E não dá para desfazer — undef temp falha, porque o "
            "próprio argumento é substituído antes. Nesse caso, reinicie a "
            "sessão.", "hint", wrap=True))
        lay.addStretch(1)
        rolagem.setWidget(host)
        return rolagem

    # ── sessão ────────────────────────────────────────────────────────────

    def ensure_started(self) -> bool:
        """Sobe o motor se ainda não subiu. ``False`` se não foi possível."""
        if self._shell is not None and self._shell.alive:
            return True
        try:
            self._shell = shell4.Shell4()
            r = self._shell.start()
        except RuntimeError as exc:
            self._print(str(exc), "erro")
            self._set_state(False)
            return False
        self._pasta.setText(str(self._shell.work_dir))
        self._print("SUPREM-IV · shell interativo. Digite help para ver os "
                    "comandos.", "dim")
        if r.text:
            self._print(r.text, "dim")
        self._set_state(True)
        return True

    def restart(self) -> None:
        """Sobe o motor de novo, zerando tudo."""
        if self._shell is None:
            self.ensure_started()
            return
        self._shell.restart()
        self.clear()
        self._print("Sessão reiniciada: malha, soluções e variáveis zeradas.",
                    "dim")
        self._set_state(self._shell.alive)

    def close_session(self) -> None:
        if self._shell is not None:
            self._shell.close()
            self._shell = None
        self._set_state(False)

    def clear(self) -> None:
        self.view.clear()

    def used(self) -> bool:
        """``True`` se o usuário já mandou algum comando."""
        return bool(self._history)

    # ── comandos ──────────────────────────────────────────────────────────

    def run(self, command: str) -> None:
        """Manda um comando e mostra a resposta."""
        if not self.ensure_started() or self._shell is None:
            return
        self._print(f"SUPREM-IV> {command}", "cmd")
        self._history.append(command)
        self._pos = len(self._history)
        resposta = self._shell.send(command)
        if resposta.text:
            self._print(resposta.text, "erro" if resposta.errors else "")
        for e in resposta.errors:
            self._print(f"  ! {e}", "erro")
        if resposta.crashed:
            self._print("O motor encerrou. Reinicie a sessão para continuar.",
                        "erro")
        if resposta.timed_out:
            self._print("A espera estourou; a resposta pode estar "
                        "incompleta.", "erro")
        self._set_state(self._shell.alive)

    def run_deck(self, deck: str) -> None:
        """Manda um deck inteiro por ``source``, sem perder a sessão."""
        if not self.ensure_started() or self._shell is None:
            return
        self._print("SUPREM-IV> source (receita do projeto)", "cmd")
        resposta = self._shell.source(deck)
        if resposta.text:
            self._print(resposta.text, "erro" if resposta.errors else "")
        for e in resposta.errors:
            self._print(f"  ! {e}", "erro")
        self._set_state(self._shell.alive)

    def _submit(self) -> None:
        texto = self.input.text().strip()
        if not texto:
            return
        self.input.clear()
        self.run(texto)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - API do Qt
        """Seta para cima e para baixo percorrem o histórico."""
        from PySide6.QtCore import QEvent

        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Up:
                self._recall(-1)
                return True
            if event.key() == Qt.Key.Key_Down:
                self._recall(1)
                return True
        return super().eventFilter(obj, event)

    def _recall(self, passo: int) -> None:
        if not self._history:
            return
        self._pos = max(0, min(len(self._history), self._pos + passo))
        self.input.setText(self._history[self._pos]
                           if self._pos < len(self._history) else "")

    # ── saída ─────────────────────────────────────────────────────────────

    def _print(self, texto: str, estilo: str = "") -> None:
        cor = {"cmd": theme.qcolor("accent-ink"),
               "erro": theme.qcolor("accent"),
               "dim": theme.qcolor("ink-dim")}.get(estilo)
        if cor is None:
            self.view.appendPlainText(texto)
        else:
            seguro = (texto.replace("&", "&amp;").replace("<", "&lt;")
                      .replace(">", "&gt;").replace("\n", "<br>"))
            self.view.appendHtml(
                f'<span style="color:{cor.name()}">{seguro}</span>')
        barra = self.view.verticalScrollBar()
        barra.setValue(barra.maximum())

    def _set_state(self, vivo: bool) -> None:
        self._estado.setText("ativo" if vivo else "desligado")
