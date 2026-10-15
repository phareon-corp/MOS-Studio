"""Tela de Processo: montar a receita, gerar o deck e rodar.

Três colunas, como no arquivo de design: a receita à esquerda (lista ordenada
de etapas), o formulário da etapa escolhida no meio, e o deck à direita.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from ...core import deck as deck_mod
from ...core.recipe import (STEP_DESCRIPTIONS, STEP_LABELS, STEP_TYPES,
                            Issue, Step, validate)
from .. import theme
from ..widgets.common import button, eyebrow, hline, label, row, stretch
from ..widgets.deck_view import DeckPanel
from ..widgets.error_panel import EngineErrorPanel
from ..widgets.step_form import StepForm
from ..widgets.step_list import StepList

#: Receita de exemplo com que o programa abre — o diodo PN por difusão.
RECEITA_INICIAL = [
    ("INITIALIZE", {"orientation": "100", "dopant": "BORON",
                    "concentration": "1E15", "dx": "5E-3", "thickness": "0.5"}),
    ("DIFFUSION", {"ambient": "DRYO2", "temperature": "1000", "time": "15",
                   "gasConc": "", "solidSol": False, "tRate": ""}),
    ("ETCH", {"material": "OXIDE", "all": True, "thickness": ""}),
    ("DIFFUSION", {"ambient": "PHOSPHOR", "temperature": "1000", "time": "30",
                   "gasConc": "1E18", "solidSol": False, "tRate": ""}),
    ("DIFFUSION", {"ambient": "NITROGEN", "temperature": "900", "time": "15",
                   "gasConc": "", "solidSol": False, "tRate": ""}),
    ("PRINT", {"what": "NET", "curve": "ACTIVE", "extra": "CONCENTR",
               "filename": "DIODED.OUT", "linespa": "1000"}),
    ("PRINT", {"what": "NET", "curve": "", "extra": "LAYER",
               "filename": "DIODEL.OUT", "linespa": "1000"}),
]

TITULO_INICIAL = "DIODO PN - DIFUSAO DE FOSFORO EM SILICIO TIPO P"


class ProcessScreen(QWidget):
    """A tela inteira de Processo."""

    recipe_changed = Signal()
    run_literal_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.steps: list[Step] = [Step(t, dict(p)) for t, p in RECEITA_INICIAL]
        self.title: str = TITULO_INICIAL
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
        self._splitter.setSizes([theme.dimension("sidebar-width"), 640,
                                 theme.dimension("deck-min-width")])
        self._splitter.setStretchFactor(1, 1)

        self.refresh()

    # ── construção ────────────────────────────────────────────────────────

    def _build_recipe_panel(self) -> QWidget:
        painel = QWidget()
        painel.setMinimumWidth(theme.dimension("sidebar-width") - theme.space("20"))
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        topo = QWidget()
        tl = QVBoxLayout(topo)
        tl.setContentsMargins(theme.space("8"), theme.space("9"),
                              theme.space("8"), theme.space("7"))
        tl.setSpacing(theme.space("6"))

        self._contagem = label("", "mono")
        tl.addWidget(row(eyebrow("receita"), stretch(), self._contagem))

        tl.addWidget(label("Título do deck", "hint"))
        self._titulo = QLineEdit(self.title)
        self._titulo.setMaxLength(72)
        self._titulo.setFont(theme.font("mono", "small", spacing="normal"))
        theme.mark(self._titulo, role="mono")
        self._titulo.textEdited.connect(self._on_title_edited)
        self._titulo.setCursorPosition(0)
        tl.addWidget(self._titulo)

        self._b_catalogo = button("+  Adicionar etapa", "small", checkable=True)
        self._b_catalogo.toggled.connect(self._toggle_catalog)
        self._b_undo = button("Desfazer", "small", tooltip="Ctrl+Z",
                              on_click=self.undo)
        self._b_redo = button("Refazer", "small", tooltip="Ctrl+Shift+Z",
                              on_click=self.redo)
        tl.addWidget(row(self._b_catalogo, stretch(), self._b_undo, self._b_redo,
                         spacing="3"))
        lay.addWidget(topo)
        lay.addWidget(hline())

        self._catalogo = self._build_catalog()
        self._catalogo.hide()
        lay.addWidget(self._catalogo)

        self.lista = StepList()
        self.lista.step_selected.connect(self.select_step)
        self.lista.reordered.connect(self._on_reordered)
        lay.addWidget(self.lista, 1)

        rodape = label("Arraste para reordenar. A ordem das etapas é a ordem "
                       "física do processo.", "hint", wrap=True)
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
        for tipo in STEP_TYPES:
            b = button("", "small", on_click=lambda _c=False, t=tipo: self.add_step(t))
            b.setText(f"{STEP_LABELS[tipo]}   ·   {tipo}")
            b.setToolTip(STEP_DESCRIPTIONS[tipo])
            b.setProperty("variant", "link")
            b.setFont(theme.font("sans", "base"))
            b.setMinimumHeight(theme.space("14"))
            lay.addWidget(b)
        nota = label(
            "PLOT não está no catálogo: a biblioteca gráfica desta compilação do "
            "SUPREM-III é um conjunto de stubs vazios e o comando é removido do "
            "deck antes de executar. Os gráficos são gerados pelo MOS-Studio a "
            "partir das tabelas de saída.", "hint", wrap=True)
        nota.setContentsMargins(theme.space("5"), theme.space("4"),
                                theme.space("5"), theme.space("2"))
        lay.addWidget(nota)
        return host

    def _toggle_catalog(self, aberto: bool) -> None:
        """Mostra ou esconde o catálogo de tipos de etapa."""
        self._catalogo.setVisible(aberto)

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
        self._banner_itens_lay = QVBoxLayout(self._banner_itens)
        self._banner_itens_lay.setContentsMargins(0, 0, 0, 0)
        self._banner_itens_lay.setSpacing(theme.space("2"))
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

    # ── estado da receita ─────────────────────────────────────────────────

    def _snapshot(self) -> tuple:
        return (self.title,
                tuple((s.type, tuple(sorted(s.params.items())), s.uid)
                      for s in self.steps),
                self._selected)

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        del self._undo[:-60]
        self._redo.clear()

    def _restore(self, snap: tuple) -> None:
        titulo, etapas, selecionado = snap
        self.title = titulo
        self.steps = [Step(t, dict(p), uid) for t, p, uid in etapas]
        self._selected = selecionado
        self._titulo.setText(titulo)
        self.refresh()

    def undo(self) -> None:
        """Desfaz a última alteração da receita."""
        if not self._undo:
            return
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())

    def redo(self) -> None:
        """Refaz a alteração desfeita."""
        if not self._redo:
            return
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())

    # ── edição ────────────────────────────────────────────────────────────

    def _index_of(self, uid: int | None) -> int:
        return next((i for i, s in enumerate(self.steps) if s.uid == uid), -1)

    @property
    def selected_step(self) -> Step | None:
        i = self._index_of(self._selected)
        return self.steps[i] if i >= 0 else None

    def select_step(self, uid: int) -> None:
        """Escolhe a etapa a editar."""
        if uid == self._selected:
            return
        self._selected = uid
        self.refresh()

    def add_step(self, step_type: str) -> None:
        """Insere uma etapa depois da escolhida."""
        self._push_undo()
        nova = Step.new(step_type)
        pos = self._index_of(self._selected)
        self.steps.insert(pos + 1 if pos >= 0 else len(self.steps), nova)
        self._selected = nova.uid
        self._b_catalogo.setChecked(False)
        self.refresh()

    def duplicate_selected(self) -> None:
        atual = self.selected_step
        if atual is None:
            return
        self._push_undo()
        copia = atual.copy()
        self.steps.insert(self._index_of(atual.uid) + 1, copia)
        self._selected = copia.uid
        self.refresh()

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

    def move_selected(self, direction: int) -> None:
        i = self._index_of(self._selected)
        j = i + direction
        if i < 0 or not (0 <= j < len(self.steps)):
            return
        self._push_undo()
        self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
        self.refresh()

    def _on_reordered(self, origem: int, destino: int) -> None:
        if not (0 <= origem < len(self.steps)):
            return
        self._undo.append(self._snapshot())
        del self._undo[:-60]
        self._redo.clear()
        etapa = self.steps.pop(origem)
        self.steps.insert(max(0, min(destino, len(self.steps))), etapa)
        self._selected = etapa.uid
        self.refresh()

    def _on_param_changed(self, uid: int, key: str, value) -> None:
        i = self._index_of(uid)
        if i < 0:
            return
        if self.steps[i].params.get(key) == value:
            return
        # Agrupa digitação: só empilha um estado por campo visitado.
        if not self._undo or self._undo[-1][1] != self._snapshot()[1]:
            self._push_undo()
        self.steps[i].params[key] = value
        anterior = {f.key for f in self.steps[i].fields()}
        self.form.refresh_problems()
        if {f.key for f in self.steps[i].fields()} != anterior:
            self.refresh()          # o campo mudou a visibilidade de outro
        else:
            self._refresh_light()

    def _on_title_edited(self, text: str) -> None:
        self.title = text
        self._refresh_light()

    # ── deck ──────────────────────────────────────────────────────────────

    def deck_lines(self) -> list[tuple[str, int | None]]:
        """Linhas do deck com a etapa de origem de cada uma."""
        return deck_mod.annotated_lines(
            self.title, [dict(s.as_dict(), uid=s.uid) for s in self.steps])

    def deck_text(self) -> str:
        """O deck a enviar ao motor (o editado à mão tem precedência)."""
        if self.deck.editing:
            return self.deck.text()
        return deck_mod.build_in_file(self.title,
                                      [s.as_dict() for s in self.steps])

    @property
    def manual_deck(self) -> bool:
        return self.deck.editing

    def _start_manual_edit(self) -> None:
        self.deck.set_manual(self.deck_text().replace("\r\n", "\n"))
        self.recipe_changed.emit()

    def _discard_manual_edit(self) -> None:
        # Sair do modo manual é explícito: `refresh` só regenera o deck quando
        # ele *não* está em edição, então quem descarta precisa devolvê-lo ao
        # modo gerado antes de redesenhar.
        self.deck.set_generated(self.deck_lines(), self._deck_filename())
        self.refresh()
        self.recipe_changed.emit()

    def hide_deck(self) -> None:
        """Esconde a coluna do deck."""
        self.deck.hide()

    def show_deck(self) -> None:
        self.deck.show()

    def toggle_deck(self) -> None:
        self.deck.setVisible(not self.deck.isVisible())

    # ── problemas ─────────────────────────────────────────────────────────

    def issues(self) -> list[Issue]:
        """Problemas que impedem rodar a receita."""
        if self.deck.editing:
            return []       # deck literal: o motor é quem julga
        return validate(self.steps)

    def focus_first_issue(self) -> None:
        """Seleciona a etapa do primeiro problema."""
        problemas = self.issues()
        if problemas and 0 <= problemas[0].index < len(self.steps):
            self.select_step(self.steps[problemas[0].index].uid)

    # ── execução ──────────────────────────────────────────────────────────

    def set_progress(self, running_index: int, done_before: int = -1) -> None:
        """Marca a etapa em curso na lista (``-1`` apaga as marcas)."""
        self._running_index = running_index
        self._done_before = done_before
        self._refresh_list()

    # ── redesenho ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Redesenha tudo: lista, formulário, deck e banner."""
        if self._selected is None and self.steps:
            self._selected = self.steps[0].uid
        self._refresh_list()
        i = self._index_of(self._selected)
        self.form.show_step(self.steps[i] if i >= 0 else None,
                            i + 1, len(self.steps))
        if not self.deck.editing:
            self.deck.set_generated(self.deck_lines(), self._deck_filename())
            self.deck.highlight_step(self._selected)
        self._refresh_banner()
        self._b_undo.setEnabled(bool(self._undo))
        self._b_redo.setEnabled(bool(self._redo))
        self.recipe_changed.emit()

    def _refresh_light(self) -> None:
        """Redesenho barato: lista, deck e banner, sem recriar o formulário."""
        self._refresh_list()
        if not self.deck.editing:
            self.deck.set_generated(self.deck_lines(), self._deck_filename())
            self.deck.highlight_step(self._selected)
        self._refresh_banner()
        self._b_undo.setEnabled(bool(self._undo))
        self._b_redo.setEnabled(bool(self._redo))
        self.recipe_changed.emit()

    def _refresh_list(self) -> None:
        indices = {p.index for p in self.issues() if p.index >= 0}
        self.lista.populate(self.steps, selected_uid=self._selected,
                            issues=indices, running_index=self._running_index,
                            done_before=self._done_before)
        self._contagem.setText(
            "1 etapa" if len(self.steps) == 1 else f"{len(self.steps)} etapas")

    def _refresh_banner(self) -> None:
        problemas = self.issues()
        while self._banner_itens_lay.count():
            item = self._banner_itens_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        if not problemas:
            self._banner.hide()
            return
        self._banner_titulo.setText(
            "1 problema impede a simulação" if len(problemas) == 1
            else f"{len(problemas)} problemas impedem a simulação")
        for p in problemas:
            prefixo = (f"Etapa {p.index + 1:02d} · " if p.index >= 0 else "")
            b = button(f"→  {prefixo}{p.message}", "link")
            b.setFont(theme.font("sans", "base"))
            if 0 <= p.index < len(self.steps):
                uid = self.steps[p.index].uid
                b.clicked.connect(lambda _c=False, u=uid: self.select_step(u))
            self._banner_itens_lay.addWidget(b)
        self._banner.show()

    def _deck_filename(self) -> str:
        base = "".join(ch for ch in self.title.split("-")[0].strip()
                       if ch.isalnum())[:8].upper()
        return f"{base or 'DECK'}.IN"
