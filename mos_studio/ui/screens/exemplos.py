"""Tela de Exemplos: os decks de fábrica do manual.

O capítulo 4 do manual do SUPREM-IV traz dezessete exemplos, e o build
instala todos. Cada cartão aqui mostra o que o deck demonstra e quais
comandos ele usa — lidos do próprio arquivo, não de uma tabela à parte
(:mod:`mos_studio.core.examples4`).

Três dos decks são defeituosos de fábrica e o catálogo diz por quê, antes de
o usuário clicar: o ``exam6`` tem um ``echo`` decorativo que o avaliador de
expressão recusa, e o ``exam11`` e o ``exam12`` pedem ``select
z=log10(silicon)`` quando em GaAs a espécie se chama ``isilicon``.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHBoxLayout, QScrollArea, QVBoxLayout,
                               QWidget)

from ...core import examples3, examples4
from .. import theme
from ..widgets.common import (ResponsiveGrid, button, column,
                              eyebrow, label)

#: Largura mínima de um cartão antes de a grade quebrar a linha. É o
#: ``minmax(min(100%,270px),1fr)`` do arquivo de design: o número de colunas
#: sai da largura disponível, não de uma constante.
CARD_MIN_WIDTH = 270


class _Recipe1DCard(QWidget):
    """Um exemplo 1-D, que abre como projeto editável."""

    chosen = Signal(str)

    def __init__(self, ex: examples3.Example3,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.example = ex
        theme.mark(self, surface="raised")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.space("8"), theme.space("8"),
                               theme.space("8"), theme.space("8"))
        lay.setSpacing(theme.space("4"))
        self.setMinimumHeight(theme.space("24") * 3)

        topo = QHBoxLayout()
        topo.setSpacing(theme.space("4"))
        ident = label(ex.engine.lower(), "mono")
        theme.mark(ident, role="eyebrow-accent")
        topo.addWidget(ident)
        topo.addStretch(1)
        topo.addWidget(label(ex.dim, "mono"))
        lay.addLayout(topo)

        titulo = label(f"{ex.name} {ex.emphasis}".strip(), "title")
        titulo.setWordWrap(True)
        lay.addWidget(titulo)
        lay.addWidget(label(ex.desc, "hint", wrap=True))
        lay.addStretch(1)
        if ex.expect:
            esperado = label(ex.expect, "hint", wrap=True)
            theme.mark(esperado, surface="code")
            esperado.setContentsMargins(theme.space("5"), theme.space("4"),
                                        theme.space("5"), theme.space("4"))
            lay.addWidget(esperado)
        lay.addWidget(label(f"{ex.step_count} etapas · abre como projeto",
                            "mono"))
        lay.addWidget(button("Abrir como projeto", "small",
                             on_click=lambda: self.chosen.emit(ex.id)))


class _ExampleCard(QWidget):
    """Um deck de fábrica do SUPREM-IV na grade."""

    chosen = Signal(str)

    def __init__(self, ex: examples4.Example,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.example = ex
        theme.mark(self, surface="raised")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.space("8"), theme.space("8"),
                               theme.space("8"), theme.space("8"))
        lay.setSpacing(theme.space("4"))
        self.setMinimumHeight(theme.space("24") * 3)

        topo = QHBoxLayout()
        topo.setSpacing(theme.space("4"))
        ident = label(ex.id, "mono")
        theme.mark(ident, role="eyebrow-accent")
        topo.addWidget(ident)
        topo.addStretch(1)
        dim = label(examples4.dim_of(ex), "mono")
        topo.addWidget(dim)
        lay.addLayout(topo)

        titulo = label(ex.name, "title")
        titulo.setWordWrap(True)
        lay.addWidget(titulo)
        lay.addWidget(label(ex.desc, "hint", wrap=True))
        lay.addStretch(1)

        if ex.runnable:
            lay.addWidget(label(examples4.summary(ex), "mono", wrap=True))
            lay.addWidget(button("Abrir e rodar", "small",
                                 on_click=lambda: self.chosen.emit(ex.id)))
        else:
            aviso = label("Deck defeituoso de fábrica", "error")
            lay.addWidget(aviso)
            lay.addWidget(label(ex.broken, "hint", wrap=True))
            b = button("Ver o deck", "small",
                       on_click=lambda: self.chosen.emit(ex.id))
            lay.addWidget(b)


class ExamplesScreen(QWidget):
    """A tela inteira de Exemplos."""

    #: Abrir um deck de fábrica do SUPREM-IV (pelo ``id`` do catálogo).
    example_chosen = Signal(str)
    #: Abrir uma receita 1-D como projeto (pelo ``id`` do catálogo).
    recipe_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filtro = ""

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

        cabecalho = QHBoxLayout()
        cabecalho.setSpacing(theme.space("8"))
        cabecalho.addWidget(column(
            eyebrow("exemplos", accent=True),
            label("Processos prontos", "title"),
            label("Os exemplos 1-D abrem como projeto: viram etapas na tela "
                  "de Processo e podem seguir para o MINIMOS. Os do manual "
                  "do SUPREM-IV rodam como estão, no Console.",
                  "hint", wrap=True),
            spacing="3"), 1)
        self._chips: dict[str, object] = {}
        chips = QHBoxLayout()
        chips.setSpacing(theme.space("3"))
        for chave, rotulo in (("", "Todos"), ("1-D", "1-D"), ("2-D", "2-D")):
            b = button(rotulo, "segment", checkable=True)
            b.setChecked(chave == "")
            b.clicked.connect(lambda _c=False, k=chave: self._filter(k))
            self._chips[chave] = b
            chips.addWidget(b)
        cabecalho.addLayout(chips)
        lay.addLayout(cabecalho)

        self._titulo_1d = column(
            eyebrow("1-d · suprem-iii · abrem como projeto"),
            label("Receitas editáveis", "title"), spacing="2")
        lay.addWidget(self._titulo_1d)
        self._grade_1d = ResponsiveGrid(CARD_MIN_WIDTH)
        lay.addWidget(self._grade_1d)

        self._titulo_fabrica = column(
            eyebrow("manual do suprem-iv · capítulo 4"),
            label("Decks de fábrica", "title"), spacing="2")
        lay.addWidget(self._titulo_fabrica)
        self._grade = ResponsiveGrid(CARD_MIN_WIDTH)
        lay.addWidget(self._grade)

        self._vazio = label(
            "Os exemplos não foram encontrados. Eles vêm com o motor, em "
            "suprem4-run/examples — reinstale o SUPREM-IV pelo "
            "build_suprem4.sh.", "hint", wrap=True)
        self._vazio.hide()
        lay.addWidget(self._vazio)
        lay.addStretch(1)
        rolagem.setWidget(host)
        self.refresh()

    # ── conteúdo ──────────────────────────────────────────────────────────

    def _filter(self, dim: str) -> None:
        for chave, b in self._chips.items():
            b.setChecked(chave == dim)
        self._filtro = dim
        self.refresh()

    def examples(self) -> list[examples4.Example]:
        """Decks de fábrica do SUPREM-IV que passam pelo filtro."""
        instalados = examples4.installed()
        if not self._filtro:
            return instalados
        return [e for e in instalados
                if examples4.dim_of(e) == self._filtro]

    def recipes(self) -> list[examples3.Example3]:
        """Receitas 1-D do MOS-Studio que passam pelo filtro."""
        if self._filtro == "2-D":
            return []
        return list(examples3.CATALOG)

    def refresh(self) -> None:
        self._vazio.setVisible(not examples4.installed())

        receitas = []
        for ex in self.recipes():
            cartao = _Recipe1DCard(ex)
            cartao.chosen.connect(self.recipe_chosen.emit)
            receitas.append(cartao)
        self._grade_1d.set_items(receitas)
        self._titulo_1d.setVisible(bool(receitas))
        self._grade_1d.setVisible(bool(receitas))

        cartoes = []
        for ex in self.examples():
            cartao = _ExampleCard(ex)
            cartao.chosen.connect(self.example_chosen.emit)
            cartoes.append(cartao)
        self._grade.set_items(cartoes)
        self._titulo_fabrica.setVisible(bool(cartoes))
        self._grade.setVisible(bool(cartoes))
