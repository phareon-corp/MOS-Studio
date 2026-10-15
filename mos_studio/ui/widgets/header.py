"""Cabeçalho do aplicativo: marca, projeto, dimensão, navegação e execução.

A navegação depende da dimensão do projeto, porque os dois motores não têm as
mesmas telas. Em 1-D (SUPREM-III) a malha é implícita — o usuário dá ``DX`` e
``THICKNES`` e o motor resolve — e existe a ponte para o MINIMOS, que é 1-D.
Em 2-D (SUPREM-IV) a malha é do usuário e passa a ser uma tela inteira, há
modelos físicos para ajustar, e o motor é um shell com que dá para conversar.

Daí as duas navegações:

* **1-D:** Processo · Resultados · Dispositivo, com Oxidação e Exemplos nas
  ferramentas;
* **2-D:** Malha · Processo · Resultados · Modelos, com Console, Estruturas e
  Exemplos.

Trocar de dimensão mantém a tela quando ela existe na outra — quem está em
Resultados 1-D cai em Resultados 2-D — e, quando não existe, cai no Processo
da dimensão escolhida.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QHBoxLayout, QSizePolicy,
                               QStackedWidget, QWidget)

from ...core import engines
from ..run_controller import format_elapsed
from .. import theme
from .common import PulseDot, Segmented, button, eyebrow, label, row, vline

#: ``(chave, número, rótulo)`` de cada área, por dimensão.
AREAS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "1d": (("processo", "01", "Processo"),
           ("resultados", "02", "Resultados"),
           ("dispositivo", "03", "Dispositivo")),
    "2d": (("malha", "01", "Malha"),
           ("processo2d", "02", "Processo"),
           ("resultados2d", "03", "Resultados"),
           ("modelos", "04", "Modelos")),
}

#: ``(chave, rótulo)`` das ferramentas, por dimensão.
TOOLS: dict[str, tuple[tuple[str, str], ...]] = {
    "1d": (("oxidacao", "Oxidação"), ("exemplos", "Exemplos")),
    "2d": (("console", "Console"), ("estrutura", "Estruturas"),
           ("exemplos", "Exemplos")),
}

#: Área que recebe o usuário quando a atual não existe na outra dimensão.
HOME_AREA = {"1d": "processo", "2d": "processo2d"}

#: Telas equivalentes entre as dimensões, para a troca não perder o lugar.
EQUIVALENT = {
    ("1d", "2d"): {"processo": "processo2d", "resultados": "resultados2d"},
    ("2d", "1d"): {"processo2d": "processo", "resultados2d": "resultados",
                   "malha": "processo", "modelos": "processo"},
}

#: Rótulo do botão de execução, por área. O que o botão faz muda com a tela:
#: na Oxidação é uma varredura, no Dispositivo é o MINIMOS.
RUN_LABELS = {
    "dispositivo": "Simular dispositivo",
    "oxidacao": "Rodar análise",
    "malha": "Gerar malha",
    "modelos": "Simular com estes modelos",
    "console": "Enviar a receita",
}
# Estruturas e Exemplos não entram: o que há para fazer ali está nos próprios
# cartões da tela, e o botão do cabeçalho fica desligado. Um rótulo como
# "Rodar exemplo" num botão apagado prometeria o que ele não faz.

#: Rótulo curto do botão de execução, para quando o cabeçalho aperta. O
#: tooltip guarda o nome inteiro.
RUN_LABELS_SHORT = {
    "dispositivo": "Dispositivo",
    "oxidacao": "Análise",
    "malha": "Malha",
    "modelos": "Simular",
    "console": "Enviar",
}

#: Dimensão de cada motor, para a pílula nomear o que vai rodar.
DIMS = (("1d", "1-D"), ("2d", "2-D"))


def engine_for(dim: str) -> str:
    """Identificador do motor daquela dimensão, em :mod:`core.engines`."""
    return engines.SUPREM4 if dim == "2d" else engines.SUPREM3


def area_for(dim: str, current: str) -> str:
    """Tela que deve ficar ativa depois de trocar para ``dim``."""
    if current in {k for k, _, _ in AREAS[dim]} | {k for k, _ in TOOLS[dim]}:
        return current
    outra = "2d" if dim == "1d" else "1d"
    return EQUIVALENT.get((outra, dim), {}).get(current, HOME_AREA[dim])


class AccentDot(QWidget):
    """O ponto laranja da marca."""

    def __init__(self, size: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(theme.qcolor("accent"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, self._size, self._size)
        p.end()


class Header(QWidget):
    """O cabeçalho. Emite a área escolhida, a dimensão e as ações de execução."""

    area_changed = Signal(str)
    dimension_changed = Signal(str)           # "1d" ou "2d"
    project_menu_requested = Signal(object)   # posição global do clique
    run_requested = Signal()
    cancel_requested = Signal()
    issues_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(theme.dimension("header-height"))
        self._buttons: dict[str, object] = {}
        self._dim = "1d"
        self._area = "processo"
        #: Nível de compactação da navegação (ver :meth:`_apply_compact`).
        self._compact = 0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.space("10"), 0, theme.space("10"), 0)
        lay.setSpacing(theme.space("9"))

        # a marca é o caminho de volta ao Início, como no design
        self._marca = button("MOS-Studio", "link",
                             tooltip="Voltar ao Início",
                             on_click=lambda: self.area_changed.emit("inicio"))
        self._marca.setFont(theme.font("display", "lead", "medium", "tight"))
        self._marca.setSizePolicy(QSizePolicy.Policy.Fixed,
                                  QSizePolicy.Policy.Fixed)
        self._esquerda = row(AccentDot(), self._marca, spacing="5")
        lay.addWidget(self._esquerda)

        self._projeto = button("", "small",
                               tooltip="Projeto aberto — clique para abrir, "
                                       "salvar ou começar outro")
        self._projeto.clicked.connect(
            lambda: self.project_menu_requested.emit(
                self._projeto.mapToGlobal(self._projeto.rect().bottomLeft())))
        self._projeto.setMaximumWidth(theme.space("24") * 6)
        self._projeto.setSizePolicy(QSizePolicy.Policy.Maximum,
                                    QSizePolicy.Policy.Fixed)
        lay.addWidget(self._projeto)

        # ── a pílula de dimensão ──
        self._dims = Segmented(list(DIMS), "1d")
        self._dims.setSizePolicy(QSizePolicy.Policy.Fixed,
                                 QSizePolicy.Policy.Fixed)
        for b in self._dims.findChildren(type(self._projeto)):
            chave = str(b.property("value"))
            if chave in dict(DIMS):
                motor = engines.get(engine_for(chave))
                b.setToolTip(f"{motor.label} — {motor.blurb}" if motor
                             else chave.upper())
        self._dims.changed.connect(self._on_dim_clicked)
        lay.addWidget(self._dims)

        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._nav = QWidget()
        self._nav.setSizePolicy(QSizePolicy.Policy.Fixed,
                                QSizePolicy.Policy.Preferred)
        self._nl = QHBoxLayout(self._nav)
        self._nl.setContentsMargins(0, 0, 0, 0)
        self._nl.setSpacing(0)
        lay.addWidget(self._nav)
        lay.addStretch(1)

        # ── a direita: simular / bloqueado / executando ──
        self._pilha = QStackedWidget()
        self._pilha.setFixedHeight(theme.dimension("button-lg"))

        self._b_run = button("Simular processo", "primary",
                             on_click=self.run_requested.emit)
        self._pilha.addWidget(row(self._b_run, spacing="0"))

        self._b_issues = button("", "link", on_click=self.issues_requested.emit)
        self._b_blocked = button("Simular processo", "primary")
        self._b_blocked.setEnabled(False)
        self._pilha.addWidget(row(self._b_issues, self._b_blocked, spacing="6"))

        self._dot = PulseDot()
        self._tempo = label("", "mono")
        self._tempo.setMinimumWidth(theme.space("24"))
        self._b_cancel = button("Cancelar", "small",
                                on_click=self.cancel_requested.emit)
        self._pilha.addWidget(row(self._dot, label("Executando", "base"),
                                  self._tempo, self._b_cancel, spacing="5"))
        lay.addWidget(self._pilha)

        self._build_nav()
        self.set_area("processo")
        self.set_project("")

    # ── navegação ─────────────────────────────────────────────────────────

    def _build_nav(self) -> None:
        """Refaz os botões da navegação para a dimensão atual."""
        for b in list(self._buttons.values()):
            self._grupo.removeButton(b)
            self._nl.removeWidget(b)
            # Como nos demais laços: o deleteLater só age quando o laço de
            # eventos roda, e até lá os botões da outra dimensão continuam
            # desenhados por cima dos novos.
            b.setParent(None)
            b.deleteLater()
        self._buttons.clear()
        while self._nl.count():
            item = self._nl.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) antes do deleteLater: o delete só acontece
                # quando o laço de eventos roda, e até lá o widget antigo
                # continua visível por cima do novo.
                w.setParent(None)
                w.deleteLater()

        def adicionar(chave: str, texto: str) -> None:
            b = button(texto, "nav", checkable=True)
            b.setProperty("area", chave)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            b.clicked.connect(
                lambda _c=False, k=chave: self.area_changed.emit(k))
            self._grupo.addButton(b)
            self._nl.addWidget(b)
            self._buttons[chave] = b

        for chave, numero, rotulo in AREAS[self._dim]:
            adicionar(chave, f"{numero}  {rotulo}")
        self._nl.addSpacing(theme.space("5"))
        self._nl.addWidget(vline())
        self._nl.addSpacing(theme.space("5"))
        self._ferramentas = eyebrow("ferramentas")
        self._nl.addWidget(self._ferramentas)
        for chave, rotulo in TOOLS[self._dim]:
            adicionar(chave, rotulo)
        self._compact = -1
        self._apply_compact()

    # ── adaptação à largura ───────────────────────────────────────────────

    def _run_text(self, area: str, curto: bool) -> str:
        """Rótulo do botão de execução para esta área."""
        if curto and area in RUN_LABELS_SHORT:
            return RUN_LABELS_SHORT[area]
        return RUN_LABELS.get(area, "Simular" if curto else "Simular processo")

    def _set_compact(self, nivel: int) -> None:
        """Aplica um nível de compactação aos rótulos."""
        nivel = max(0, min(3, nivel))
        if nivel == self._compact:
            return
        self._compact = nivel
        self._ferramentas.setVisible(nivel < 1)
        for chave, numero, rotulo in AREAS[self._dim]:
            b = self._buttons.get(chave)
            if b is not None:
                b.setText(rotulo if nivel >= 2 else f"{numero}  {rotulo}")
                b.setToolTip(rotulo if nivel >= 2 else "")
        self.set_area(self._area)
        self._nav.adjustSize()

    def _other_items_width(self) -> int:
        """Largura que todos os itens do cabeçalho pedem, fora a navegação.

        Vem do próprio layout, item a item, para nenhuma peça ficar de fora
        da conta — foi o que estragou as tentativas anteriores de estimar.
        """
        lay = self.layout()
        if lay is None:
            return 0
        larg = 0
        itens = 0
        for i in range(lay.count()):
            item = lay.itemAt(i)
            w = item.widget()
            if w is self._nav:
                itens += 1
                continue
            if w is not None:
                if w.isVisible():
                    larg += w.sizeHint().width()
                    itens += 1
                continue
            if item.spacerItem() is None:
                larg += item.sizeHint().width()
                itens += 1
        esq, _, dir_, _ = lay.getContentsMargins()
        return larg + esq + dir_ + lay.spacing() * max(0, itens - 1)

    def _nav_width_at(self, nivel: int) -> int:
        """Largura que a navegação pediria neste nível de compactação."""
        fm = None
        larg = 0
        for chave, numero, rotulo in AREAS[self._dim]:
            b = self._buttons.get(chave)
            if b is None:
                continue
            fm = b.fontMetrics()
            texto = rotulo if nivel >= 2 else f"{numero}  {rotulo}"
            # O botão guarda a mesma folga horizontal em qualquer rótulo.
            folga = b.sizeHint().width() - fm.horizontalAdvance(b.text())
            larg += fm.horizontalAdvance(texto) + folga
        for chave, _rotulo in TOOLS[self._dim]:
            b = self._buttons.get(chave)
            if b is not None:
                larg += b.sizeHint().width()
        larg += theme.space("5") * 2 + theme.dimension("border")
        if nivel < 1 and fm is not None:
            larg += (self._ferramentas.sizeHint().width())
        return larg

    def _right_saving(self) -> int:
        """Quanto o rótulo curto do botão de execução economiza."""
        fm = self._b_run.fontMetrics()
        return max(0, fm.horizontalAdvance(self._run_text(self._area, False))
                   - fm.horizontalAdvance(self._run_text(self._area, True)))

    def _apply_compact(self) -> None:
        """Escolhe o nível de compactação que cabe na largura atual.

        São três graus, nesta ordem de sacrifício: a palavra "ferramentas", os
        números das áreas e, por último, o rótulo longo do botão de execução.

        Sem isto, o Qt espremia os botões e cortava cada palavra — "Proces",
        "Resulta", "Model" — assim que a janela chegava ao seu tamanho mínimo.
        """
        if not self._buttons or self.width() <= 0:
            return
        sobra = self.width() - self._other_items_width()
        escolhido = 3
        for n in (0, 1, 2, 3):
            disponivel = sobra + (self._right_saving() if n >= 3 else 0)
            if self._nav_width_at(min(n, 2)) <= disponivel:
                escolhido = n
                break
        self._set_compact(escolhido)

    def resizeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().resizeEvent(event)
        self._apply_compact()

    def _on_dim_clicked(self, _index: int) -> None:
        self.set_dimension(self._dims.value(), emit=True)

    # ── estado ────────────────────────────────────────────────────────────

    def dimension(self) -> str:
        return self._dim

    def set_dimension(self, dim: str, *, emit: bool = False) -> None:
        """Troca a dimensão e refaz a navegação.

        Com ``emit``, avisa a janela — e também qual área ficou ativa, porque
        a tela atual pode não existir na dimensão nova.
        """
        if dim not in dict(DIMS):
            return
        destino = area_for(dim, self._area)
        if dim == self._dim:
            self._dims.set_value(dim)
            return
        self._dim = dim
        self._dims.set_value(dim)
        self._build_nav()
        self.set_area(destino)
        if emit:
            self.dimension_changed.emit(dim)
            self.area_changed.emit(destino)

    def set_area(self, area: str) -> None:
        """Marca a aba ativa e ajusta o rótulo do botão de execução."""
        self._area = area
        for chave, b in self._buttons.items():
            b.setChecked(chave == area)
        inteiro = self._run_text(area, False)
        texto = self._run_text(area, self._compact >= 3)
        self._b_run.setText(texto)
        self._b_blocked.setText(texto)
        for b in (self._b_run, self._b_blocked):
            b.setToolTip(inteiro if texto != inteiro else "")

    def areas(self) -> list[str]:
        """Chaves que a navegação atual oferece."""
        return list(self._buttons)

    def set_project(self, name: str) -> None:
        """Mostra o nome do projeto aberto (vazio = nenhum).

        Sem projeto não há o que simular, então a pílula de dimensão também
        sai de cena — escolher motor antes de ter projeto não decide nada.
        """
        if name:
            metrics = self._projeto.fontMetrics()
            largura = self._projeto.maximumWidth() - theme.space("12")
            self._projeto.setText(
                metrics.elidedText(name, Qt.TextElideMode.ElideRight, largura))
            self._projeto.setToolTip(name)
            self._projeto.show()
            self._dims.show()
            self._nav.show()
        else:
            self._projeto.hide()
            self._dims.hide()
            self._nav.hide()

    def _size_stack_to_page(self) -> None:
        """Faz a pilha ocupar só o que a página visível precisa.

        Um ``QStackedWidget`` dimensiona pela maior das páginas, então a de
        "executando" — que tem tempo e botão de cancelar — mandava na largura
        mesmo com o botão simples em cena, e o cabeçalho perdia espaço à toa.
        """
        atual = self._pilha.currentWidget()
        for i in range(self._pilha.count()):
            pagina = self._pilha.widget(i)
            pagina.setSizePolicy(
                QSizePolicy.Policy.Preferred if pagina is atual
                else QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred)
        self._pilha.adjustSize()
        self._apply_compact()

    def show_idle(self) -> None:
        self._dot.stop()
        self._pilha.setCurrentIndex(0)
        self._size_stack_to_page()

    def show_blocked(self, count: int) -> None:
        self._dot.stop()
        self._b_issues.setText(
            "1 problema impede a simulação" if count == 1
            else f"{count} problemas impedem a simulação")
        self._pilha.setCurrentIndex(1)
        self._size_stack_to_page()

    def show_running(self, elapsed: float) -> None:
        self._tempo.setText(format_elapsed(elapsed))
        if self._pilha.currentIndex() != 2:
            self._pilha.setCurrentIndex(2)
            self._size_stack_to_page()
            self._dot.start()

    def set_run_enabled(self, enabled: bool) -> None:
        """Desliga o botão quando o motor não está disponível."""
        self._b_run.setEnabled(enabled)
