"""Gráficos do dispositivo: a curva I-V, os mapas 2-D e a superfície 3-D.

O MINIMOS escreve os campos numa grade estruturada (o PIF), mas o visualizador
externo que os desenhava (``plotmtv``) não existe mais. Aqui a grade é pintada
direto, sem intermediário — de duas formas: o mapa, visto de cima, e a
superfície, vista em perspectiva, que era o que o app antigo mostrava com o
``plot_surface`` do matplotlib.

A escala de cor é divergente e vem dos tokens do tema, de modo que os dois
desenhos usem a mesma leitura e troquem de paleta junto com o resto da
interface.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import theme


def _mistura(a: QColor, b: QColor, t: float) -> QColor:
    """Interpola duas cores; ``t`` vai de 0 (a) a 1 (b)."""
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def cor_divergente(t: float) -> QColor:
    """Cor da escala divergente dos mapas, com ``t`` de -1 a +1.

    Dois polos e um meio neutro, nunca uma matiz no meio e nunca um arco-íris:
    os campos do MINIMOS têm sinal, e o zero quer dizer alguma coisa — a
    fronteira da região de depleção, o ponto onde o campo inverte.

    A escala anterior ia de ``nfill`` a ``accent``. Os dois têm o **mesmo**
    RGB (``nfill`` é o accent com alfa 77), e ``_mistura`` descarta o alfa:
    o mapa inteiro saía de uma cor só, um retângulo laranja chapado.
    """
    t = max(-1.0, min(1.0, t))
    meio = theme.qcolor("field-mid")
    polo = theme.qcolor("field-pos" if t >= 0 else "field-neg")
    return _mistura(meio, polo, abs(t))


def _fmt(v: float) -> str:
    """Número curto, com vírgula decimal, para rótulo de eixo."""
    if v == 0:
        return "0"
    if abs(v) >= 1e4 or abs(v) < 1e-3:
        return f"{v:.1E}".replace(".", ",")
    return f"{v:.3g}".replace(".", ",")


class IVChart(QWidget):
    """Curva I-V: uma ou mais varreduras, eixo de corrente linear.

    O design desenha a área sob a curva com um gradiente suave e uma transição
    ao trocar de curva; o Qt não anima QSS, então aqui a área é um
    preenchimento sólido translúcido e a troca é instantânea — anotado em
    ``docs/fidelidade-visual.md``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._curvas: list[tuple[str, list[tuple[float, float]]]] = []
        self._xlabel = ""
        self._ylabel = "ID (A)"
        self._vazio = "Rode a simulação para ver a curva"
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_curves(self, curvas, xlabel: str = "", ylabel: str = "ID (A)"
                   ) -> None:
        self._curvas = [(n, list(p)) for n, p in curvas if p]
        self._xlabel, self._ylabel = xlabel, ylabel
        self.update()

    def set_empty_message(self, texto: str) -> None:
        self._vazio = texto
        self.update()

    def clear(self) -> None:
        self._curvas = []
        self.update()

    def has_data(self) -> bool:
        return bool(self._curvas)

    def paintEvent(self, event) -> None:          # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("bg-2"))
        if not self._curvas:
            p.setPen(QPen(theme.qcolor("ink-faint")))
            p.setFont(theme.font("sans", "small"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._vazio)
            p.end()
            return

        xs = [x for _, pts in self._curvas for x, _ in pts]
        ys = [y for _, pts in self._curvas for _, y in pts]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(0.0, min(ys)), max(ys)
        if x1 == x0:
            x1 = x0 + 1.0
        if y1 == y0:
            y1 = y0 + 1e-12
        folga = (y1 - y0) * 0.1
        y1 += folga

        # A margem da esquerda é medida, não fixa. Uma corrente de dreno sai
        # em notação científica ("3,6E-05"), e com margem fixa o rótulo é
        # cortado pela borda do gráfico — some justamente a ordem de grandeza,
        # que é o que interessa ler.
        p.setFont(theme.font("mono", "micro"))
        rotulos_y = [_fmt(y0 + (y1 - y0) * i / 4) for i in range(5)]
        m_esq = max(theme.space("16"),
                    max(p.fontMetrics().horizontalAdvance(r)
                        for r in rotulos_y) + theme.space("6"))
        m_dir = theme.space("8")
        m_topo, m_base = theme.space("8"), theme.space("14")
        larg = self.width() - m_esq - m_dir
        alt = self.height() - m_topo - m_base
        if larg <= 10 or alt <= 10:
            p.end()
            return

        def px(x): return m_esq + (x - x0) / (x1 - x0) * larg
        def py(y): return m_topo + alt - (y - y0) / (y1 - y0) * alt

        p.setPen(QPen(theme.qcolor("line"), theme.dimension("border")))
        for i in range(5):
            yy = m_topo + alt * i / 4
            p.drawLine(int(m_esq), int(yy), int(m_esq + larg), int(yy))
        p.setPen(QPen(theme.qcolor("line-strong"), theme.dimension("border")))
        p.drawLine(int(m_esq), int(m_topo + alt), int(m_esq + larg),
                   int(m_topo + alt))
        p.drawLine(int(m_esq), int(m_topo), int(m_esq), int(m_topo + alt))

        p.setFont(theme.font("mono", "micro"))
        p.setPen(QPen(theme.qcolor("ink-faint")))
        for i in range(5):
            v = x0 + (x1 - x0) * i / 4
            # Os números do eixo ficam logo abaixo da linha; a faixa de
            # baixo (m_base) é dividida entre eles e o nome do eixo, sem as
            # duas coisas se sobreporem.
            p.drawText(int(px(v) - 30), int(m_topo + alt + theme.space("2")),
                       60, theme.space("6"), Qt.AlignmentFlag.AlignCenter,
                       _fmt(v))
            v = y0 + (y1 - y0) * i / 4
            p.drawText(0, int(py(v) - theme.space("4")),
                       m_esq - theme.space("3"), theme.space("8"),
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter, _fmt(v))
        p.setFont(theme.font("mono", "micro", "medium", "wide"))
        p.setPen(QPen(theme.qcolor("ink-dim")))
        if self._xlabel:
            p.drawText(int(m_esq), int(self.height() - theme.space("6")),
                       larg, theme.space("6"), Qt.AlignmentFlag.AlignCenter,
                       self._xlabel)

        cores = ("accent", "ink", "amber", "al")
        for i, (_nome, pts) in enumerate(self._curvas):
            cor = theme.qcolor(cores[i % len(cores)])
            p.setPen(QPen(cor, 2))
            anterior = None
            for x, y in pts:
                atual = (px(x), py(y))
                if anterior is not None:
                    p.drawLine(int(anterior[0]), int(anterior[1]),
                               int(atual[0]), int(atual[1]))
                anterior = atual
            r = theme.space("2")
            p.setBrush(cor)
            for x, y in pts:
                p.drawEllipse(int(px(x) - r / 2), int(py(y) - r / 2), r, r)
            p.setBrush(Qt.BrushStyle.NoBrush)
        p.end()


class FieldMap(QWidget):
    """Mapa 2-D de um campo físico sobre a grade do MINIMOS.

    Pinta a grade estruturada célula por célula. A grade do motor não é
    uniforme (é mais fina perto da superfície e dos contatos), então cada
    célula é desenhada com a largura que lhe cabe em vez de uma imagem
    reamostrada — assim o refinamento aparece em vez de se perder.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lat: list[float] = []
        self._vert: list[float] = []
        self._vals: list[float] = []
        self._titulo = ""
        self._log = False
        self._vazio = "Rode a simulação no modo de mapas"
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_field(self, lat, vert, valores, titulo: str = "",
                  log: bool = False) -> None:
        self._lat, self._vert = list(lat), list(vert)
        self._vals, self._titulo, self._log = list(valores), titulo, log
        self.update()

    def clear(self) -> None:
        self._lat, self._vert, self._vals, self._titulo = [], [], [], ""
        self.update()

    def has_data(self) -> bool:
        return bool(self._lat and self._vert and self._vals)

    def _escala(self) -> tuple[float, float]:
        """``(lo, hi)`` da escala de cor.

        Quando o campo tem os dois sinais, a escala é simétrica em torno do
        zero: senão o meio neutro cairia fora do zero e o mapa mentiria sobre
        onde o campo inverte.
        """
        vs = [v for v in self._vals if v is not None]
        if self._log:
            vs = [math.log10(abs(v)) for v in vs if v]
        if not vs:
            return 0.0, 1.0
        lo, hi = min(vs), max(vs)
        if not self._log and lo < 0.0 < hi:
            extremo = max(abs(lo), abs(hi))
            return (-extremo, extremo)
        return (lo, hi if hi > lo else lo + 1.0)

    def _divergente(self) -> bool:
        """``True`` quando a escala tem dois polos em torno do zero."""
        lo, hi = self._escala()
        return not self._log and lo < 0.0 < hi

    def _cor(self, v: float, lo: float, hi: float) -> QColor:
        """A cor de um valor, na escala que este campo pede."""
        if self._divergente():
            return cor_divergente(v / hi if hi else 0.0)
        t = (v - lo) / (hi - lo) if hi > lo else 0.0
        return _mistura(theme.qcolor("bg-3"), theme.qcolor("field-pos"), t)

    def paintEvent(self, event) -> None:          # noqa: N802 - API do Qt
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qcolor("bg-2"))
        m_esq, m_dir = theme.space("14"), theme.space("12")
        m_topo, m_base = theme.space("8"), theme.space("12")
        larg = self.width() - m_esq - m_dir
        alt = self.height() - m_topo - m_base
        nl, nv = len(self._lat), len(self._vert)
        if larg <= 10 or alt <= 10 or not self.has_data() or nl < 2 or nv < 2:
            p.setPen(QPen(theme.qcolor("ink-faint")))
            p.setFont(theme.font("sans", "small"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._vazio)
            p.end()
            return

        x0, x1 = min(self._lat), max(self._lat)
        y0, y1 = min(self._vert), max(self._vert)
        lo, hi = self._escala()

        def px(x): return m_esq + (x - x0) / (x1 - x0) * larg
        def py(y): return m_topo + (y - y0) / (y1 - y0) * alt

        for iv in range(nv - 1):
            for il in range(nl - 1):
                idx = iv * nl + il
                if idx >= len(self._vals):
                    continue
                v = self._vals[idx]
                if self._log:
                    v = math.log10(abs(v)) if v else lo
                xa, xb = px(self._lat[il]), px(self._lat[il + 1])
                ya, yb = py(self._vert[iv]), py(self._vert[iv + 1])
                p.fillRect(int(xa), int(ya),
                           max(1, int(xb) - int(xa) + 1),
                           max(1, int(yb) - int(ya) + 1),
                           self._cor(v, lo, hi))

        p.setPen(QPen(theme.qcolor("line-strong"), theme.dimension("border")))
        p.drawRect(int(m_esq), int(m_topo), int(larg), int(alt))

        # barra de cor
        bx = m_esq + larg + theme.space("3")
        bw = theme.space("3")
        for i in range(int(alt)):
            t = 1.0 - i / max(1, alt - 1)
            p.setPen(QPen(self._cor(lo + t * (hi - lo), lo, hi)))
            p.drawLine(int(bx), int(m_topo + i), int(bx + bw), int(m_topo + i))
        if self._divergente():
            # Marca o zero na barra: é a leitura que o mapa oferece.
            zero = m_topo + alt * (hi / (hi - lo))
            p.setPen(QPen(theme.qcolor("ink-dim"), 1))
            p.drawLine(int(bx), int(zero), int(bx + bw), int(zero))
            p.setFont(theme.font("mono", "micro"))
            p.drawText(int(bx - theme.space("12")),
                       int(zero - theme.space("3")), theme.space("11"),
                       theme.space("5"), Qt.AlignmentFlag.AlignRight, "0")

        p.setFont(theme.font("mono", "micro"))
        p.setPen(QPen(theme.qcolor("ink-faint")))
        # em escala log os extremos são expoentes; mostramos a potência
        def rotulo(v: float) -> str:
            return f"1e{v:.1f}".replace(".", ",") if self._log else _fmt(v)

        p.drawText(int(bx - theme.space("12")), int(m_topo),
                   theme.space("11"), theme.space("5"),
                   Qt.AlignmentFlag.AlignRight, rotulo(hi))
        p.drawText(int(bx - theme.space("12")),
                   int(m_topo + alt - theme.space("5")),
                   theme.space("11"), theme.space("5"),
                   Qt.AlignmentFlag.AlignRight, rotulo(lo))
        p.drawText(int(m_esq), int(m_topo + alt + theme.space("4")),
                   int(larg), theme.space("5"),
                   Qt.AlignmentFlag.AlignCenter,
                   f"lateral {_fmt(x0)} a {_fmt(x1)} µm  ·  "
                   f"profundidade até {_fmt(y1)} µm")
        if self._titulo:
            p.setFont(theme.font("mono", "micro", "medium", "wide"))
            p.setPen(QPen(theme.qcolor("ink-dim")))
            p.drawText(int(m_esq), int(theme.space("2")), int(larg),
                       theme.space("6"), Qt.AlignmentFlag.AlignLeft,
                       self._titulo.upper())
        p.end()


class SurfacePlot(QWidget):
    """A superfície 3-D de um campo sobre a seção do dispositivo.

    É o gráfico que o app antigo desenhava com o ``plot_surface`` do
    matplotlib e que se perdeu na migração. Aqui não há matplotlib: a grade do
    PIF é projetada e pintada quadrilátero a quadrilátero, de trás para a
    frente (algoritmo do pintor), com a mesma escala divergente do mapa 2-D.

    Ver em perspectiva mostra o que o mapa visto de cima esconde — a altura
    da barreira no canal, a inclinação do potencial ao longo do canal, o pico
    do campo na borda do dreno.

    Arrastar gira; a roda aproxima.
    """

    #: Limites da elevação, em graus. Acima de ~85° a superfície vira o mapa
    #: 2-D e o desenho perde a razão de ser; abaixo de ~5° ela some de perfil.
    MIN_ELEV, MAX_ELEV = 5.0, 85.0

    #: Quantos quadriláteros, no máximo, por eixo. Acima disto o desenho fica
    #: lento sem ganhar leitura — a grade do MINIMOS tem 23×33.
    MAX_QUADS = 64

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lat: list[float] = []
        self._vert: list[float] = []
        self._vals: list[float] = []
        self._titulo = ""
        self._az = 35.0          # azimute, graus
        self._elev = 28.0        # elevação, graus
        self._zoom = 1.0
        self._malha = True
        self._arrasto: QPointF | None = None
        self._vazio = "Rode a simulação no modo de mapas"
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── dados ─────────────────────────────────────────────────────────────

    def set_field(self, lat, vert, valores, titulo: str = "") -> None:
        self._lat, self._vert = list(lat), list(vert)
        self._vals, self._titulo = list(valores), titulo
        self.update()

    def clear(self) -> None:
        self._lat, self._vert, self._vals, self._titulo = [], [], [], ""
        self.update()

    def has_data(self) -> bool:
        return bool(self._lat and self._vert and self._vals)

    def set_wireframe(self, ligado: bool) -> None:
        self._malha = ligado
        self.update()

    def set_view(self, azimute: float, elevacao: float) -> None:
        self._az = azimute % 360.0
        self._elev = min(max(elevacao, self.MIN_ELEV), self.MAX_ELEV)
        self.update()

    def view(self) -> tuple[float, float]:
        return (self._az, self._elev)

    def reset_view(self) -> None:
        self._az, self._elev, self._zoom = 35.0, 28.0, 1.0
        self.update()

    # ── interação ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:        # noqa: N802 - API do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._arrasto = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:         # noqa: N802 - API do Qt
        if self._arrasto is None:
            return
        delta = event.position() - self._arrasto
        self._arrasto = event.position()
        self.set_view(self._az + delta.x() * 0.4,
                      self._elev - delta.y() * 0.3)

    def mouseReleaseEvent(self, event) -> None:      # noqa: N802 - API do Qt
        self._arrasto = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event) -> None:             # noqa: N802 - API do Qt
        passos = event.angleDelta().y() / 120.0
        self._zoom = min(max(self._zoom * (1.1 ** passos), 0.4), 3.0)
        self.update()

    # ── projeção ──────────────────────────────────────────────────────────

    def _escala(self) -> tuple[float, float]:
        """``(lo, hi)`` do campo, simétrico em torno do zero quando há sinal."""
        vs = [v for v in self._vals if v is not None]
        if not vs:
            return 0.0, 1.0
        lo, hi = min(vs), max(vs)
        if lo < 0.0 < hi:
            extremo = max(abs(lo), abs(hi))
            return (-extremo, extremo)
        return (lo, hi if hi > lo else lo + 1.0)

    def _indices(self, n: int) -> list[int]:
        """Índices de uma amostragem que preserva as pontas."""
        if n <= self.MAX_QUADS + 1:
            return list(range(n))
        passo = (n - 1) / float(self.MAX_QUADS)
        saida = sorted({int(round(i * passo)) for i in range(self.MAX_QUADS + 1)})
        if saida[-1] != n - 1:
            saida.append(n - 1)
        return saida

    def paintEvent(self, event) -> None:             # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("bg-2"))

        if not self.has_data() or len(self._lat) < 2 or len(self._vert) < 2:
            p.setPen(QPen(theme.qcolor("ink-faint")))
            p.setFont(theme.font("sans", "small"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._vazio)
            p.end()
            return

        nl, nv = len(self._lat), len(self._vert)
        ils, ivs = self._indices(nl), self._indices(nv)
        lo, hi = self._escala()
        span = (hi - lo) or 1.0
        x0, x1 = min(self._lat), max(self._lat)
        y0, y1 = min(self._vert), max(self._vert)
        larg_um = (x1 - x0) or 1.0
        prof_um = (y1 - y0) or 1.0

        ca, sa = math.cos(math.radians(self._az)), math.sin(math.radians(self._az))
        ce, se = (math.cos(math.radians(self._elev)),
                  math.sin(math.radians(self._elev)))
        #: Quanto a altura do campo pesa em relação à base, antes do
        #: enquadramento. É a proporção do gráfico, não o tamanho dele.
        relevo = 0.8

        def bruto(il: int, iv: int) -> tuple[float, float, float]:
            """Coordenadas projetadas antes de escalar, mais a profundidade."""
            u = (self._lat[il] - x0) / larg_um - 0.5
            v = (self._vert[iv] - y0) / prof_um - 0.5
            idx = iv * nl + il
            valor = self._vals[idx] if idx < len(self._vals) else lo
            h = ((valor - lo) / span - 0.5) * relevo
            dx = u * ca - v * sa
            dy = u * sa + v * ca
            return (dx, dy * se - h, dy * ce)

        # Enquadra pela projeção, não por uma constante: o desenho muda de
        # tamanho com o ângulo, e uma escala fixa deixava a vista de lado
        # ocupando um quinto da área disponível.
        cantos = [bruto(il, iv) for iv in ivs for il in ils]
        bx0 = min(c[0] for c in cantos)
        bx1 = max(c[0] for c in cantos)
        by0 = min(c[1] for c in cantos)
        by1 = max(c[1] for c in cantos)
        margem = theme.space("12")
        util_l = max(1.0, self.width() - 2 * margem)
        util_a = max(1.0, self.height() - 2 * margem - theme.space("12"))
        escala = min(util_l / max(bx1 - bx0, 1e-6),
                     util_a / max(by1 - by0, 1e-6)) * self._zoom
        cx = self.width() / 2.0 - (bx0 + bx1) / 2.0 * escala
        cy = self.height() / 2.0 - (by0 + by1) / 2.0 * escala

        def projetar(il: int, iv: int) -> tuple[QPointF, float]:
            """Ponto na tela e a profundidade, para ordenar o desenho."""
            dx, dy, prof = bruto(il, iv)
            return (QPointF(cx + dx * escala, cy + dy * escala), prof)

        # Algoritmo do pintor: o que está atrás é desenhado antes.
        faces = []
        for a in range(len(ivs) - 1):
            for b in range(len(ils) - 1):
                iv0, iv1 = ivs[a], ivs[a + 1]
                il0, il1 = ils[b], ils[b + 1]
                cantos = [projetar(il0, iv0), projetar(il1, iv0),
                          projetar(il1, iv1), projetar(il0, iv1)]
                prof = sum(c[1] for c in cantos) / 4.0
                idx = iv0 * nl + il0
                valor = self._vals[idx] if idx < len(self._vals) else lo
                faces.append((prof, [c[0] for c in cantos], valor))
        faces.sort(key=lambda f: f[0])

        caneta = (QPen(theme.qcolor("line"), 0.5) if self._malha
                  else Qt.PenStyle.NoPen)
        for _prof, cantos, valor in faces:
            cor = cor_divergente(valor / hi if hi else 0.0) if lo < 0 < hi \
                else _mistura(theme.qcolor("bg-3"), theme.qcolor("field-pos"),
                              (valor - lo) / span)
            p.setBrush(cor)
            p.setPen(caneta)
            p.drawPolygon(QPolygonF(cantos))

        self._desenhar_legenda(p, lo, hi)
        p.end()

    def _desenhar_legenda(self, p: QPainter, lo: float, hi: float) -> None:
        """Título, extremos e a dica de como girar."""
        p.setFont(theme.font("mono", "micro", "medium", "wide"))
        p.setPen(QPen(theme.qcolor("ink-dim")))
        if self._titulo:
            p.drawText(theme.space("8"), theme.space("8"),
                       self._titulo.upper())
        p.setFont(theme.font("mono", "micro"))
        p.setPen(QPen(theme.qcolor("ink-faint")))
        p.drawText(theme.space("8"), theme.space("14"),
                   f"de {_fmt(lo)} a {_fmt(hi)}")
        p.drawText(theme.space("8"), self.height() - theme.space("6"),
                   f"arraste para girar · roda aproxima · "
                   f"azimute {self._az:.0f}° · elevação {self._elev:.0f}°")
