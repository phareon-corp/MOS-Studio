"""Peças da tela inicial: fundo do herói, cartão de receita e linha do fluxo."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ...core.library import Recipe
from ...core.preview import Preview
from .. import theme
from .common import label

#: Tokens trocados para desenhar sobre o herói escuro.
HERO_COLORS = {"bg": "hero-bg", "ink": "hero-ink", "ink-dim": "hero-ink-dim",
               "ink-faint": "hero-ink-dim", "line": "hero-line",
               "line-strong": "hero-border"}


class HeroBackground(QWidget):
    """Fundo do herói: grade fina e um brilho radial atrás do gráfico.

    O design faz isso com `background-image` em gradiente e `mask-image`;
    aqui é pintura direta, que é o que o Qt oferece.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.fillRect(r, theme.qcolor("hero-bg"))

        # grade de 80 px, esmaecida para as bordas
        passo = theme.space("20") * 2
        centro = QPointF(r.width() * 0.55, r.height() * 0.45)
        maior = max(r.width(), r.height())
        p.setPen(QPen(theme.qcolor("hero-line"), theme.dimension("border")))
        x = 0
        while x <= r.width():
            p.drawLine(QPointF(x, 0), QPointF(x, r.height()))
            x += passo
        y = 0
        while y <= r.height():
            p.drawLine(QPointF(0, y), QPointF(r.width(), y))
            y += passo

        # véu que apaga a grade longe do centro
        veu = QRadialGradient(centro, maior * 0.75)
        fundo = theme.qcolor("hero-bg")
        transparente = theme.qcolor("hero-bg")
        transparente.setAlpha(0)
        veu.setColorAt(0.0, transparente)
        veu.setColorAt(0.55, transparente)
        veu.setColorAt(1.0, fundo)
        p.fillRect(r, veu)

        # brilho do acento atrás do painel de pré-visualização
        brilho = QRadialGradient(QPointF(r.width() * 0.78, r.height() * 0.45),
                                 maior * 0.45)
        acento = theme.qcolor("accent")
        acento.setAlpha(40)
        apagado = theme.qcolor("accent")
        apagado.setAlpha(0)
        brilho.setColorAt(0.0, acento)
        brilho.setColorAt(1.0, apagado)
        p.fillRect(r, brilho)
        p.end()


