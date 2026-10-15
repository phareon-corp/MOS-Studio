"""Tela de Malha: as linhas do SUPREM-IV e o que elas custam.

No SUPREM-III a malha era implícita — o usuário dava ``DX`` e ``THICKNES`` e o
motor resolvia. No SUPREM-IV a malha é decisão do projeto: cada cartão
``line`` fixa uma posição e o espaçamento *naquele ponto*, e o motor subdivide
o que fica entre duas linhas por progressão geométrica.

Por isso esta tela existe, e por isso ela mostra a contagem de nós antes de
rodar: a diferença entre 0,02 e 0,002 µm de espaçamento na superfície é a
diferença entre doze segundos e vinte minutos de espera.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLineEdit,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ...core import mesh as mesh_mod
from .. import theme
from ..widgets.common import (button, eyebrow, hline, label, row, stretch,
                              column)
from ..widgets.mesh_view import MeshView

#: Rótulo e explicação de cada eixo. ``y`` cresce para dentro da lâmina, que é
#: a convenção dos exemplos de fábrica.
AXES = (("x", "Direção x (lateral)",
         "A largura da seção. A borda esquerda é plano de simetria: só metade "
         "do dispositivo é simulada."),
        ("y", "Direção y (profundidade)",
         "Da superfície para dentro. O refino aqui define a resolução do "
         "perfil de dopagem."))


class _AxisTable(QWidget):
    """A tabela editável de um eixo."""

    changed = Signal()

    def __init__(self, axis: str, title: str, hint: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.axis = axis
        self._lines: list[mesh_mod.Line] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, theme.space("6"))
        lay.setSpacing(theme.space("4"))

        self._contagem = label("—", "mono")
        lay.addWidget(row(label(title), stretch(), self._contagem))
        lay.addWidget(label(hint, "hint", wrap=True))

        cabecalho = QWidget()
        cl = QHBoxLayout(cabecalho)
        cl.setContentsMargins(theme.space("6"), 0, theme.space("6"), 0)
        cl.setSpacing(theme.space("4"))
        cl.addWidget(label("", "hint"), 0)
        cl.addWidget(label("loc (µm)", "hint"), 1)
        cl.addWidget(label("spacing (µm)", "hint"), 1)
        cl.addSpacing(theme.space("12"))
        lay.addWidget(cabecalho)

        self._corpo = QWidget()
        self._grade = QGridLayout(self._corpo)
        self._grade.setContentsMargins(0, 0, 0, 0)
        self._grade.setSpacing(theme.space("3"))
        lay.addWidget(self._corpo)

        self._b_add = button(f"+  line {axis}", "small",
                             on_click=self._add_line)
        lay.addWidget(row(self._b_add, stretch()))

    # ── dados ─────────────────────────────────────────────────────────────

    def set_lines(self, linhas: list[mesh_mod.Line], node_count: int) -> None:
        self._lines = linhas
        self._contagem.setText(f"{node_count} linhas" if node_count else "—")
        self._rebuild()

    def lines(self) -> list[mesh_mod.Line]:
        return self._lines

    def _rebuild(self) -> None:
        while self._grade.count():
            item = self._grade.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()
        for i, ln in enumerate(self._lines):
            num = label(f"{i + 1:02d}", "mono")
            num.setFixedWidth(theme.space("12"))
            loc = QLineEdit(f"{ln.loc:g}")
            spac = QLineEdit(f"{ln.spacing:g}")
            for campo in (loc, spac):
                campo.setFont(theme.font("mono", "small", spacing="normal"))
                theme.mark(campo, role="mono")
            loc.editingFinished.connect(
                lambda c=loc, j=i: self._edit(j, "loc", c.text()))
            spac.editingFinished.connect(
                lambda c=spac, j=i: self._edit(j, "spacing", c.text()))
            remover = button("×", "icon",
                             tooltip="Remover esta linha",
                             on_click=lambda _c=False, j=i: self._remove(j))
            # Duas linhas é o mínimo para o eixo ter extensão.
            remover.setEnabled(len(self._lines) > 2)
            self._grade.addWidget(num, i, 0)
            self._grade.addWidget(loc, i, 1)
            self._grade.addWidget(spac, i, 2)
            self._grade.addWidget(remover, i, 3)
        self._grade.setColumnStretch(1, 1)
        self._grade.setColumnStretch(2, 1)

    # ── edição ────────────────────────────────────────────────────────────

    def _edit(self, index: int, campo: str, texto: str) -> None:
        try:
            valor = float(texto.replace(",", "."))
        except ValueError:
            self._rebuild()          # devolve o valor anterior ao campo
            return
        if index >= len(self._lines):
            return
        ln = self._lines[index]
        if campo == "loc":
            if abs(valor - ln.loc) < 1e-12:
                return
            ln.loc = valor
        else:
            if abs(valor - ln.spacing) < 1e-12:
                return
            ln.spacing = valor
        self.changed.emit()

    def _add_line(self) -> None:
        """Acrescenta uma linha meio micron depois da última."""
        ultima = self._lines[-1] if self._lines else mesh_mod.Line(0.0, 0.1)
        self._lines.append(mesh_mod.Line(round(ultima.loc + 0.5, 4),
                                         ultima.spacing))
        self.changed.emit()

    def _remove(self, index: int) -> None:
        if len(self._lines) <= 2 or index >= len(self._lines):
            return
        del self._lines[index]
        self.changed.emit()


class MeshScreen(QWidget):
    """A tela inteira de Malha."""

    mesh_changed = Signal()
    #: Resultado da conferência contra o motor: ``(nós, mensagem)``.
    checked = Signal(int, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mesh = mesh_mod.default_mesh()

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(divisor)

        divisor.addWidget(self._build_editor())
        divisor.addWidget(self._build_preview())
        divisor.setSizes([theme.dimension("sidebar-width") + theme.space("20"),
                          760])
        divisor.setStretchFactor(1, 1)
        self.refresh()

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_editor(self) -> QWidget:
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setMinimumWidth(theme.dimension("sidebar-width"))
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("10"), theme.space("10"),
                               theme.space("10"), theme.space("10"))
        lay.setSpacing(theme.space("7"))

        lay.addWidget(eyebrow("suprem-iv · malha 2-d", accent=True))
        titulo = label("Linhas da malha", "title")
        lay.addWidget(titulo)
        lay.addWidget(label(
            "Cada cartão line fixa uma posição e o espaçamento local. Entre "
            "duas linhas o motor subdivide por progressão geométrica, com "
            "razão limitada a 1,5 — por isso a contagem de nós nem sempre é "
            "a que a divisão simples sugeriria.", "hint", wrap=True))

        self._tabelas: dict[str, _AxisTable] = {}
        for eixo, titulo_eixo, dica in AXES:
            t = _AxisTable(eixo, titulo_eixo, dica)
            t.changed.connect(self._on_edited)
            self._tabelas[eixo] = t
            lay.addWidget(t)
            lay.addWidget(hline())

        self._erro = label("", "hint", wrap=True)
        theme.mark(self._erro, role="error")
        self._erro.hide()
        lay.addWidget(self._erro)

        lay.addWidget(eyebrow("regiões e contornos"))
        lay.addWidget(label(
            "A interface gera estes cartões junto com as linhas; as tags das "
            "bordas são fixas para o region e o boundary não poderem "
            "discordar da malha.", "hint", wrap=True))
        self._cartoes = label("", "mono", wrap=True)
        theme.mark(self._cartoes, surface="code")
        self._cartoes.setContentsMargins(theme.space("6"), theme.space("5"),
                                         theme.space("6"), theme.space("5"))
        lay.addWidget(self._cartoes)

        lay.addWidget(row(button("Restaurar a malha padrão", "small",
                                 tooltip="Os valores do exam5, o transistor "
                                         "LDD do manual",
                                 on_click=self.reset), stretch()))
        lay.addStretch(1)
        rolagem.setWidget(host)
        return rolagem

    def _build_preview(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("10"), theme.space("10"),
                               theme.space("10"), theme.space("10"))
        lay.setSpacing(theme.space("7"))

        self._stats: dict[str, object] = {}
        faixa = QWidget()
        fl = QHBoxLayout(faixa)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(theme.space("12"))
        for chave, rotulo in (("nodes", "nós"), ("triangles", "triângulos"),
                              ("spacing", "menor passo"),
                              ("time", "tempo estimado")):
            valor = label("—", "title")
            self._stats[chave] = valor
            fl.addWidget(column(eyebrow(rotulo), valor, spacing="2"))
        fl.addStretch(1)
        self._b_tri = button("Triângulos", "small", checkable=True)
        self._b_tri.setChecked(True)
        self._b_tri.setToolTip("Mostra a diagonal de cada célula")
        self._b_tri.toggled.connect(
            lambda on: self.view.set_show_triangles(on))
        fl.addWidget(self._b_tri)
        lay.addWidget(faixa)

        self.view = MeshView()
        lay.addWidget(self.view, 1)

        self._aviso = label("", "error", wrap=True)
        self._aviso.hide()
        lay.addWidget(self._aviso)

        self._conferido = label("", "hint", wrap=True)
        self._conferido.hide()
        lay.addWidget(self._conferido)
        lay.addWidget(label(
            "As linhas em laranja são as que você pediu; as finas são as que "
            "o motor cria entre elas. O tempo é uma estimativa grosseira "
            "medida nesta máquina, não uma promessa.", "hint", wrap=True))
        return host

    # ── estado ────────────────────────────────────────────────────────────

    def mesh(self) -> mesh_mod.Mesh:
        return self._mesh

    def set_mesh(self, malha: mesh_mod.Mesh) -> None:
        self._mesh = malha
        self.refresh()

    def reset(self) -> None:
        self._mesh = mesh_mod.default_mesh()
        self.refresh()
        self.mesh_changed.emit()

    def cards(self) -> list[str]:
        return mesh_mod.to_cards(self._mesh)

    def stats(self) -> mesh_mod.MeshStats:
        return mesh_mod.stats(self._mesh)

    def check_with_engine(self) -> tuple[int, str]:
        """Pede ao motor que gere esta malha e compara com a previsão.

        É barato (o deck não tem etapa de processo) e é a única prova de que
        a pré-visualização concorda com o motor.
        """
        previsto = mesh_mod.stats(self._mesh)
        if not previsto.ok:
            self._show_check(0, previsto.error)
            return (0, previsto.error)
        nos, erro = mesh_mod.engine_check(self._mesh)
        self._show_check(nos, erro, previsto.nodes)
        self.checked.emit(nos, erro)
        return (nos, erro)

    def _show_check(self, nos: int, erro: str, previsto: int = 0) -> None:
        if erro or not nos:
            texto = erro or "O motor não gerou a malha."
        elif nos == previsto:
            texto = (f"O motor gerou {nos} nós — exatamente o que a "
                     "pré-visualização mostra.")
        else:
            texto = (f"O motor gerou {nos} nós, e a pré-visualização previa "
                     f"{previsto}. Vale conferir o cálculo da malha.")
        self._conferido.setText(texto)
        self._conferido.show()

    def _warning(self, s: mesh_mod.MeshStats) -> str:
        """O que avisar sobre o tamanho desta malha.

        Três faixas, todas medidas nesta máquina com o transistor LDD: a
        partir de ~3.000 nós o resultado já não muda; acima de ~5.000 a espera
        começa a incomodar; e acima de ~9.000 o motor **cai**, com falha de
        segmentação e sem mensagem — a execução simplesmente não produz
        resultado.
        """
        if not s.ok:
            return ""
        if s.risky:
            return (f"São {s.nodes} nós. O SUPREM-IV cai acima de cerca de "
                    f"{mesh_mod.MAX_SAFE_NODES} nós — falha de segmentação, "
                    "sem mensagem, e nenhum resultado. Aumente o espaçamento "
                    "antes de rodar.")
        if s.slow:
            extra = ("  Acima de cerca de "
                     f"{mesh_mod.CONVERGED_NODE_COUNT} nós o resultado já "
                     "não muda: refinar além disso só custa tempo."
                     if s.converged else "")
            return (f"São {s.nodes} nós, cerca de "
                    f"{s.estimated_seconds:.0f} s de execução.".replace(".", ",")
                    + extra)
        return ""

    def issues(self) -> list[str]:
        """Problemas que impedem gerar a malha."""
        erro = (mesh_mod.validate_axis(self._mesh.x)
                or mesh_mod.validate_axis(self._mesh.y))
        return [erro] if erro else []

    def _on_edited(self) -> None:
        self._mesh.x = self._tabelas["x"].lines()
        self._mesh.y = self._tabelas["y"].lines()
        self.refresh()
        self.mesh_changed.emit()

    def refresh(self) -> None:
        s = mesh_mod.stats(self._mesh)
        self._tabelas["x"].set_lines(self._mesh.x, len(s.x_positions))
        self._tabelas["y"].set_lines(self._mesh.y, len(s.y_positions))
        self.view.set_mesh(self._mesh)

        if s.ok:
            self._stats["nodes"].setText(f"{s.nodes}")
            self._stats["triangles"].setText(f"{s.triangles}")
            self._stats["spacing"].setText(
                f"{s.min_spacing:.4f}".rstrip("0").replace(".", ","))
            self._stats["time"].setText(
                f"{s.estimated_seconds:.1f}".replace(".", ",") + " s")
        else:
            for w in self._stats.values():
                w.setText("—")

        self._erro.setText(s.error)
        self._erro.setVisible(bool(s.error))
        self._aviso.setText(self._warning(s))
        self._aviso.setVisible(bool(self._aviso.text()))
        self._conferido.hide()
        self._cartoes.setText("\n".join(
            c for c in mesh_mod.to_cards(self._mesh)
            if not c.startswith("line ")) or "—")
