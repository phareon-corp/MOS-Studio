"""Tela inicial: do processo ao transistor.

É a tela do arquivo de design: o herói com a pré-visualização de uma receita,
o fluxo de quatro passos, a biblioteca de receitas prontas e, no rodapé, as
execuções da versão anterior, a verificação do motor e a pasta de trabalho.

As pré-visualizações são perfis reais, calculados pelo SUPREM-III e guardados
em cache — nenhuma curva é ilustrativa.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QPushButton,
                               QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ...core import minimos, preview, suprem, workspace
from ...core.library import RECIPES, get
from ...core.recipe import fmt_number
from .. import theme
from ..widgets.common import (PulseDot, ResponsiveGrid, button, column,
                              eyebrow, hline, label, row, stretch, vline)
from ..widgets.hero import (HERO_COLORS, FlowStep, HeroBackground, RecipeCard)
from ..widgets.profile_chart import ChartData, ProfileChart, Series

#: Largura mínima de um cartão do fluxo antes de a grade quebrar a linha.
#: É o ``minmax(min(100%,220px),1fr)`` do arquivo de design.
CARD_MIN_WIDTH = 220

#: O mesmo para os três cartões do rodapé, que têm mais texto.
FOOTER_CARD_MIN_WIDTH = 300

FLUXO = (
    ("01", "Receita", "Etapas tipadas, com unidade, faixa e verificação antes "
                      "de rodar."),
    ("02", "Execução", "Tempo decorrido, etapa corrente e cancelamento sempre "
                       "à vista."),
    ("03", "Análise", "Perfil por etapa, junção e camadas; sobreponha "
                      "execuções."),
    ("04", "Dispositivo", "O perfil calculado vira a dopagem do deck do "
                          "MINIMOS."),
)


class _FilledBar(QWidget):
    """Retângulo preenchido com um token de cor do tema."""

    def __init__(self, token: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._token = token

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qcolor(self._token))
        p.end()


class _PreviewWorker(QObject):
    """Calcula as pré-visualizações fora da thread da interface."""

    ready = Signal(str, object)
    finished = Signal()

    def run(self) -> None:
        for receita in RECIPES:
            try:
                self.ready.emit(receita.key, preview.compute(receita))
            except Exception:                    # noqa: BLE001 - segue adiante
                self.ready.emit(receita.key, preview.Preview(key=receita.key,
                                                             error="falhou"))
        self.finished.emit()


class _ClickableCard(QWidget):
    """Um cartão que responde ao clique, com realce no hover."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme.mark(self, role="tutorial-entry", hovered="false")
        self.setAutoFillBackground(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        politica = QSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Minimum)
        politica.setHeightForWidth(True)
        self.setSizePolicy(politica)

    def hasHeightForWidth(self) -> bool:      # noqa: N802 - API do Qt
        return True

    def heightForWidth(self, largura: int) -> int:   # noqa: N802 - API do Qt
        lay = self.layout()
        return lay.heightForWidth(largura) if lay is not None else -1

    def resizeEvent(self, event) -> None:     # noqa: N802 - API do Qt
        """Reserva a altura que o texto quebrado precisa.

        O ``heightForWidth`` sozinho não basta: ele só vale se **todos** os
        layouts até a janela o repassarem, e a cadeia do herói não repassa.
        Medindo aqui, com a largura já conhecida, o cartão cresce sozinho e a
        segunda linha da descrição para de sumir.
        """
        super().resizeEvent(event)
        lay = self.layout()
        if lay is None:
            return
        preciso = lay.heightForWidth(self.width())
        if preciso > 0 and preciso != self.minimumHeight():
            self.setMinimumHeight(preciso)

    def enterEvent(self, event) -> None:      # noqa: N802 - API do Qt
        theme.mark(self, hovered="true")
        theme.restyle(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:      # noqa: N802 - API do Qt
        theme.mark(self, hovered="false")
        theme.restyle(self)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:   # noqa: N802 - API do Qt
        if (event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class HomeScreen(QWidget):
    """A tela inicial inteira, rolável."""

    new_project = Signal(str)        # chave da receita
    open_project = Signal()
    import_deck = Signal()
    import_legacy = Signal()
    change_working_dir = Signal()
    recheck_engines = Signal()
    #: Abrir o passeio pela interface.
    tour_requested = Signal()
    #: Abrir o projeto guiado (transistor LDD).
    guided_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: dict[str, RecipeCard] = {}
        self._previews: dict[str, preview.Preview] = {}
        self._flow_steps: list[FlowStep] = []
        #: Roteiros já concluídos, para o contador do cartão de tutorial.
        self._tut_feitos: set[str] = set()
        self._tut_marcas: dict[str, object] = {}
        self._hovered = RECIPES[0].key
        self._thread: QThread | None = None

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        conteudo = QWidget()
        self._corpo = QVBoxLayout(conteudo)
        self._corpo.setContentsMargins(0, 0, 0, 0)
        self._corpo.setSpacing(0)
        self._corpo.addWidget(self._build_hero())
        self._corpo.addWidget(self._build_library())
        self._corpo.addWidget(self._build_footer_cards())
        self._corpo.addStretch(1)
        self._scroll.setWidget(conteudo)
        raiz.addWidget(self._scroll)

        self.set_hovered(self._hovered)
        self._set_flow(0)
        self._refresh_tutorial()

    # ── herói ─────────────────────────────────────────────────────────────

    def _build_hero(self) -> QWidget:
        fundo = HeroBackground()
        lay = QVBoxLayout(fundo)
        lay.setContentsMargins(theme.space("16"), theme.space("20"),
                               theme.space("16"), theme.space("12"))
        lay.setSpacing(theme.space("16"))

        topo = QHBoxLayout()
        topo.setSpacing(theme.space("24"))
        topo.addWidget(self._build_hero_text(), 1)
        topo.addWidget(self._build_preview_panel(), 1)
        lay.addLayout(topo)

        lay.addWidget(self._hero_line())
        # Grade que reflui, como o auto-fit do arquivo de design: quatro
        # cartões lado a lado numa janela larga, duas linhas numa estreita —
        # em vez de quatro colunas espremidas até o texto quebrar palavra.
        fluxo = ResponsiveGrid(CARD_MIN_WIDTH, spacing="12")
        passos = []
        for i, (numero, titulo, descricao) in enumerate(FLUXO):
            passo = FlowStep(i, numero, titulo, descricao)
            passo.entered.connect(self._set_flow)
            self._paint_on_hero(passo)
            self._flow_steps.append(passo)
            passos.append(passo)
        fluxo.set_items(passos)
        self._paint_on_hero(fluxo)
        lay.addWidget(fluxo)
        return fundo

    def _hero_line(self) -> QWidget:
        linha = _FilledBar("hero-line")
        linha.setFixedHeight(theme.dimension("border"))
        return linha

    def _paint_on_hero(self, widget: QWidget) -> None:
        """Marca o widget e os filhos para usarem as cores do herói.

        É propriedade dinâmica, não paleta: o `color` do QSS vence a paleta.
        """
        for alvo in [widget, *widget.findChildren(QWidget)]:
            if alvo.property("onhero") is None:
                theme.mark(alvo, onhero="true")
                theme.restyle(alvo)

    def _build_hero_text(self) -> QWidget:
        caixa = QWidget()
        lay = QVBoxLayout(caixa)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space("10"))

        lay.addWidget(label("01 / primeiro uso", "eyebrow-accent"))

        titulo = label("", "display")
        titulo.setTextFormat(Qt.TextFormat.RichText)
        titulo.setWordWrap(True)
        titulo.setText(
            f'<span style="color:{theme.color("hero-ink")}">Do processo</span><br>'
            f'<span style="font-family:\'{theme.resolve_family("serif")}\';'
            f'font-style:italic;color:{theme.color("hero-ink-dim")}">'
            f'ao transistor.</span>')
        titulo.setFont(theme.font("display", "display", "medium", "tighter"))
        lay.addWidget(titulo)

        texto = label(
            "Simule o processo em 1-D com o SUPREM-III ou em seção "
            "transversal 2-D com o SUPREM-IV, compare execuções lado a lado "
            "e leve o perfil de dopagem direto para o MINIMOS. Tudo em um "
            "único projeto.", "dim", wrap=True)
        texto.setMaximumWidth(theme.space("24") * 11)
        lay.addWidget(texto)

        acoes = QHBoxLayout()
        acoes.setSpacing(theme.space("5"))
        b_novo = button("Novo projeto  ↗", "primary",
                        on_click=lambda: self.new_project.emit(self._hovered))
        b_abrir = button("Abrir projeto…", "ghost",
                         on_click=self.open_project.emit)
        b_deck = button("Importar deck .IN", "ghost",
                        on_click=self.import_deck.emit)
        for b in (b_novo, b_abrir, b_deck):
            theme.mark(b, onhero="true")
            acoes.addWidget(b)
        acoes.addStretch(1)
        lay.addLayout(acoes)

        lay.addWidget(self._build_tutorial_card())

        self._pulso = PulseDot()
        self._motores = label("", "eyebrow")
        lay.addWidget(row(self._pulso, self._motores, stretch(), spacing="4"))

        self._paint_on_hero(caixa)
        for w in (texto, self._motores):
            self._tint(w, "hero-ink-dim")
        self._tint(titulo, "hero-ink")
        return caixa

    def _build_tutorial_card(self) -> QWidget:
        """O cartão dos roteiros guiados, dentro do herói.

        É como o arquivo de design apresenta os dois tutoriais: cada um com o
        nome, o tamanho ("13 PASSOS · 4 MIN") e uma linha dizendo o que se
        faz nele. Antes eram dois links soltos, que não diziam nada sobre o
        que havia do outro lado.
        """
        caixa = QWidget()
        theme.mark(caixa, surface="hero-surface", role="tutorial-card")
        caixa.setAutoFillBackground(True)
        caixa.setMaximumWidth(theme.space("24") * 11)
        lay = QVBoxLayout(caixa)
        lay.setContentsMargins(theme.space("8"), theme.space("7"),
                               theme.space("8"), theme.space("7"))
        lay.setSpacing(theme.space("5"))

        titulo = label("novo por aqui? · tutorial interativo", "eyebrow")
        self._tut_progresso = label("", "eyebrow")
        lay.addWidget(row(titulo, stretch(), self._tut_progresso))

        for chave, nome, medida, descricao, sinal in (
                ("ui", "Tour pela interface", "13 passos · 4 min",
                 "Destaques sobre as telas de verdade. Você clica você mesmo: "
                 "malha, receita 2-D, cortes e console.",
                 self.tour_requested),
                ("ldd", "Projeto guiado: LDD 2-D", "exam5 · 12 etapas",
                 "Monte o transistor LDD do manual do SUPREM-IV etapa por "
                 "etapa e veja a seção transversal crescer.",
                 self.guided_requested)):
            lay.addWidget(self._tutorial_entry(chave, nome, medida,
                                               descricao, sinal))

        for w in (titulo, self._tut_progresso):
            self._tint(w, "hero-ink-dim")
        return caixa

    def _tutorial_entry(self, chave: str, nome: str, medida: str,
                        descricao: str, sinal) -> QWidget:
        """Um dos dois roteiros, como cartão inteiro clicável.

        Não é um ``QPushButton``: um botão com layout dentro não adota a
        altura do próprio conteúdo, e as duas linhas de texto saíam
        esmagadas numa tira ilegível.
        """
        alvo = _ClickableCard()
        alvo.clicked.connect(sinal.emit)
        lay = QVBoxLayout(alvo)
        lay.setContentsMargins(theme.space("7"), theme.space("6"),
                               theme.space("7"), theme.space("6"))
        lay.setSpacing(theme.space("3"))

        titulo = label(nome, "base")
        titulo.setFont(theme.font("sans", "base", "medium"))
        marca = label(medida, "eyebrow")
        self._tut_marcas[chave] = marca
        lay.addWidget(row(titulo, stretch(), marca))
        texto = label(descricao, "hint", wrap=True)
        # Sem heightForWidth, o layout dá ao rótulo a altura de uma linha só
        # e o texto quebrado some a partir da segunda.
        politica = texto.sizePolicy()
        politica.setHeightForWidth(True)
        texto.setSizePolicy(politica)
        lay.addWidget(texto)

        self._tint(titulo, "hero-ink")
        for w in (marca, texto):
            self._tint(w, "hero-ink-dim")
        return alvo

    def mark_tutorial_done(self, chave: str) -> None:
        """Marca um roteiro como concluído, para o contador do cartão."""
        self._tut_feitos.add(chave)
        self._refresh_tutorial()

    def _refresh_tutorial(self) -> None:
        self._tut_progresso.setText(
            f"{len(self._tut_feitos)} de 2 concluídos".upper())
        for chave, marca in self._tut_marcas.items():
            if chave in self._tut_feitos:
                marca.setText("concluído ✓".upper())

    def _tint(self, widget: QWidget, token: str) -> None:
        """Escolhe a tinta do herói: clara (`hero-ink`) ou apagada."""
        theme.mark(widget, onhero="dim" if token.endswith("dim") else "ink")
        theme.restyle(widget)

    def _build_preview_panel(self) -> QWidget:
        painel = _FilledBar("hero-surface")
        painel.setMinimumWidth(theme.space("24") * 9)

        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cabeca = QWidget()
        cl = QHBoxLayout(cabeca)
        cl.setContentsMargins(theme.space("9"), theme.space("7"),
                              theme.space("9"), theme.space("7"))
        self._previa_rotulo = label("pré-visualização · perfil líquido", "eyebrow")
        self._previa_nome = label("", "base")
        cl.addWidget(self._previa_rotulo)
        cl.addStretch(1)
        cl.addWidget(self._previa_nome)
        lay.addWidget(cabeca)
        lay.addWidget(self._hero_line())

        self._previa_grafico = ProfileChart()
        self._previa_grafico.set_color_map(HERO_COLORS)
        self._previa_grafico.setMinimumHeight(theme.space("24") * 5)
        self._previa_grafico.set_empty_message("calculando a pré-visualização…")
        lay.addWidget(self._previa_grafico, 1)

        self._chips = QWidget()
        self._chips_lay = QHBoxLayout(self._chips)
        self._chips_lay.setContentsMargins(theme.space("9"), theme.space("4"),
                                           theme.space("9"), theme.space("5"))
        self._chips_lay.setSpacing(theme.space("3"))
        lay.addWidget(self._chips)

        lay.addWidget(self._hero_line())
        self._stats = QWidget()
        self._stats_lay = QHBoxLayout(self._stats)
        self._stats_lay.setContentsMargins(0, 0, 0, 0)
        self._stats_lay.setSpacing(theme.dimension("border"))
        lay.addWidget(self._stats)

        self._paint_on_hero(painel)
        self._tint(self._previa_rotulo, "hero-ink-dim")
        return painel

    # ── biblioteca ────────────────────────────────────────────────────────

    def _build_library(self) -> QWidget:
        secao = QWidget()
        lay = QVBoxLayout(secao)
        lay.setContentsMargins(theme.space("16"), theme.space("20"),
                               theme.space("16"), theme.space("16"))
        lay.setSpacing(theme.space("12"))

        cabeca = QHBoxLayout()
        cabeca.setSpacing(theme.space("24"))
        cabeca.addWidget(label("02 / biblioteca", "eyebrow"), 0,
                         Qt.AlignmentFlag.AlignTop)
        texto = QVBoxLayout()
        texto.setSpacing(theme.space("5"))
        titulo = label("", "display")
        titulo.setTextFormat(Qt.TextFormat.RichText)
        titulo.setWordWrap(True)
        titulo.setText(
            f'Comece de uma receita '
            f'<span style="font-family:\'{theme.resolve_family("serif")}\';'
            f'font-style:italic;color:{theme.color("ink-dim")}">pronta</span>')
        titulo.setFont(theme.font("display", "h1", "medium", "tight"))
        texto.addWidget(titulo)
        desc = label(
            "As receitas embutidas são conteúdo editável, não código. Passe o "
            "mouse para ver o perfil acima — ele é calculado pelo SUPREM-III, "
            "não é ilustração.", "dim", wrap=True)
        desc.setMaximumWidth(theme.space("24") * 14)
        texto.addWidget(desc)
        cabeca.addLayout(texto, 1)
        lay.addLayout(cabeca)

        grade = QGridLayout()
        grade.setSpacing(theme.dimension("border"))
        for i, receita in enumerate(RECIPES):
            cartao = RecipeCard(receita)
            cartao.hovered.connect(self.set_hovered)
            cartao.chosen.connect(self.new_project.emit)
            self._cards[receita.key] = cartao
            grade.addWidget(cartao, i // 3, i % 3)
        for c in range(3):
            grade.setColumnStretch(c, 1)
        moldura = _FilledBar("line-strong")
        moldura.setLayout(grade)
        lay.addWidget(moldura)
        return secao

    # ── rodapé ────────────────────────────────────────────────────────────

    def _build_footer_cards(self) -> QWidget:
        secao = QWidget()
        lay = QVBoxLayout(secao)
        lay.setContentsMargins(theme.space("16"), 0,
                               theme.space("16"), theme.space("20"))
        lay.setSpacing(0)

        self._card_legado = self._card()
        self._legado_lay = self._card_body(self._card_legado)
        self._card_motor = self._card()
        self._motor_lay = self._card_body(self._card_motor)
        self._card_pasta = self._card()
        self._pasta_lay = self._card_body(self._card_pasta)

        self._cards_rodape = ResponsiveGrid(FOOTER_CARD_MIN_WIDTH,
                                            spacing="0")
        self._cards_rodape.set_items(
            [self._card_legado, self._card_motor, self._card_pasta])
        lay.addWidget(self._cards_rodape)
        return secao

    def _card(self) -> QWidget:
        w = QWidget()
        theme.mark(w, surface="raised")
        w.setAutoFillBackground(True)
        return w

    def _card_body(self, card: QWidget) -> QVBoxLayout:
        lay = QVBoxLayout(card)
        lay.setContentsMargins(theme.space("13"), theme.space("14"),
                               theme.space("13"), theme.space("14"))
        lay.setSpacing(theme.space("5"))
        return lay

    # ── estado ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Atualiza os cartões do rodapé e dispara as pré-visualizações."""
        self._refresh_engines()
        self._refresh_legacy()
        self._refresh_folder()
        self._start_previews()

    def _clear(self, lay: QVBoxLayout) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _refresh_engines(self) -> None:
        from ...core import suprem4

        problemas_sup = suprem.check_engine(suprem.find_run_dir())
        problemas_s4 = suprem4.check_engine(suprem4.find_run_dir())
        problemas_mm = minimos.check_engine(minimos.find_dir())
        tudo_ok = not problemas_sup and not problemas_s4 and not problemas_mm
        self._motores.setText(
            ("SUPREM-III, SUPREM-IV e MINIMOS verificados · binários nativos"
             if tudo_ok
             else "Motor incompleto — veja a verificação abaixo").upper())
        if tudo_ok:
            self._pulso.start()
        else:
            self._pulso.stop()

        self._clear(self._motor_lay)
        self._motor_lay.addWidget(eyebrow("verificação do motor"))
        itens = self._engine_items(problemas_sup, problemas_mm)
        grade = QGridLayout()
        grade.setSpacing(theme.space("4"))
        for i, (nome, detalhe, ok) in enumerate(itens):
            marca = label("✓" if ok else "✕", "mono")
            if not ok:
                theme.mark(marca, role="error")
                theme.restyle(marca)
            linha = QVBoxLayout()
            linha.setSpacing(0)
            linha.addWidget(label(nome, "mono"))
            linha.addWidget(label(detalhe, "hint"))
            caixa = QWidget()
            cl = QHBoxLayout(caixa)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(theme.space("4"))
            cl.addWidget(marca, 0, Qt.AlignmentFlag.AlignTop)
            cl.addLayout(linha, 1)
            grade.addWidget(caixa, i // 2, i % 2)
        host = QWidget()
        host.setLayout(grade)
        self._motor_lay.addWidget(host)
        self._motor_lay.addStretch(1)
        self._motor_lay.addWidget(button("Verificar de novo", "small",
                                         on_click=self.recheck_engines.emit))

    def _engine_items(self, problemas_sup, problemas_mm):
        from ...core import suprem4

        itens = []
        for binario in suprem.BINARIES:
            falha = next((p for p in problemas_sup if binario in p), "")
            itens.append((binario, falha or "SUPREM-III", not falha))
        problemas_s4 = suprem4.check_engine(suprem4.find_run_dir())
        itens.append(("suprem", problemas_s4[0] if problemas_s4
                      else "SUPREM-IV.GS · motor 2-D", not problemas_s4))
        faltando = [p for p in problemas_sup if "coeficiente" in p]
        itens.append(("Arquivos de dados",
                      f"{len(suprem.DATA_FILES)} coeficientes e modelos"
                      if not faltando else faltando[0],
                      not faltando))
        itens.append(("mm_pl",
                      next((p for p in problemas_mm if "mm_pl" in p), "MINIMOS 6.1"),
                      not any("mm_pl" in p for p in problemas_mm)))
        itens.append(("stack.rul",
                      next((p for p in problemas_mm if "stack" in p),
                           "regras do MINIMOS"),
                      not any("stack" in p for p in problemas_mm)))
        return itens

    def _refresh_legacy(self) -> None:
        self._clear(self._legado_lay)
        total = workspace.count_legacy_runs()
        importado = workspace.legacy_imported()
        self._legado_lay.addWidget(eyebrow("versão anterior"))
        numero = label(str(total), "metric")
        numero.setFont(theme.font("display", "h1", "medium", "tighter"))
        unidade = label("execuções", "serif")
        self._legado_lay.addWidget(row(numero, unidade, stretch(), spacing="4"))
        self._legado_lay.addWidget(label(
            f"Encontradas em {workspace.legacy_results_dir()}. "
            + ("Já aparecem na lista de execuções."
               if importado else
               "Importe para listá-las junto com as novas — os arquivos não "
               "saem do lugar."),
            "hint", wrap=True))
        self._legado_lay.addStretch(1)
        if total and not importado:
            self._legado_lay.addWidget(button(
                f"Importar {total} execuções", "small",
                on_click=self.import_legacy.emit))

    def _refresh_folder(self) -> None:
        self._clear(self._pasta_lay)
        self._pasta_lay.addWidget(eyebrow("pasta de trabalho"))
        caminho = label(str(workspace.working_dir()), "title")
        caminho.setFont(theme.font("display", "h3", "medium", "tight"))
        caminho.setWordWrap(True)
        self._pasta_lay.addWidget(caminho)
        from ... import paths as _paths
        self._pasta_lay.addWidget(label(
            f"Projetos e execuções ficam aqui, fora da pasta do programa. "
            f"As preferências ficam em {_paths.config_dir()}.", "hint", wrap=True))
        self._pasta_lay.addStretch(1)
        self._pasta_lay.addWidget(button("Escolher outra pasta", "small",
                                         on_click=self.change_working_dir.emit))

    # ── pré-visualizações ─────────────────────────────────────────────────

    def _start_previews(self) -> None:
        if self._thread is not None:
            return
        pendentes = [r for r in RECIPES if r.key not in self._previews]
        if not pendentes:
            return
        self._thread = QThread(self)
        self._worker = _PreviewWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.ready.connect(self._on_preview)
        self._worker.finished.connect(self._on_previews_done)
        self._thread.start()

    def shutdown(self) -> None:
        """Encerra a thread das prévias antes de a janela morrer.

        As prévias rodam o motor de verdade; sem esperar por elas, o Qt
        reclama de thread destruída e o processo aborta na saída.
        """
        if self._thread is None:
            return
        self._thread.quit()
        self._thread.wait(5000)
        self._thread = None

    def _on_preview(self, chave: str, previa) -> None:
        self._previews[chave] = previa
        cartao = self._cards.get(chave)
        if cartao is not None:
            cartao.set_preview(previa)
        if chave == self._hovered:
            self._show_preview(chave)

    def _on_previews_done(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None

    def set_hovered(self, chave: str) -> None:
        """Destaca uma receita e mostra o perfil dela no herói."""
        self._hovered = chave
        for k, cartao in self._cards.items():
            cartao.set_active(k == chave)
        self._show_preview(chave)

    def _show_preview(self, chave: str) -> None:
        receita = get(chave)
        self._previa_nome.setText(f"{receita.name} {receita.emphasis}".strip())
        previa = self._previews.get(chave)

        self._clear_layout(self._chips_lay)
        etapas = receita.build()
        visiveis, resto = etapas[:8], len(etapas) - 8
        for etapa in visiveis:
            ficha = label(etapa.type, "eyebrow")
            ficha.setContentsMargins(theme.space("3"), theme.space("1"),
                                     theme.space("3"), theme.space("1"))
            self._tint(ficha, "hero-ink-dim")
            self._chips_lay.addWidget(ficha)
        if resto > 0:
            mais = label(f"+{resto}", "eyebrow")
            self._tint(mais, "hero-ink-dim")
            self._chips_lay.addWidget(mais)
        self._chips_lay.addStretch(1)

        if previa is None:
            self._previa_grafico.clear()
            self._previa_grafico.set_empty_message("calculando a pré-visualização…")
            self._fill_stats(receita, None)
            return
        if not previa.ok:
            self._previa_grafico.clear()
            self._previa_grafico.set_empty_message(
                previa.error or "esta receita não produz tabela de perfil")
        else:
            self._previa_grafico.set_data(ChartData(
                series=[Series("Líquido", [(x, abs(c)) for x, c in previa.points],
                               "accent", width=2.0)],
                junctions=previa.junctions))
        self._fill_stats(receita, previa)

    def _clear_layout(self, lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _fill_stats(self, receita, previa) -> None:
        self._clear_layout(self._stats_lay)
        if previa is None:
            dados = [("JUNÇÃO", "—", "calculando"),
                     ("SUPERFÍCIE", "—", ""),
                     ("ETAPAS", str(receita.step_count),
                      "etapa" if receita.step_count == 1 else "etapas")]
        else:
            if previa.junction is not None:
                juncao = (f"{previa.junction:.3f}".replace(".", ","), "µm")
            elif previa.ok:
                juncao = ("—", "sem junção")
            else:
                juncao = ("—", "sem perfil")
            superficie = (fmt_number(previa.surface), "cm⁻³") if previa.ok \
                else ("—", "")
            dados = [("JUNÇÃO", *juncao), ("SUPERFÍCIE", *superficie),
                     ("ETAPAS", str(receita.step_count),
                      "etapa" if receita.step_count == 1 else "etapas")]
        for rotulo, valor, unidade in dados:
            caixa = _FilledBar("hero-bg")
            cl = QVBoxLayout(caixa)
            cl.setContentsMargins(theme.space("9"), theme.space("7"),
                                  theme.space("9"), theme.space("7"))
            cl.setSpacing(theme.space("3"))
            r = label(rotulo, "eyebrow")
            v = label(valor, "title")
            v.setFont(theme.font("display", "h3", "medium", "tight"))
            u = label(unidade, "serif")
            u.setFont(theme.font("serif", "base", italic=True))
            cl.addWidget(r)
            cl.addWidget(row(v, u, stretch(), spacing="2"))
            self._paint_on_hero(caixa)
            self._tint(r, "hero-ink-dim")
            self._tint(u, "hero-ink-dim")
            self._tint(v, "hero-ink")
            self._stats_lay.addWidget(caixa, 1)

    def _set_flow(self, indice: int) -> None:
        for i, passo in enumerate(self._flow_steps):
            passo.set_active(i <= indice)

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
