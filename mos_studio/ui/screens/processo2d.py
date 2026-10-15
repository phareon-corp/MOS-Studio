"""Tela de Processo 2-D: a receita do SUPREM-IV.

Mesma divisão em três colunas da tela 1-D — receita, formulário da etapa, deck
— porque é o mesmo gesto: montar uma sequência de etapas físicas e ver o
arquivo que vai para o motor. A lista e o formulário são os mesmos widgets: o
``Step4`` tem a mesma interface do ``Step`` 1-D de propósito.

O que muda é o vocabulário e o que a verificação sabe. Em 2-D a corrosão tem
forma (à esquerda de uma reta, por coordenadas), o implante é autoalinhado
pela máscara que já está na lâmina, e há avisos que só fazem sentido aqui —
como o de implantar sem recozer depois, que faz a tela de Resultados parecer
vazia porque a dopagem *ativa* ainda não enxerga o implante.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from ...core import mesh as mesh_mod
from ...core import recipe4
from .. import theme
from ..widgets.common import button, eyebrow, hline, label, row, stretch
from ..widgets.deck_view import DeckPanel
from ..widgets.error_panel import EngineErrorPanel
from ..widgets.step_form import StepForm
from ..widgets.step_list import StepList

#: Receita com que a tela abre: o transistor LDD do ``exam5``, que é o
#: exemplo de referência do manual e o projeto guiado da interface.
RECEITA_INICIAL: list[tuple[str, dict]] = [
    ("INIT", {"impurity": "boron", "conc": "1E15", "orient": "100"}),
    ("DIFFUSE", {"ambient": "dryo2", "temp": "1000", "time": "30"}),
    ("DEPOSIT", {"material": "poly", "thick": "0.3", "divisions": "6"}),
    ("ETCH", {"material": "poly", "mode": "right", "p1x": "0.35"}),
    ("IMPLANT", {"impurity": "phosphorus", "dose": "5E13", "energy": "40"}),
    ("DIFFUSE", {"ambient": "nitrogen", "temp": "900", "time": "30"}),
    ("DEPOSIT", {"material": "oxide", "thick": "0.15", "divisions": "4"}),
    ("ETCH", {"material": "oxide", "mode": "dry", "thick": "0.15"}),
    ("IMPLANT", {"impurity": "arsenic", "dose": "5E15", "energy": "60"}),
    ("DIFFUSE", {"ambient": "nitrogen", "temp": "900", "time": "20"}),
]

TITULO_INICIAL = "TRANSISTOR LDD - SECAO TRANSVERSAL"


def receita_inicial() -> list[recipe4.Step4]:
    """Uma cópia nova da receita de abertura."""
    passos = []
    for tipo, params in RECEITA_INICIAL:
        s = recipe4.Step4.new(tipo)
        s.params.update(params)
        passos.append(s)
    return passos


class Process2DScreen(QWidget):
    """A tela inteira de Processo 2-D."""

    recipe_changed = Signal()
    run_literal_requested = Signal()
    #: O projeto guiado pede a próxima etapa do roteiro.
    guided_step_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.steps: list[recipe4.Step4] = receita_inicial()
        self.title: str = TITULO_INICIAL
        self._mesh = mesh_mod.default_mesh()
        self._selected: int | None = self.steps[0].uid if self.steps else None
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []
        self._running_index = -1
        self._done_before = -1

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(self._splitter)

        self._splitter.addWidget(self._build_recipe_panel())
        self._splitter.addWidget(self._build_detail_panel())
        self.deck = DeckPanel()
        self.deck.step_requested.connect(self.select_step)
        self.deck.edit_started.connect(self._start_manual_edit)
        self.deck.edit_discarded.connect(self._discard_manual_edit)
        self.deck.run_literal_requested.connect(self.run_literal_requested.emit)
        self.deck.hide_requested.connect(self.hide_deck)
        self._splitter.addWidget(self.deck)
        self._splitter.setSizes([theme.dimension("sidebar-width"), 620,
                                 theme.dimension("deck-min-width")])
        self._splitter.setStretchFactor(1, 1)
        self.refresh()

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_recipe_panel(self) -> QWidget:
        painel = QWidget()
        painel.setMinimumWidth(theme.dimension("sidebar-width")
                               - theme.space("20"))
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        topo = QWidget()
        tl = QVBoxLayout(topo)
        tl.setContentsMargins(theme.space("8"), theme.space("9"),
                              theme.space("8"), theme.space("7"))
        tl.setSpacing(theme.space("6"))
        self._contagem = label("", "mono")
        tl.addWidget(row(eyebrow("receita 2-d"), stretch(), self._contagem))

        self._b_catalogo = button("+  Adicionar etapa", "small",
                                  checkable=True)
        self._b_catalogo.toggled.connect(
            lambda aberto: self._catalogo.setVisible(aberto))
        self._b_undo = button("Desfazer", "small", tooltip="Ctrl+Z",
                              on_click=self.undo)
        self._b_redo = button("Refazer", "small", tooltip="Ctrl+Shift+Z",
                              on_click=self.redo)
        tl.addWidget(row(self._b_catalogo, stretch(), self._b_undo,
                         self._b_redo, spacing="3"))

        # Só aparece durante o projeto guiado: ali a próxima etapa é uma só,
        # e o catálogo inteiro seria um convite a errar o roteiro.
        self.b_guiado = button("Acrescentar a próxima etapa", "primary",
                               on_click=self.guided_step_requested.emit)
        self.b_guiado.hide()
        tl.addWidget(self.b_guiado)
        lay.addWidget(topo)
        lay.addWidget(hline())

        self._catalogo = self._build_catalog()
        self._catalogo.hide()
        lay.addWidget(self._catalogo)

        self.lista = StepList()
        self.lista.step_selected.connect(self.select_step)
        self.lista.reordered.connect(self._on_reordered)
        lay.addWidget(self.lista, 1)

        rodape = label("A malha vem da tela de Malha e entra no deck antes da "
                       "primeira etapa.", "hint", wrap=True)
        rodape.setContentsMargins(theme.space("8"), theme.space("6"),
                                  theme.space("8"), theme.space("6"))
        lay.addWidget(rodape)
        return painel

    def _build_catalog(self) -> QWidget:
        host = QWidget()
        theme.mark(host, surface="raised")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("4"), theme.space("4"),
                               theme.space("4"), theme.space("4"))
        lay.setSpacing(theme.space("1"))
        for tipo in recipe4.STEP_TYPES:
            b = button(f"{recipe4.STEP_LABELS[tipo]}   ·   {tipo}", "small",
                       on_click=lambda _c=False, t=tipo: self.add_step(t))
            b.setToolTip(recipe4.STEP_DESCRIPTIONS[tipo])
            b.setProperty("variant", "link")
            b.setFont(theme.font("sans", "base"))
            b.setMinimumHeight(theme.space("14"))
            lay.addWidget(b)
        nota = label(
            "Não há etapa de gráfico: os cartões plot.1d, plot.2d e contour "
            "desta compilação não desenham nada — a biblioteca gráfica são "
            "talões vazios. Os desenhos da tela de Resultados saem das "
            "tabelas do print.1d.", "hint", wrap=True)
        nota.setContentsMargins(theme.space("5"), theme.space("4"),
                                theme.space("5"), theme.space("2"))
        lay.addWidget(nota)
        return host

    def _build_detail_panel(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._banner = QWidget()
        theme.mark(self._banner, surface="accent-soft")
        bl = QVBoxLayout(self._banner)
        bl.setContentsMargins(theme.space("16"), theme.space("8"),
                              theme.space("16"), theme.space("8"))
        bl.setSpacing(theme.space("4"))
        self._banner_titulo = label("", "base")
        self._banner_titulo.setFont(theme.font("sans", "base", "semibold"))
        theme.mark(self._banner_titulo, role="error")
        bl.addWidget(self._banner_titulo)
        self._banner_itens = QWidget()
        self._banner_lay = QVBoxLayout(self._banner_itens)
        self._banner_lay.setContentsMargins(0, 0, 0, 0)
        self._banner_lay.setSpacing(theme.space("2"))
        bl.addWidget(self._banner_itens)
        lay.addWidget(self._banner)
        self._banner.hide()

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        self.form = StepForm()
        self.form.param_changed.connect(self._on_param_changed)
        self.form.move_requested.connect(self.move_selected)
        self.form.duplicate_requested.connect(self.duplicate_selected)
        self.form.remove_requested.connect(self.remove_selected)
        rolagem.setWidget(self.form)
        lay.addWidget(rolagem, 1)

        self.erro = EngineErrorPanel()
        lay.addWidget(self.erro)
        return host

    # ── histórico ─────────────────────────────────────────────────────────

    def _snapshot(self) -> tuple:
        return (self.title,
                tuple((s.type, tuple(sorted(s.params.items())), s.uid)
                      for s in self.steps),
                self._selected)

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        del self._undo[:-50]
        self._redo.clear()

    def _restore(self, snap: tuple) -> None:
        titulo, passos, selecionado = snap
        self.title = titulo
        self.steps = [recipe4.Step4(type=t, params=dict(p), uid=u)
                      for t, p, u in passos]
        self._selected = selecionado
        self.refresh()
        self.recipe_changed.emit()

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    # ── receita ───────────────────────────────────────────────────────────

    def _index_of(self, uid: int | None) -> int:
        return next((i for i, s in enumerate(self.steps) if s.uid == uid), -1)

    def selected_step(self) -> recipe4.Step4 | None:
        i = self._index_of(self._selected)
        return self.steps[i] if i >= 0 else None

    def select_step(self, uid: int) -> None:
        if self._index_of(uid) < 0:
            return
        self._selected = uid
        self._refresh_light()

    def add_step(self, step_type: str) -> None:
        self._push_undo()
        novo = recipe4.Step4.new(step_type)
        i = self._index_of(self._selected)
        self.steps.insert(i + 1 if i >= 0 else len(self.steps), novo)
        self._selected = novo.uid
        self._b_catalogo.setChecked(False)
        self.refresh()
        self.recipe_changed.emit()

    def duplicate_selected(self) -> None:
        i = self._index_of(self._selected)
        if i < 0:
            return
        self._push_undo()
        copia = self.steps[i].copy()
        self.steps.insert(i + 1, copia)
        self._selected = copia.uid
        self.refresh()
        self.recipe_changed.emit()

    def remove_selected(self) -> None:
        i = self._index_of(self._selected)
        if i < 0:
            return
        self._push_undo()
        del self.steps[i]
        if self.steps:
            self._selected = self.steps[min(i, len(self.steps) - 1)].uid
        else:
            self._selected = None
        self.refresh()
        self.recipe_changed.emit()

    def move_selected(self, direction: int) -> None:
        i = self._index_of(self._selected)
        j = i + direction
        if i < 0 or not (0 <= j < len(self.steps)):
            return
        self._push_undo()
        self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
        self.refresh()
        self.recipe_changed.emit()

    def _on_reordered(self, origem: int, destino: int) -> None:
        if not (0 <= origem < len(self.steps)) or origem == destino:
            return
        self._push_undo()
        passo = self.steps.pop(origem)
        self.steps.insert(min(destino, len(self.steps)), passo)
        self._selected = passo.uid
        self.refresh()
        self.recipe_changed.emit()

    def _on_param_changed(self, uid: int, key: str, value) -> None:
        i = self._index_of(uid)
        if i < 0:
            return
        if self.steps[i].params.get(key) == value:
            return
        self._push_undo()
        self.steps[i].params[key] = value
        self.refresh()
        self.recipe_changed.emit()

    # ── malha e deck ──────────────────────────────────────────────────────

    def set_guided(self, ativo: bool, restam: int = 0, total: int = 0) -> None:
        """Liga o modo do projeto guiado.

        O rótulo é curto de propósito: a coluna da receita tem a largura da
        barra lateral, e "Acrescentar a próxima etapa · faltam N" era cortado
        no meio. A contagem inteira fica no tooltip.
        """
        self.b_guiado.setVisible(ativo and restam > 0)
        if ativo and restam > 0:
            feitas = max(0, total - restam)
            self.b_guiado.setText(f"Próxima etapa · {feitas + 1} de {total}"
                                  if total else "Próxima etapa")
            self.b_guiado.setToolTip(
                f"Acrescenta a próxima etapa do roteiro; faltam {restam}.")
        self._b_catalogo.setVisible(not ativo)

    def set_mesh(self, malha: mesh_mod.Mesh) -> None:
        """A malha vem da tela de Malha; o deck a recebe inteira."""
        self._mesh = malha
        self.refresh()

    def mesh(self) -> mesh_mod.Mesh:
        return self._mesh

    def deck_lines(self) -> list[tuple[str, int | None]]:
        return recipe4.cards_with_origin(mesh_mod.to_cards(self._mesh),
                                         self.steps)

    def deck_text(self, *, print_cut: float | None = None) -> str:
        if self.deck.editing:
            return self.deck.text()
        return recipe4.build_deck(self.title, mesh_mod.to_cards(self._mesh),
                                  self.steps, print_cut=print_cut)

    def manual_deck(self) -> bool:
        return self.deck.editing

    def _start_manual_edit(self) -> None:
        self.deck.set_manual(self.deck_text())

    def _discard_manual_edit(self) -> None:
        self.deck.set_generated(self.deck_lines(), self._deck_filename())
        self.refresh()

    def _deck_filename(self) -> str:
        from ...core.workspace import slug
        return f"{slug(self.title.title() or 'processo')}.IN"

    def hide_deck(self) -> None:
        self.deck.hide()

    def show_deck(self) -> None:
        self.deck.show()

    def toggle_deck(self) -> None:
        self.deck.setVisible(not self.deck.isVisible())

    # ── verificação ───────────────────────────────────────────────────────

    def issues(self) -> list[recipe4.Issue]:
        problemas = list(recipe4.validate(self.steps))
        for texto in self._mesh_issues():
            problemas.append(recipe4.Issue(-1, texto))
        return problemas

    def warnings(self) -> list[recipe4.Issue]:
        return recipe4.warnings(self.steps)

    def _mesh_issues(self) -> list[str]:
        erro = (mesh_mod.validate_axis(self._mesh.x)
                or mesh_mod.validate_axis(self._mesh.y))
        return [f"Malha: {erro}"] if erro else []

    def focus_first_issue(self) -> None:
        problemas = recipe4.validate(self.steps)
        if not problemas:
            return
        alvo = next((p for p in problemas if p.uid is not None), problemas[0])
        if alvo.uid is not None:
            self.select_step(alvo.uid)

    def set_progress(self, running_index: int, done_before: int = -1) -> None:
        self._running_index = running_index
        self._done_before = done_before
        self._refresh_list()

    # ── redesenho ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._refresh_list()
        self._refresh_banner()
        passo = self.selected_step()
        i = self._index_of(self._selected)
        self.form.show_step(passo, i + 1, len(self.steps))
        if not self.deck.editing:
            self.deck.set_generated(self.deck_lines(), self._deck_filename())
        self.deck.highlight_step(self._selected)

    def _refresh_light(self) -> None:
        passo = self.selected_step()
        i = self._index_of(self._selected)
        self.form.show_step(passo, i + 1, len(self.steps))
        self.lista.populate(self.steps, selected_uid=self._selected,
                            issues=self._issue_rows(),
                            running_index=self._running_index,
                            done_before=self._done_before)
        self.deck.highlight_step(self._selected)

    def _issue_rows(self) -> set[int]:
        return {p.index for p in recipe4.validate(self.steps) if p.index >= 0}

    def _refresh_list(self) -> None:
        self._contagem.setText(f"{len(self.steps)} etapas")
        self.lista.populate(self.steps, selected_uid=self._selected,
                            issues=self._issue_rows(),
                            running_index=self._running_index,
                            done_before=self._done_before)

    def _refresh_banner(self) -> None:
        while self._banner_lay.count():
            item = self._banner_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        problemas = self.issues()
        avisos = self.warnings()
        if not problemas and not avisos:
            self._banner.hide()
            return
        if problemas:
            self._banner_titulo.setText(
                "1 problema impede a simulação" if len(problemas) == 1
                else f"{len(problemas)} problemas impedem a simulação")
        else:
            self._banner_titulo.setText(
                "1 aviso" if len(avisos) == 1 else f"{len(avisos)} avisos")
        for p in (problemas or avisos)[:4]:
            numero = f"{p.index + 1:02d} · " if p.index >= 0 else ""
            self._banner_lay.addWidget(
                label(f"{numero}{p.message}", "hint", wrap=True))
        self._banner.show()