class Sparkline(QWidget):
    """Traço do perfil no topo do cartão de receita."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._points: list[tuple[float, float]] = []
        self._active = False
        self.setFixedHeight(theme.space("24") * 2)

    def set_points(self, pontos: list[tuple[float, float]]) -> None:
        self._points = pontos
        self.update()

    def set_active(self, ativo: bool) -> None:
        self._active = ativo
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self._points) < 2:
            p.setPen(theme.qcolor("ink-faint"))
            p.setFont(theme.font("sans", "small"))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter),
                       "sem pré-visualização")
            p.end()
            return

        xs = [x for x, _ in self._points]
        ys = [max(abs(c), 1e10) for _, c in self._points]
        x_max = max(xs) or 1.0
        lo = math.floor(math.log10(min(ys)))
        hi = math.ceil(math.log10(max(ys)))
        if hi - lo < 2:
            hi = lo + 2
        margem = theme.space("4")
        largura = self.width()
        altura = self.height() - margem

        def px(x):
            return x / x_max * largura

        def py(c):
            v = math.log10(max(abs(c), 10.0 ** lo))
            return margem + (1 - (v - lo) / (hi - lo)) * (altura - margem)

        caminho = QPainterPath()
        for i, (x, c) in enumerate(self._points):
            ponto = QPointF(px(x), py(c))
            caminho.moveTo(ponto) if i == 0 else caminho.lineTo(ponto)

        area = QPainterPath(caminho)
        area.lineTo(QPointF(largura, self.height()))
        area.lineTo(QPointF(0, self.height()))
        area.closeSubpath()
        preenchimento = theme.qcolor("accent")
        preenchimento.setAlpha(40 if self._active else 15)
        p.fillPath(area, preenchimento)

        p.setPen(QPen(theme.qcolor("accent"), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(caminho)
        p.end()


class RecipeCard(QWidget):
    """Cartão de uma receita da biblioteca."""

    hovered = Signal(str)
    chosen = Signal(str)

    def __init__(self, recipe: Recipe, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.recipe = recipe
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setMinimumHeight(theme.space("24") * 6 + theme.space("16"))
        self.setAutoFillBackground(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, theme.space("11"))
        lay.setSpacing(theme.space("8"))

        self.spark = Sparkline()
        lay.addWidget(self.spark)

        miolo = QVBoxLayout()
        miolo.setContentsMargins(theme.space("13"), 0, theme.space("13"), 0)
        miolo.setSpacing(theme.space("8"))

        topo = QHBoxLayout()
        topo.setContentsMargins(0, 0, 0, 0)
        self._tag = label(recipe.tag.upper(), "eyebrow-accent")
        topo.addWidget(self._tag)
        topo.addStretch(1)
        self._seta = _ArrowBadge()
        topo.addWidget(self._seta)
        miolo.addLayout(topo)

        desc = label(recipe.description, "dim", wrap=True)
        miolo.addWidget(desc)
        miolo.addStretch(1)

        self._nome = label("", "title")
        self._nome.setTextFormat(Qt.TextFormat.RichText)
        self._nome.setText(
            f'<span>{recipe.name}</span> '
            f'<span style="font-family:\'{theme.resolve_family("serif")}\';'
            f'font-style:italic;color:{theme.color("ink-dim")}">'
            f'{recipe.emphasis}</span>')
        miolo.addWidget(self._nome)

        self._meta = label("", "eyebrow")
        miolo.addWidget(self._meta)
        lay.addLayout(miolo)
        self.set_preview(None)

    def set_preview(self, previa: Preview | None) -> None:
        """Preenche o traço e a linha de metadados com o perfil calculado."""
        n = self.recipe.step_count
        etapas = "1 ETAPA" if n == 1 else f"{n} ETAPAS"
        if previa is None:
            self.spark.set_points([])
            self._meta.setText(f"{etapas}      CALCULANDO…")
            return
        self.spark.set_points(previa.points)
        if previa.error:
            detalhe = "SEM PRÉ-VISUALIZAÇÃO"
        elif previa.junction is not None:
            detalhe = f"XJ {previa.junction:.3f} µM".replace(".", ",")
        elif previa.ok:
            detalhe = "SEM JUNÇÃO"
        else:
            detalhe = "SEM PERFIL"
        self._meta.setText(f"{etapas}      {detalhe}")

    def set_active(self, ativo: bool) -> None:
        self._active = ativo
        self.spark.set_active(ativo)
        self._seta.set_active(ativo)
        self.update()

    # ── interação ─────────────────────────────────────────────────────────

    def enterEvent(self, event) -> None:  # noqa: N802 - API do Qt
        self.hovered.emit(self.recipe.key)
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self.chosen.emit(self.recipe.key)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.fillRect(self.rect(),
                   theme.qcolor("bg-2" if self._active else "bg"))
        # linha sob o traço, como no design
        y = self.spark.geometry().bottom()
        p.fillRect(QRect(0, y, self.width(), theme.dimension("border")),
                   theme.qcolor("line"))
        p.end()


class _ArrowBadge(QWidget):
    """Círculo com a seta diagonal, que se endireita quando o cartão acende."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setFixedSize(theme.space("16") + theme.space("2"),
                          theme.space("16") + theme.space("2"))

    def set_active(self, ativo: bool) -> None:
        self._active = ativo
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._active:
            p.setBrush(theme.qcolor("ink"))
            p.setPen(QPen(theme.qcolor("ink"), 1))
            tinta = theme.qcolor("bg")
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(theme.qcolor("line-strong"), 1))
            tinta = theme.qcolor("ink-dim")
        p.drawEllipse(r)
        p.save()
        p.translate(r.center())
        if not self._active:
            p.rotate(45)
        p.setPen(QPen(tinta, 1.5))
        braco = theme.space("4")
        p.drawLine(QPointF(-braco, braco), QPointF(braco, -braco))
        p.drawLine(QPointF(0, -braco), QPointF(braco, -braco))
        p.drawLine(QPointF(braco, 0), QPointF(braco, -braco))
        p.restore()
        p.end()


class FlowStep(QWidget):
    """Um dos quatro passos do fluxo, sob o herói."""

    entered = Signal(int)

    def __init__(self, indice: int, numero: str, titulo: str, descricao: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._indice = indice
        self._ativo = False
        self.setMouseTracking(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, theme.space("11"), theme.space("11"),
                               theme.space("14"))
        lay.setSpacing(theme.space("4"))
        self._numero = label(numero, "eyebrow")
        self._titulo = label(titulo, "title")
        self._titulo.setFont(theme.font("display", "title", "medium", "tight"))
        desc = label(descricao, "dim", wrap=True)
        desc.setMaximumWidth(theme.space("24") * 7)
        for w in (self._numero, self._titulo, desc):
            lay.addWidget(w)
        lay.addStretch(1)

    def set_active(self, ativo: bool) -> None:
        self._ativo = ativo
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - API do Qt
        self.entered.emit(self._indice)
        super().enterEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        p = QPainter(self)
        if self._ativo:
            p.fillRect(QRect(0, 0, self.width(), 2), theme.qcolor("accent"))
        p.end()
