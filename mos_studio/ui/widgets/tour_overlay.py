"""O destaque dos roteiros guiados, por cima da interface de verdade.

Em vez de um vídeo ou de uma janela de ajuda à parte, o passeio escurece a
janela, abre um buraco em volta do widget de que está falando e põe o cartão
ao lado. O usuário faz a ação na interface real — é a diferença entre
aprender onde as coisas ficam e assistir alguém mexer.

O cartão segue o arquivo de design em todos os detalhes:

* barra de progresso em segmentos no topo, um por passo, acesos até o atual;
* linha de identificação com o roteiro e a posição (``TOUR · INTERFACE · 3/13``);
* o cartão do deck que o passo ilustra, num bloco com fundo e borda;
* a ação pedida precedida de um ponto que pulsa enquanto se espera;
* rodapé com "Sair do tutorial", "Voltar" e um botão que muda de rótulo —
  **Pular** quando há ação pendente, **Concluir** no último passo, **Próximo**
  no resto.

E se move: o buraco e o cartão deslizam para o alvo em 0,35 s, com a mesma
curva do design. A posição do cartão é calculada em volta do destaque — ao
lado quando o alvo é alto, abaixo (ou acima, se não couber) quando é baixo —
e nunca encosta na borda da janela.

Os widgets de destaque se registram por nome (:meth:`TourOverlay.register`),
para o roteiro em :mod:`mos_studio.core.tour` não precisar conhecer a árvore
de widgets.
"""

from __future__ import annotations

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QRect, QRectF,
                            QTimer, QVariantAnimation, Qt, Signal)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget)

from ...core import tour as tour_mod
from .. import theme
from .common import PulseDot, button, label, row, stretch

#: Folga em volta do widget destacado, em pixels. É o ``-6`` do design.
PADDING = 6

#: Margem mínima entre o cartão e a borda da janela.
MARGIN = 16

#: Com que frequência o destaque confere se a ação pedida já foi feita.
POLL_MS = 250

#: Largura do cartão, fixa como no design.
CARD_WIDTH = 380

#: Altura usada no cálculo da posição antes de o cartão existir.
CARD_HEIGHT_GUESS = 290

#: Duração e curva da transição, iguais às do design.
MOVE_MS = 350
EASING = QEasingCurve.Type.OutCubic

#: Altura de cada segmento da barra de progresso.
DOT_HEIGHT = 3


