"""Tela de Modelos: os coeficientes físicos que o motor vai usar.

Os valores desta tela não são escolha do MOS-Studio. Vêm, nesta ordem, do
``data/modelrc`` — que o motor lê antes de qualquer deck — e do
``data/suprem.key``, a gramática compilada. A ordem importa: o ``suprem.key``
declara ``interstitial D.0 = 1e-9`` e o ``modelrc`` sobrescreve com
``1.03e6``. Mostrar o primeiro seria mostrar um número que o motor nunca usa.

Só o que for alterado entra no deck. Um projeto que não mexe em nada roda com
o ``modelrc`` da instalação, que é o que se quer quase sempre; e o deck fica
dizendo exatamente qual foi a decisão do projeto, em vez de repetir dezenas
de padrões.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLineEdit,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ...core import models4
from .. import theme
from ..widgets.common import (button, column, eyebrow, hline, label, row,
                              stretch)


class ModelsScreen(QWidget):
    """A tela inteira de Modelos."""

    models_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.models = models4.Models4()
        self._group = models4.GROUPS[0]
        self._choice = self._group.default_choice()
        self._campos: dict[str, QLineEdit] = {}

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(divisor)
        divisor.addWidget(self._build_nav())
        divisor.addWidget(self._build_table())
        divisor.addWidget(self._build_deck())
        divisor.setSizes([theme.space("24") * 5, 720,
                          theme.dimension("deck-min-width")])
        divisor.setStretchFactor(1, 1)
        self.refresh()

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_nav(self) -> QWidget:
        host = QWidget()
        host.setMinimumWidth(theme.space("24") * 4)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("5"), theme.space("9"),
                               theme.space("5"), theme.space("9"))
        lay.setSpacing(theme.space("1"))
        lay.addWidget(eyebrow("modelos físicos"))
        lay.addSpacing(theme.space("4"))
        self._b_grupos: dict[str, object] = {}
        for g in models4.GROUPS:
            cartao = models4.card_name(g, g.default_choice()) or "—"
            b = button("", "nav", checkable=True,
                       on_click=lambda _c=False, k=g.id: self.select_group(k))
            b.setText(f"{g.label}\n{cartao}")
            b.setToolTip(g.desc)
            b.setMinimumHeight(theme.space("16"))
            self._b_grupos[g.id] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self._contagem = label("", "hint", wrap=True)
        lay.addWidget(self._contagem)
        return host

    def _build_table(self) -> QWidget:
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("10"), theme.space("10"),
                               theme.space("10"), theme.space("10"))
        lay.setSpacing(theme.space("8"))

        self._eyebrow = eyebrow("", accent=True)
        self._titulo = label("", "title")
        self._desc = label("", "hint", wrap=True)
        lay.addWidget(column(self._eyebrow, self._titulo, self._desc,
                             spacing="3"))

        self._escolha_host = QWidget()
        el = QVBoxLayout(self._escolha_host)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(theme.space("4"))
        self._escolha_rotulo = label("", "base")
        el.addWidget(self._escolha_rotulo)
        self._escolha_faixa = QWidget()
        self._escolha_lay = QHBoxLayout(self._escolha_faixa)
        self._escolha_lay.setContentsMargins(0, 0, 0, 0)
        self._escolha_lay.setSpacing(theme.space("3"))
        el.addWidget(self._escolha_faixa)
        lay.addWidget(self._escolha_host)

        self._switch_host = QWidget()
        self._switch_lay = QVBoxLayout(self._switch_host)
        self._switch_lay.setContentsMargins(0, 0, 0, 0)
        self._switch_lay.setSpacing(theme.space("6"))
        lay.addWidget(self._switch_host)

        self._toggle_host = QWidget()
        tl = QHBoxLayout(self._toggle_host)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(theme.space("5"))
        self._b_toggle = button("", "segment", checkable=True)
        self._b_toggle.toggled.connect(self._on_toggle)
        tl.addWidget(self._b_toggle)
        self._toggle_nota = label("", "hint", wrap=True)
        tl.addWidget(self._toggle_nota, 1)
        lay.addWidget(self._toggle_host)

        cabecalho = QWidget()
        cl = QHBoxLayout(cabecalho)
        cl.setContentsMargins(0, 0, theme.space("4"), theme.space("3"))
        cl.setSpacing(theme.space("5"))
        for texto, peso in (("parâmetro", 11), ("valor", 10),
                            ("unidade", 6), ("significado", 16)):
            cl.addWidget(eyebrow(texto), peso)
        lay.addWidget(cabecalho)
        lay.addWidget(hline(strong=True))

        self._tabela = QWidget()
        self._grade = QGridLayout(self._tabela)
        self._grade.setContentsMargins(0, theme.space("2"), 0, 0)
        self._grade.setSpacing(theme.space("3"))
        lay.addWidget(self._tabela)

        self._b_reset = button("Restaurar o padrão do motor", "small",
                               on_click=self._reset_group)
        self._alterados = label("", "hint")
        lay.addWidget(row(self._b_reset, self._alterados, stretch()))

        self._nota = label("", "hint", wrap=True)
        lay.addWidget(self._nota)
        lay.addStretch(1)
        rolagem.setWidget(host)
        return rolagem

    def _build_deck(self) -> QWidget:
        host = QWidget()
        theme.mark(host, surface="code")
        host.setMinimumWidth(theme.space("24") * 7)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("8"), theme.space("9"),
                               theme.space("8"), theme.space("9"))
        lay.setSpacing(theme.space("6"))
        lay.addWidget(eyebrow("linhas geradas no deck"))
        self._deck = label("", "mono", wrap=True)
        self._deck.setAlignment(Qt.AlignmentFlag.AlignTop
                                | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._deck, 1)
        lay.addWidget(label(
            "Só o que você alterar entra no deck. O resto vem do arquivo de "
            "coeficientes da instalação (modelrc), que é lido antes de "
            "qualquer cartão.", "hint", wrap=True))
        return host

    # ── estado ────────────────────────────────────────────────────────────

    def select_group(self, gid: str) -> None:
        g = models4.group(gid)
        if g is None:
            return
        self._group = g
        self._choice = g.default_choice()
        self.refresh()

    def set_models(self, modelos: models4.Models4) -> None:
        self.models = modelos
        self.refresh()

    def cards(self) -> list[str]:
        return self.models.cards()

    def _pick_choice(self, chave: str) -> None:
        self._choice = chave
        self.refresh()

    def _reset_group(self) -> None:
        self.models.reset(self._group, self._choice)
        self.refresh()
        self.models_changed.emit()

    def _on_value(self, param: str, texto: str) -> None:
        self.models.set(self._group, self._choice, param, texto)
        self.refresh()
        self.models_changed.emit()

    def _on_switch(self, switch: models4.Switch, opcao: str) -> None:
        self.models.set_switch(self._group, switch, opcao, self._choice)
        self.refresh()
        self.models_changed.emit()

    def _on_toggle(self, estado: bool) -> None:
        if not self._group.toggle:
            return
        if estado == self.models.toggle(self._group, self._choice):
            return
        self.models.set_toggle(self._group, estado, self._choice)
        self.refresh()
        self.models_changed.emit()

    # ── redesenho ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        g, escolha = self._group, self._choice
        for gid, b in self._b_grupos.items():
            b.setChecked(gid == g.id)

        cartao = models4.card_name(g, escolha)
        quals = " ".join(models4.qualifiers(g, escolha))
        self._eyebrow.setText(f"cartão  {cartao} {quals}".upper())
        self._titulo.setText(g.title)
        self._desc.setText(g.desc)

        self._refresh_choices()
        self._refresh_switches()
        self._refresh_toggle()
        self._refresh_rows()

        alterados = self.models.changed(g, escolha)
        self._alterados.setText(
            "nenhum valor alterado nesta aba" if not alterados
            else f"{len(alterados)} alterado"
            + ("" if len(alterados) == 1 else "s"))
        self._b_reset.setEnabled(bool(alterados))
        self._nota.setText(g.note)
        self._nota.setVisible(bool(g.note))

        total = self.models.count()
        self._contagem.setText(
            "Nenhum modelo alterado: o projeto roda com o modelrc da "
            "instalação." if not total
            else f"{total} parâmetro{'s' if total > 1 else ''} alterado"
                 f"{'s' if total > 1 else ''} no projeto.")
        self._deck.setText("\n".join(self.models.cards()) or "—")

    def _refresh_choices(self) -> None:
        while self._escolha_lay.count():
            item = self._escolha_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        g = self._group
        if not g.choices:
            self._escolha_host.hide()
            return
        self._escolha_host.show()
        self._escolha_rotulo.setText(g.choice_label)
        for op in g.choices:
            b = button(op.label, "segment", checkable=True)
            b.setChecked(op.id == self._choice)
            b.clicked.connect(lambda _c=False, k=op.id: self._pick_choice(k))
            self._escolha_lay.addWidget(b)
        self._escolha_lay.addStretch(1)

    def _refresh_switches(self) -> None:
        while self._switch_lay.count():
            item = self._switch_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        g = self._group
        if not g.switches:
            self._switch_host.hide()
            return
        self._switch_host.show()
        for sw in g.switches:
            ativo = self.models.switch(g, sw, self._choice)
            padrao = models4.engine_switch(g, sw, self._choice)
            faixa = QWidget()
            fl = QHBoxLayout(faixa)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(theme.space("3"))
            for op in sw.options:
                b = button(op.label, "segment", checkable=True)
                b.setChecked(op.id == ativo)
                if op.id == padrao:
                    b.setToolTip("É o que o motor liga sozinho")
                b.clicked.connect(
                    lambda _c=False, s=sw, k=op.id: self._on_switch(s, k))
                fl.addWidget(b)
            fl.addStretch(1)
            self._switch_lay.addWidget(
                column(label(sw.label), faixa,
                       label(sw.note, "hint", wrap=True), spacing="3"))

    def _refresh_toggle(self) -> None:
        g = self._group
        if not g.toggle:
            self._toggle_host.hide()
            return
        self._toggle_host.show()
        self._b_toggle.setText(g.toggle_label or g.toggle)
        self._b_toggle.blockSignals(True)
        self._b_toggle.setChecked(self.models.toggle(g, self._choice))
        self._b_toggle.blockSignals(False)
        self._toggle_nota.setText(g.toggle_note)

    def _refresh_rows(self) -> None:
        while self._grade.count():
            item = self._grade.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        self._campos.clear()
        linhas = models4.rows(self._group, self._choice, self.models.overrides)
        if not linhas:
            self._grade.addWidget(
                label("Este cartão não tem parâmetro editável para esta "
                      "escolha.", "hint", wrap=True), 0, 0, 1, 4)
            return
        for i, r in enumerate(linhas):
            nome = label(r.name, "mono")
            nome.setToolTip(f"padrão do motor: {r.default}  ({r.source})")
            campo = QLineEdit(r.value)
            campo.setFont(theme.font("mono", "small", spacing="normal"))
            theme.mark(campo, role="mono")
            if r.changed:
                theme.mark(campo, state="changed")
            campo.editingFinished.connect(
                lambda c=campo, k=r.name: self._on_value(k, c.text()))
            self._campos[r.name] = campo
            self._grade.addWidget(nome, i, 0)
            self._grade.addWidget(campo, i, 1)
            self._grade.addWidget(label(r.unit, "hint"), i, 2)
            self._grade.addWidget(label(r.meaning, "hint", wrap=True), i, 3)
        self._grade.setColumnStretch(0, 11)
        self._grade.setColumnStretch(1, 10)
        self._grade.setColumnStretch(2, 6)
        self._grade.setColumnStretch(3, 16)
