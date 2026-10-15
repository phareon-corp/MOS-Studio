"""Tela de Estruturas: gravar, retomar e exportar o estado da simulação.

Uma estrutura é a malha, os materiais e **todas** as soluções num ponto do
processo. Serve para três coisas: retomar uma simulação longa sem refazer as
etapas, exportar para um simulador de dispositivo, e trazer um perfil medido
de fora como dopagem inicial.

Os cartões foram conferidos contra o ``suprem.key``. O mockup trazia
``profile infile=sims.dat impurity=boron``; o cartão ``profile`` não tem
``impurity`` — a espécie entra como palavra solta, ``profile boron
infile=sims.dat``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QScrollArea,
                               QVBoxLayout, QWidget)

from .. import theme
from ..widgets.common import (ResponsiveGrid, button, column,
                              eyebrow, hline, label)

#: Largura mínima de um cartão de ação antes de a grade quebrar a linha.
CARD_MIN_WIDTH = 250

#: Extensões que o motor grava. ``.str``/``.sup`` são estruturas completas;
#: ``.mesh``/``.pis`` são malhas exportadas.
STRUCTURE_SUFFIXES = (".str", ".sup", ".s4s")
EXPORT_SUFFIXES = (".mesh", ".pis", ".simpl")


@dataclass(frozen=True)
class Action:
    """Uma das coisas que dá para fazer com uma estrutura."""

    label: str
    desc: str
    card: str
    #: Nome da etapa da receita que faz isso, quando existe uma.
    step: str = ""


ACTIONS: tuple[Action, ...] = (
    Action("Salvar estrutura",
           "Grava malha, materiais e todas as soluções do ponto atual da "
           "receita. Acrescente uma etapa “Salvar estrutura” onde quiser o "
           "ponto de retomada.",
           "structure outfile=estrutura.str", step="STRUCTURE"),
    Action("Retomar de uma estrutura",
           "Carrega uma estrutura gravada e continua dali, sem refazer as "
           "etapas anteriores. Substitui a malha e o initialize.",
           "structure infile=estrutura.str"),
    Action("Exportar para o PISCES",
           "Grava a malha com a dopagem no formato do simulador de "
           "dispositivo. É o que o segundo deck do exam5 faz.",
           "structure pisces=dispositivo.mesh"),
    Action("Montar o dispositivo inteiro",
           "A simulação usa metade da seção, com a borda esquerda como plano "
           "de simetria. O espelho reconstrói a outra metade antes de gravar.",
           "structure mirror left"),
    Action("Importar um perfil medido",
           "Lê um perfil de SIMS como dopagem inicial, em vez de calcular o "
           "implante. A espécie é palavra solta, não impurity=.",
           "profile boron infile=sims.dat"),
)


class StructureScreen(QWidget):
    """A tela inteira de Estruturas."""

    #: Pede para acrescentar uma etapa à receita 2-D.
    add_step_requested = Signal(str)
    #: Pede para mandar um comando ao Console.
    command_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dir: Path | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        raiz.addWidget(rolagem)

        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("12"), theme.space("11"),
                               theme.space("12"), theme.space("12"))
        lay.setSpacing(theme.space("9"))

        lay.addWidget(column(
            eyebrow("structure · profile", accent=True),
            label("Arquivos de estrutura", "title"),
            label("Uma estrutura guarda malha, materiais e soluções. Salve "
                  "no meio da receita para retomar depois, ou exporte para "
                  "simular o dispositivo em outro programa.", "hint",
                  wrap=True), spacing="3"))

        # Grade que reflui: cinco cartões lado a lado só cabem numa janela
        # larga; abaixo disso eles quebram em linhas em vez de espremer o
        # texto. É o ``auto-fit minmax(min(100%,250px),1fr)`` do design.
        self._cartoes = ResponsiveGrid(CARD_MIN_WIDTH)
        self._cartoes.set_items([self._build_action(a) for a in ACTIONS])
        lay.addWidget(self._cartoes)

        lay.addWidget(hline())
        cabecalho = QWidget()
        hl = QHBoxLayout(cabecalho)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(theme.space("6"))
        hl.addWidget(eyebrow("arquivos na pasta da execução"))
        hl.addStretch(1)
        self._pasta = label("—", "mono")
        hl.addWidget(self._pasta)
        hl.addWidget(button("Escolher a pasta…", "small",
                            on_click=self._pick_dir))
        hl.addWidget(button("Atualizar", "small", on_click=self.refresh))
        lay.addWidget(cabecalho)

        self._lista = QWidget()
        self._lista_lay = QVBoxLayout(self._lista)
        self._lista_lay.setContentsMargins(0, 0, 0, 0)
        self._lista_lay.setSpacing(0)
        lay.addWidget(self._lista)
        lay.addStretch(1)
        rolagem.setWidget(host)
        self.refresh()

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_action(self, a: Action) -> QWidget:
        host = QWidget()
        theme.mark(host, surface="raised")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("7"), theme.space("7"),
                               theme.space("7"), theme.space("7"))
        lay.setSpacing(theme.space("4"))
        titulo = label(a.label)
        titulo.setFont(theme.font("sans", "base", "medium"))
        titulo.setWordWrap(True)
        lay.addWidget(titulo)
        lay.addWidget(label(a.desc, "hint", wrap=True))
        lay.addStretch(1)
        cartao = label(a.card, "mono", wrap=True)
        theme.mark(cartao, surface="code")
        cartao.setContentsMargins(theme.space("4"), theme.space("3"),
                                  theme.space("4"), theme.space("3"))
        lay.addWidget(cartao)
        acoes = QHBoxLayout()
        acoes.setSpacing(theme.space("3"))
        if a.step:
            acoes.addWidget(button(
                "Acrescentar à receita", "small",
                on_click=lambda _c=False, s=a.step:
                self.add_step_requested.emit(s)))
        acoes.addWidget(button(
            "Mandar ao Console", "small",
            on_click=lambda _c=False, c=a.card:
            self.command_requested.emit(c)))
        acoes.addStretch(1)
        lay.addLayout(acoes)
        return host

    # ── arquivos ──────────────────────────────────────────────────────────

    def set_directory(self, pasta: Path | None) -> None:
        self._dir = Path(pasta) if pasta else None
        self.refresh()

    def _pick_dir(self) -> None:
        escolhida = QFileDialog.getExistingDirectory(
            self, "Pasta com as estruturas",
            str(self._dir) if self._dir else "")
        if escolhida:
            self.set_directory(Path(escolhida))

    def files(self) -> list[Path]:
        """Estruturas e exportações da pasta, da mais recente para a antiga."""
        if self._dir is None or not self._dir.is_dir():
            return []
        alvos = STRUCTURE_SUFFIXES + EXPORT_SUFFIXES
        try:
            achados = [p for p in self._dir.iterdir()
                       if p.is_file() and p.suffix.lower() in alvos]
        except OSError:
            return []
        return sorted(achados, key=lambda p: p.stat().st_mtime, reverse=True)

    def refresh(self) -> None:
        self._pasta.setText(str(self._dir) if self._dir else "—")
        while self._lista_lay.count():
            item = self._lista_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        arquivos = self.files()
        if not arquivos:
            self._lista_lay.addWidget(label(
                "Nenhuma estrutura nesta pasta ainda. Acrescente uma etapa "
                "“Salvar estrutura” à receita e rode o processo.",
                "hint", wrap=True))
            return
        for p in arquivos:
            self._lista_lay.addWidget(self._build_file_row(p))
            self._lista_lay.addWidget(hline())

    def _build_file_row(self, caminho: Path) -> QWidget:
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(0, theme.space("5"), 0, theme.space("5"))
        lay.setSpacing(theme.space("6"))
        nome = label(caminho.name, "mono")
        nome.setMinimumWidth(theme.space("24") * 2)
        lay.addWidget(nome, 3)
        exportacao = caminho.suffix.lower() in EXPORT_SUFFIXES
        lay.addWidget(label("malha exportada" if exportacao
                            else "estrutura completa", "hint"), 2)
        try:
            tamanho = caminho.stat().st_size
        except OSError:
            tamanho = 0
        lay.addWidget(label(f"{tamanho / 1024:.0f} kB", "mono"), 1)
        lay.addStretch(1)
        if not exportacao:
            lay.addWidget(button(
                "Retomar daqui", "small",
                tooltip=f"structure infile={caminho.name}",
                on_click=lambda _c=False, n=caminho.name:
                self.command_requested.emit(f"structure infile={n}")))
        return host
