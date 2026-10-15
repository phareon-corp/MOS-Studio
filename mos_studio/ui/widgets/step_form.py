"""Formulário de uma etapa: um campo por parâmetro, com rótulo e unidade.

É aqui que a interface deixa de falar o dialeto do SUPREM. O rótulo é o nome
em português do parâmetro, a unidade fica ao lado do campo, a faixa aceita
aparece abaixo, e o nome original (``TEMPERAT``, ``GAS.CONC``) fica à direita
em monospace para quem for ler o deck depois.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QSizePolicy, QVBoxLayout, QWidget)

from ...core.recipe import Field, Step, check_field, range_hint
from .. import theme
from .common import button, label, row


class FieldRow(QWidget):
    """Um parâmetro editável."""

    changed = Signal(str, object)      # chave, valor

    def __init__(self, field: Field, value, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field = field
        self._editor: QWidget | None = None
        self._hint: QLabel | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space("4"))

        cabeca = QWidget()
        hl = QHBoxLayout(cabeca)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(theme.space("4"))
        titulo = QLabel(field.label)
        titulo.setFont(theme.font("sans", "base", "medium"))
        hl.addWidget(titulo)
        hl.addStretch(1)
        chave = label(field.key, "mono")
        chave.setFont(theme.font("mono", "micro", "regular", "wide"))
        theme.mark(chave, role="eyebrow")
        hl.addWidget(chave)
        lay.addWidget(cabeca)

        if field.kind == "choice":
            from .common import Segmented
            seg = Segmented(list(field.choices), str(value or ""))
            seg.changed.connect(lambda _i: self.changed.emit(field.key, seg.value()))
            self._editor = seg
            lay.addWidget(seg)
        elif field.kind == "bool":
            caixa = QCheckBox(field.help or "sim")
            caixa.setChecked(bool(value))
            caixa.toggled.connect(lambda v: self.changed.emit(field.key, bool(v)))
            self._editor = caixa
            lay.addWidget(caixa)
        else:
            caixa = QWidget()
            hb = QHBoxLayout(caixa)
            hb.setContentsMargins(0, 0, 0, 0)
            hb.setSpacing(theme.space("4"))
            edit = QLineEdit("" if value is None else str(value))
            edit.setFont(theme.font("mono", "body"))
            theme.mark(edit, role="mono")
            edit.setFixedHeight(theme.dimension("field-height"))
            edit.textEdited.connect(lambda t: self.changed.emit(field.key, t))
            hb.addWidget(edit, 1)
            if field.unit:
                hb.addWidget(label(field.unit, "unit"))
            self._editor = edit
            lay.addWidget(caixa)

        dica = range_hint(field)
        if dica or field.kind == "number":
            self._hint = label(dica, "hint", wrap=True)
            lay.addWidget(self._hint)

    def set_problem(self, message: str) -> None:
        """Marca (ou desmarca, com mensagem vazia) o problema do campo."""
        if isinstance(self._editor, QLineEdit):
            self._editor.setProperty("state", "invalid" if message else "")
            theme.restyle(self._editor)
        if self._hint is not None:
            if message:
                self._hint.setText(message)
                theme.mark(self._hint, role="error")
            else:
                self._hint.setText(range_hint(self.field))
                theme.mark(self._hint, role="hint")
            theme.restyle(self._hint)


class StepForm(QWidget):
    """Formulário completo de uma etapa, com as ações de reordenar e remover."""

    param_changed = Signal(int, str, object)   # uid, chave, valor
    move_requested = Signal(int)               # -1 acima, +1 abaixo
    duplicate_requested = Signal()
    remove_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._step: Step | None = None
        self._rows: dict[str, FieldRow] = {}

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(theme.space("16"), theme.space("14"),
                                      theme.space("16"), theme.space("20"))
        self._root.setSpacing(theme.space("13"))

        self._eyebrow = label("", "eyebrow")
        self._title = label("", "title")
        self._desc = label("", "dim", wrap=True)
        self._desc.setMaximumWidth(theme.dimension("detail-max-width"))

        cabeca = QWidget()
        hl = QHBoxLayout(cabeca)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(theme.space("8"))
        texto = QWidget()
        vl = QVBoxLayout(texto)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(theme.space("3"))
        vl.addWidget(self._eyebrow)
        vl.addWidget(self._title)
        vl.addWidget(self._desc)
        hl.addWidget(texto, 1)

        self._acoes = row(
            button("↑", "icon", tooltip="Mover para cima",
                   on_click=lambda: self.move_requested.emit(-1)),
            button("↓", "icon", tooltip="Mover para baixo",
                   on_click=lambda: self.move_requested.emit(1)),
            button("Duplicar", "danger",
                   on_click=lambda: self.duplicate_requested.emit()),
            button("Remover", "danger",
                   on_click=lambda: self.remove_requested.emit()),
            spacing="3")
        self._acoes.setSizePolicy(QSizePolicy.Policy.Fixed,
                                  QSizePolicy.Policy.Fixed)
        hl.addWidget(self._acoes, 0, Qt.AlignmentFlag.AlignTop)
        self._root.addWidget(cabeca)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(theme.space("12"))
        self._grid.setVerticalSpacing(theme.space("11"))
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._root.addWidget(self._grid_host)
        self._root.addStretch(1)

        self._vazio = label("Receita vazia. Adicione uma Inicialização para começar.",
                            "dim")
        self._root.addWidget(self._vazio)
        self._vazio.hide()

    # ── conteúdo ──────────────────────────────────────────────────────────

    def show_step(self, step: Step | None, position: int = 0, total: int = 0) -> None:
        """Mostra uma etapa (ou o estado vazio, com ``None``)."""
        self._step = step
        self._clear_grid()
        if step is None:
            self._eyebrow.hide()
            self._title.hide()
            self._desc.hide()
            self._acoes.hide()
            self._vazio.show()
            return
        self._vazio.hide()
        for w in (self._eyebrow, self._title, self._desc, self._acoes):
            w.show()
        self._eyebrow.setText(
            f"ETAPA {position:02d} DE {total:02d} · {step.type}")
        self._title.setText(step.label)
        self._desc.setText(step.description)

        linha = 0
        coluna = 0
        for field in step.fields():
            fr = FieldRow(field, step.params.get(field.key, ""))
            fr.changed.connect(
                lambda key, value, uid=step.uid:
                self.param_changed.emit(uid, key, value))
            self._rows[field.key] = fr
            if field.wide:
                if coluna != 0:
                    linha += 1
                    coluna = 0
                self._grid.addWidget(fr, linha, 0, 1, 2)
                linha += 1
            else:
                self._grid.addWidget(fr, linha, coluna)
                coluna += 1
                if coluna == 2:
                    coluna = 0
                    linha += 1
        self.refresh_problems()

    def refresh_problems(self) -> None:
        """Repinta as marcas de problema a partir dos valores atuais."""
        if self._step is None:
            return
        for key, fr in self._rows.items():
            issue = check_field(self._step, fr.field)
            fr.set_problem(issue.message if issue is not None else "")

    def _clear_grid(self) -> None:
        self._rows.clear()
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