class _Progress(QWidget):
    """A barra de progresso em segmentos do topo do cartão."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._total = 0
        self._index = 0
        self.setFixedHeight(DOT_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_progress(self, index: int, total: int) -> None:
        self._index, self._total = index, total
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._total <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        vao = 3
        largura = (self.width() - vao * (self._total - 1)) / self._total
        for i in range(self._total):
            p.setBrush(theme.qcolor("accent") if i <= self._index
                       else theme.qcolor("line-strong"))
            p.drawRoundedRect(QRectF(i * (largura + vao), 0.0,
                                     largura, float(DOT_HEIGHT)), 2.0, 2.0)
        p.end()


class TourOverlay(QWidget):
    """A camada escura com o buraco e o cartão.

    Vive sobre a janela inteira e só aparece durante um roteiro.
    """

    finished = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._targets: dict[str, QWidget] = {}
        self._steps: tuple[tour_mod.Step, ...] = ()
        self._index = 0
        self._host = parent
        self._label = ""
        #: Retângulo desenhado agora — animado até o do alvo.
        self._rect = QRect()
        self._wanted = QRect()
        self.hide()

        self._build_card()
        self._card.hide()

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(MOVE_MS)
        self._anim.setEasingCurve(EASING)
        self._anim.valueChanged.connect(self._on_anim)

        self._card_anim = QVariantAnimation(self)
        self._card_anim.setDuration(MOVE_MS)
        self._card_anim.setEasingCurve(EASING)
        self._card_anim.valueChanged.connect(
            lambda p: self._card.move(p.toPoint() if hasattr(p, "toPoint")
                                      else p))

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        parent.installEventFilter(self)

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_card(self) -> None:
        # O cartão é **irmão** da camada escura, não filho: para o clique
        # passar para a interface de verdade, a camada precisa ficar
        # transparente ao mouse — e o Qt não desce o teste de acerto por
        # dentro de um widget transparente, o que levaria os botões do cartão
        # junto. Como irmão, erguido acima, ele recebe clique normalmente.
        self._card = QWidget(self._host)
        theme.mark(self._card, surface="raised", role="tour-card")
        self._card.setFixedWidth(CARD_WIDTH)
        self._card_width = CARD_WIDTH

        caixa = QVBoxLayout(self._card)
        caixa.setContentsMargins(theme.space("8"), theme.space("7"),
                                 theme.space("8"), theme.space("8"))
        caixa.setSpacing(theme.space("5"))

        self._progresso = _Progress()
        caixa.addWidget(self._progresso)

        self._eyebrow = label("", "eyebrow-accent")
        caixa.addWidget(self._eyebrow)

        self._titulo = label("", "title")
        self._titulo.setWordWrap(True)
        caixa.addWidget(self._titulo)

        self._texto = label("", "dim", wrap=True)
        caixa.addWidget(self._texto)

        self._cartao_deck = label("", "mono", wrap=True)
        theme.mark(self._cartao_deck, surface="code", role="tour-code")
        self._cartao_deck.setContentsMargins(theme.space("5"),
                                             theme.space("4"),
                                             theme.space("5"),
                                             theme.space("4"))
        caixa.addWidget(self._cartao_deck)

        self._pulso = PulseDot()
        self._acao = label("", "base", wrap=True)
        self._acao.setFont(theme.font("sans", "small", "medium"))
        self._acao_linha = row(self._pulso, self._acao, stretch(),
                               spacing="4")
        caixa.addWidget(self._acao_linha)

        self._b_sair = button("Sair do tutorial", "link", on_click=self.stop)
        self._b_voltar = button("Voltar", "small", on_click=self.previous)
        self._b_proximo = button("Próximo", "primary", on_click=self.next)
        rodape = QHBoxLayout()
        rodape.setContentsMargins(0, theme.space("2"), 0, 0)
        rodape.setSpacing(theme.space("4"))
        rodape.addWidget(self._b_sair)
        rodape.addStretch(1)
        rodape.addWidget(self._b_voltar)
        rodape.addWidget(self._b_proximo)
        caixa.addLayout(rodape)

    # ── registro ──────────────────────────────────────────────────────────

    def register(self, nome: str, widget: QWidget) -> None:
        """Associa um nome de destaque a um widget da janela."""
        self._targets[nome] = widget

    # ── roteiro ───────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        """Há um roteiro em curso.

        Depende de ter passos, não de o widget estar visível: numa janela que
        ainda não foi mostrada o destaque existe e funciona, e amarrar o
        estado à visibilidade tornava o roteiro indistinguível de nenhum.
        """
        return bool(self._steps)

    @property
    def index(self) -> int:
        return self._index

    def steps(self) -> tuple[tour_mod.Step, ...]:
        return self._steps

    def start(self, steps: tuple[tour_mod.Step, ...], label: str = "") -> None:
        """Começa um roteiro. ``label`` nomeia-o na linha de identificação."""
        if not steps:
            return
        self._steps = steps
        self._index = 0
        self._label = label or "TOUR"
        self._rect = QRect()
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        self._card.show()
        self._card.raise_()
        self._timer.start()
        self._refresh(animate=False)

    def stop(self) -> None:
        self._timer.stop()
        self._anim.stop()
        self._card_anim.stop()
        self._card.hide()
        self.hide()
        self._steps = ()
        self.finished.emit()

    def next(self) -> None:
        """Avança um passo, fazendo a ação pendente se houver.

        "Pular" não pula o **efeito** do passo, só a parte de fazer você
        mesmo: senão quem clicasse em pular do começo ao fim terminava o
        passeio sem o aplicativo ter saído da tela de Início, com treze
        cartões falando de telas que nunca apareceram.
        """
        passo = self.current()
        if passo is not None and passo.perform is not None and self.waiting():
            try:
                passo.perform(self._host)
            except Exception:  # noqa: BLE001 - o roteiro não derruba a tela
                pass
        if self._index + 1 >= len(self._steps):
            self.stop()
            return
        self._index += 1
        self._refresh()

    def previous(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._refresh()

    def current(self) -> tour_mod.Step | None:
        if not self._steps or self._index >= len(self._steps):
            return None
        return self._steps[self._index]

    def waiting(self) -> bool:
        """``True`` enquanto o passo espera uma ação que não foi feita."""
        passo = self.current()
        if passo is None or passo.done is None:
            return False
        try:
            return not bool(passo.done(self._host))
        except Exception:      # noqa: BLE001 - o roteiro não derruba a tela
            return True

    # ── estado ────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Avança sozinho quando a ação pedida foi feita.

        Também reposiciona: o alvo se move quando a navegação muda de tela,
        a janela é redimensionada ou um painel aparece.
        """
        passo = self.current()
        if passo is None:
            return
        if passo.done is not None and not self.waiting():
            self.next()
            return
        self._aim()
        self._refresh_waiting()

    def _target_rect(self) -> QRect | None:
        passo = self.current()
        if passo is None or not passo.target:
            return None
        w = self._targets.get(passo.target)
        if w is None or not w.isVisible():
            return None
        topo = w.mapTo(self._host, w.rect().topLeft())
        r = QRect(topo, w.size()).adjusted(-PADDING, -PADDING,
                                           PADDING, PADDING)
        # Um alvo fora da área visível não vale destacar.
        return r if r.intersects(self.rect()) else None

    def _aim(self, animate: bool = True) -> None:
        """Move o buraco e o cartão para o alvo do passo atual."""
        alvo = self._target_rect() or QRect()
        destino = self._card_pos(alvo)
        if alvo == self._wanted and self._card.pos() == destino:
            return
        self._wanted = alvo
        if not animate or self._rect.isNull() or alvo.isNull():
            self._anim.stop()
            self._card_anim.stop()
            self._rect = alvo
            self._card.move(destino)
            self._update_mouse_transparency()
            self.update()
            return
        self._anim.stop()
        self._anim.setStartValue(self._rect)
        self._anim.setEndValue(alvo)
        self._anim.start()
        self._card_anim.stop()
        self._card_anim.setStartValue(self._card.pos())
        self._card_anim.setEndValue(destino)
        self._card_anim.start()

    def _on_anim(self, valor) -> None:
        self._rect = valor if isinstance(valor, QRect) else QRect(valor)
        self._update_mouse_transparency()
        self.update()

    def _fit_card_width(self) -> None:
        """Encolhe o cartão quando a janela é estreita demais para 380 px.

        A largura do design é fixa, e numa janela larga é a certa. Mas numa
        estreita um cartão que não cabe sairia pela borda ou taparia a tela
        inteira, então ele cede.
        """
        alvo = min(CARD_WIDTH, max(240, self.width() - 2 * MARGIN))
        if alvo != self._card_width:
            self._card_width = alvo
            self._card.setFixedWidth(alvo)
            self._card.adjustSize()

    def _card_pos(self, alvo: QRect) -> QPoint:
        """Onde o cartão cabe sem tapar o destaque.

        É o cálculo do arquivo de design: ao lado quando o alvo é alto (mais
        de 45% da altura da janela), abaixo — ou acima, se não couber — quando
        é baixo. E nunca encostando na borda.
        """
        larg, alt = self.width(), self.height()
        passo = self._card_width
        altura = self._card.height() or CARD_HEIGHT_GUESS
        if alvo.isNull():
            return QPoint(max(MARGIN, (larg - passo) // 2),
                          max(MARGIN, (alt - altura) // 2))

        def limita(x: int, y: int) -> QPoint:
            return QPoint(
                min(max(x, MARGIN), max(MARGIN, larg - passo - MARGIN)),
                min(max(y, MARGIN), max(MARGIN, alt - altura - MARGIN)))

        if alvo.height() > alt * 0.45:
            # Alvo alto: o cartão vai para o lado.
            direita = alvo.right() + MARGIN
            if direita + passo + MARGIN <= larg:
                x = direita
            else:
                x = alvo.left() - passo - MARGIN
            y = alvo.top() + theme.space("10")
            if alvo.width() > larg * 0.55:
                # Alvo largo *e* alto: ocupa quase tudo; encaixa no canto.
                return limita(alvo.right() - passo,
                              alvo.bottom() - altura - theme.space("6"))
            return limita(x, y)

        abaixo = alvo.bottom() + theme.space("6")
        if abaixo + altura + MARGIN <= alt:
            return limita(alvo.left(), abaixo)
        return limita(alvo.left(), alvo.top() - altura - theme.space("6"))

    def _refresh(self, animate: bool = True) -> None:
        passo = self.current()
        if passo is None:
            return
        total = len(self._steps)
        self._progresso.set_progress(self._index, total)
        self._eyebrow.setText(
            f"{self._label} · {self._index + 1} / {total}".upper())
        self._titulo.setText(passo.title)
        self._texto.setText(passo.text)
        self._cartao_deck.setText(passo.card)
        self._cartao_deck.setVisible(bool(passo.card))
        self._b_voltar.setVisible(self._index > 0)
        self._refresh_waiting()
        self._fit_card_width()
        self._card.adjustSize()
        self._aim(animate)
        self._card.raise_()
        self.update()

    def _refresh_waiting(self) -> None:
        """A ação pendente e o rótulo do botão da direita."""
        passo = self.current()
        if passo is None:
            return
        esperando = self.waiting()
        ultimo = self._index + 1 >= len(self._steps)
        self._acao.setText(passo.action)
        self._acao_linha.setVisible(bool(passo.action) and esperando)
        if esperando:
            self._pulso.start()
        else:
            self._pulso.stop()
        # Esperando, o botão oferece pular — e perde o destaque, para a ação
        # continuar sendo o caminho principal.
        self._b_proximo.setText(
            "Pular" if esperando else ("Concluir" if ultimo else "Próximo"))
        theme.mark(self._b_proximo,
                   variant="ghost" if esperando else "primary")
        theme.restyle(self._b_proximo)

    # ── eventos ───────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - API do Qt
        if obj is self._host and event.type() in (QEvent.Type.Resize,
                                                  QEvent.Type.LayoutRequest):
            self.setGeometry(self._host.rect())
            if self.running:
                self._fit_card_width()
                self._card.adjustSize()
                self._aim(animate=False)
        return super().eventFilter(obj, event)

    def _update_mouse_transparency(self) -> None:
        """Com destaque em cena, a camada some para o mouse.

        É o ``pointer-events:none`` do arquivo de design: o clique vai direto
        ao widget destacado, que é onde a ação pedida acontece. Sem destaque,
        a camada bloqueia, porque não há o que fazer embaixo.

        Antes isto era feito ligando e desligando o atributo por 350 ms a cada
        clique; o primeiro clique só servia para abrir a passagem, e o usuário
        tinha de clicar várias vezes até acertar a janela de tempo.
        """
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          not self._rect.isNull())

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        """Só chega aqui quando não há destaque; aí a camada bloqueia."""
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if event.key() == Qt.Key.Key_Escape:
            self.stop()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return,
                             Qt.Key.Key_Enter):
            self.next()
        elif event.key() == Qt.Key.Key_Left:
            self.previous()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        escuro = QPainterPath()
        escuro.addRect(QRectF(self.rect()))
        if not self._rect.isNull():
            raio = float(theme.radius("md"))
            buraco = QPainterPath()
            buraco.addRoundedRect(QRectF(self._rect), raio, raio)
            escuro = escuro.subtracted(buraco)
        p.fillPath(escuro, theme.qcolor("scrim"))
        if not self._rect.isNull():
            p.setPen(QPen(theme.qcolor("accent"), 2))
            p.drawRoundedRect(QRectF(self._rect), float(theme.radius("md")),
                              float(theme.radius("md")))
        p.end()
