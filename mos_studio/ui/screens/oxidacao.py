"""Tela de Oxidação: medir Deal-Grove no próprio motor.

O experimento é o do laboratório: oxida-se o mesmo silício por vários tempos,
mede-se a espessura de cada corrida e ajusta-se ``t/Xo = (1/B)·Xo + A/B``. O
gráfico é essa linearização — se o ajuste é bom, os pontos caem sobre a reta, e
é isso que o R² ao lado mede.

As constantes de literatura ficam à vista para comparação, não para substituir
a medida: o que o app mostra como B e B/A vem sempre das corridas.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QScrollArea,
                               QSizePolicy, QSplitter, QVBoxLayout, QWidget)

from ...core import oxidation
from ...core.recipe import Field, fmt_number, parse_float
from .. import theme
from ..widgets.common import (button, eyebrow, hline, label, row, stretch)
from ..widgets.error_panel import EngineErrorPanel
from ..widgets.step_form import FieldRow

#: Constantes de Deal-Grove da literatura (Deal & Grove 1965), para comparar.
#: ``B`` em µm²/h e ``B/A`` em µm/h, em silício (100).
LITERATURA = {
    ("WETO2", 1000): (0.287, 0.715),
    ("WETO2", 1100): (0.510, 4.640),
    ("WETO2", 1200): (0.720, 14.40),
    ("DRYO2", 1000): (0.0117, 0.0710),
    ("DRYO2", 1100): (0.0270, 0.300),
    ("DRYO2", 1200): (0.0450, 1.120),
}

#: Tempos com que a tela abre — cobrem o regime linear e o parabólico.
TEMPOS_PADRAO = "10, 30, 60, 120, 240"

CAMPOS = [
    Field("temperature", "Temperatura", "number", unit="°C",
          minimum=700, maximum=1250,
          help="Deal-Grove foi medido entre 700 e 1200 °C."),
    Field("doping", "Dopagem do substrato", "number", unit="cm⁻³",
          help="Dopagem alta acelera a oxidação; o motor leva isso em conta."),
    Field("times", "Tempos de oxidação", "text", unit="min", wide=True,
          help="Separados por vírgula ou espaço; use vírgula entre dígitos "
               "para decimal (0,5). Cada tempo é uma corrida do motor."),
]


class _SweepWorker(QThread):
    """Roda a varredura fora da interface, um ponto por vez."""

    point = Signal(int, object)
    finished_sweep = Signal(object)

    def __init__(self, tempos, params, parent=None) -> None:
        super().__init__(parent)
        self._tempos = tempos
        self._params = params
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:          # noqa: D102 - API do QThread
        r = oxidation.sweep(self._tempos,
                            on_point=lambda i, p: self.point.emit(i, p),
                            should_stop=lambda: self._stop, **self._params)
        self.finished_sweep.emit(r)


class DealGroveChart(QWidget):
    """A linearização de Deal-Grove: t/Xo contra Xo, com a reta do ajuste.

    O design mostra sombra sob a área do gráfico e transição ao entrar; o Qt
    não tem nenhum dos dois em QSS, então aqui há só a linha e os pontos —
    a divergência está anotada em ``docs/fidelidade-visual.md``.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pontos: list[tuple[float, float]] = []
        self._fit: dict[str, float] = {}
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)

    def set_sweep(self, sweep) -> None:
        validos = sweep.valid() if sweep else []
        self._pontos = [(p.thickness_um, p.time_min / p.thickness_um)
                        for p in validos if p.thickness_um]
        self._fit = dict(sweep.fit) if sweep and sweep.fit else {}
        self.update()

    def clear(self) -> None:
        self._pontos, self._fit = [], {}
        self.update()

    def paintEvent(self, event) -> None:      # noqa: N802 - API do Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), theme.qcolor("bg-2"))
        m_esq, m_dir = theme.space("16"), theme.space("8")
        m_topo, m_base = theme.space("8"), theme.space("14")
        larg = self.width() - m_esq - m_dir
        alt = self.height() - m_topo - m_base
        if larg <= 10 or alt <= 10:
            p.end()
            return

        if not self._pontos:
            p.setPen(QPen(theme.qcolor("ink-faint")))
            p.setFont(theme.font("sans", "small"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Rode a varredura para medir B e A")
            p.end()
            return

        xs = [x for x, _ in self._pontos]
        ys = [y for _, y in self._pontos]
        x0, x1 = 0.0, max(xs) * 1.15
        y0, y1 = 0.0, max(ys) * 1.15
        if x1 <= x0 or y1 <= y0:
            p.end()
            return

        def px(x): return m_esq + (x - x0) / (x1 - x0) * larg
        def py(y): return m_topo + alt - (y - y0) / (y1 - y0) * alt

        # grade e eixos
        p.setPen(QPen(theme.qcolor("line"), theme.dimension("border")))
        for i in range(5):
            yy = m_topo + alt * i / 4
            p.drawLine(int(m_esq), int(yy), int(m_esq + larg), int(yy))
        p.setPen(QPen(theme.qcolor("line-strong"), theme.dimension("border")))
        p.drawLine(int(m_esq), int(m_topo + alt), int(m_esq + larg),
                   int(m_topo + alt))
        p.drawLine(int(m_esq), int(m_topo), int(m_esq), int(m_topo + alt))

        # marcações
        p.setFont(theme.font("mono", "micro"))
        p.setPen(QPen(theme.qcolor("ink-faint")))
        for i in range(5):
            v = x0 + (x1 - x0) * i / 4
            p.drawText(int(px(v) - 24), int(m_topo + alt + theme.space("6")),
                       48, theme.space("6"), Qt.AlignmentFlag.AlignCenter,
                       f"{v:.2f}".replace(".", ","))
            v = y0 + (y1 - y0) * i / 4
            p.drawText(0, int(py(v) - theme.space("4")),
                       m_esq - theme.space("3"), theme.space("8"),
                       Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignVCenter,
                       f"{v:.0f}")
        p.setFont(theme.font("mono", "micro", "medium", "wide"))
        p.setPen(QPen(theme.qcolor("ink-dim")))
        p.drawText(int(m_esq), int(self.height() - theme.space("5")),
                   larg, theme.space("5"), Qt.AlignmentFlag.AlignCenter,
                   "Xo (µm)")

        # reta do ajuste: y = (1/B)·x + A/B
        if self._fit:
            m, c = self._fit.get("m", 0.0), self._fit.get("c", 0.0)
            pen = QPen(theme.qcolor("accent"), 2)
            p.setPen(pen)
            p.drawLine(int(px(x0)), int(py(m * x0 + c)),
                       int(px(x1)), int(py(m * x1 + c)))

        # pontos medidos
        r = theme.space("3")
        for x, y in self._pontos:
            p.setPen(QPen(theme.qcolor("bg-2"), 2))
            p.setBrush(theme.qcolor("ink"))
            p.drawEllipse(int(px(x) - r / 2), int(py(y) - r / 2), r, r)
        p.end()


class OxidationScreen(QWidget):
    """A tela inteira de Oxidação."""

    run_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.params = {"ambient": "WETO2", "temperature": "1000",
                       "orientation": "100", "doping": "1E15",
                       "times": TEMPOS_PADRAO}
        self.sweep: oxidation.OxidationSweep | None = None
        self._worker: _SweepWorker | None = None

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(self._splitter)
        self._splitter.addWidget(self._build_params())
        self._splitter.addWidget(self._build_center())
        self._splitter.setSizes([theme.dimension("sidebar-width"), 720])
        self._splitter.setStretchFactor(1, 1)
        self._refresh_literature()

    # ── painel de parâmetros ──────────────────────────────────────────────

    def _build_params(self) -> QWidget:
        painel = QWidget()
        theme.mark(painel, surface="sidebar")
        painel.setMinimumWidth(theme.dimension("sidebar-width")
                               - theme.space("20"))
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cabeca = QWidget()
        hl = QVBoxLayout(cabeca)
        hl.setContentsMargins(theme.space("8"), theme.space("8"),
                              theme.space("8"), theme.space("6"))
        hl.setSpacing(theme.space("3"))
        hl.addWidget(eyebrow("experimento", True))
        hl.addWidget(label("Deal-Grove", "title"))
        sub = label("Cada tempo é uma corrida do SUPREM; o ajuste sai das "
                    "espessuras medidas.", wrap=True)
        theme.mark(sub, role="muted")
        hl.addWidget(sub)
        lay.addWidget(cabeca)
        lay.addWidget(hline())

        corpo = QWidget()
        cl = QVBoxLayout(corpo)
        cl.setContentsMargins(theme.space("8"), theme.space("7"),
                              theme.space("8"), theme.space("7"))
        cl.setSpacing(theme.space("7"))

        cl.addWidget(self._seg_row("Ambiente", "ambient",
                                   [("WETO2", "Úmido"), ("DRYO2", "Seco"),
                                    ("STEAM", "Vapor")]))
        cl.addWidget(self._seg_row("Orientação", "orientation",
                                   [("100", "(100)"), ("111", "(111)")]))
        self._rows: dict[str, FieldRow] = {}
        for campo in CAMPOS:
            fr = FieldRow(campo, self.params.get(campo.key, ""))
            fr.changed.connect(self._on_param)
            self._rows[campo.key] = fr
            cl.addWidget(fr)

        cl.addWidget(hline())
        self._lit = label("", wrap=True)
        theme.mark(self._lit, role="muted")
        self._lit.setFont(theme.font("mono", "micro"))
        cl.addWidget(eyebrow("literatura"))
        cl.addWidget(self._lit)
        cl.addStretch(1)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        rolagem.setWidget(corpo)
        lay.addWidget(rolagem, 1)

        lay.addWidget(hline())
        acoes = QWidget()
        al = QHBoxLayout(acoes)
        al.setContentsMargins(theme.space("8"), theme.space("6"),
                              theme.space("8"), theme.space("6"))
        al.setSpacing(theme.space("4"))
        self._btn_run = button("Rodar varredura", "primary",
                               on_click=self._start)
        self._btn_run.setFixedHeight(theme.dimension("button-lg"))
        al.addWidget(self._btn_run, 1)
        self._btn_stop = button("Parar", "ghost", on_click=self._stop)
        self._btn_stop.setFixedHeight(theme.dimension("button-lg"))
        self._btn_stop.setVisible(False)
        al.addWidget(self._btn_stop)
        lay.addWidget(acoes)
        return painel

    def _seg_row(self, titulo: str, chave: str,
                 opcoes: list[tuple[str, str]]) -> QWidget:
        from ..widgets.common import Segmented
        cab = label(titulo)
        cab.setFont(theme.font("sans", "base", "medium"))
        seg = Segmented(opcoes, self.params.get(chave, ""))
        seg.changed.connect(lambda _i, c=chave, s=seg:
                            self._on_param(c, s.value()))
        host = QWidget()
        vl = QVBoxLayout(host)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(theme.space("4"))
        vl.addWidget(cab)
        vl.addWidget(seg)
        return host

    # ── centro: métricas, gráfico e tabela ────────────────────────────────

    def _build_center(self) -> QWidget:
        painel = QWidget()
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.erro = EngineErrorPanel()
        lay.addWidget(self.erro)

        metricas = QWidget()
        theme.mark(metricas, surface="raised")
        ml = QHBoxLayout(metricas)
        ml.setContentsMargins(theme.space("10"), theme.space("8"),
                              theme.space("10"), theme.space("8"))
        ml.setSpacing(theme.space("10"))
        self._metricas: dict[str, tuple] = {}
        for chave, titulo, unidade in (("B_h", "B", "µm²/h"),
                                       ("A", "A", "µm"),
                                       ("BA_h", "B/A", "µm/h"),
                                       ("r2", "R²", "")):
            bloco = QWidget()
            bl = QVBoxLayout(bloco)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(theme.space("2"))
            bl.addWidget(eyebrow(titulo))
            valor = label("—", "metric")
            bl.addWidget(valor)
            un = label(unidade, "unit")
            bl.addWidget(un)
            ml.addWidget(bloco)
            self._metricas[chave] = (valor, un)
        ml.addStretch(1)
        lay.addWidget(metricas)
        lay.addWidget(hline())

        self.chart = DealGroveChart()
        lay.addWidget(self.chart, 1)
        lay.addWidget(hline())

        rodape = QWidget()
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(theme.space("10"), theme.space("5"),
                              theme.space("10"), theme.space("5"))
        rl.setSpacing(theme.space("5"))
        self._andamento = label("")
        theme.mark(self._andamento, role="muted")
        self._andamento.setFont(theme.font("mono", "micro"))
        rl.addWidget(self._andamento)
        rl.addWidget(stretch())
        self._btn_csv = button("Exportar CSV", "small", on_click=self._csv)
        self._btn_csv.setEnabled(False)
        rl.addWidget(self._btn_csv)
        lay.addWidget(rodape)
        lay.addWidget(hline())

        self.tabela = QWidget()
        theme.mark(self.tabela, surface="raised")
        self._tl = QVBoxLayout(self.tabela)
        self._tl.setContentsMargins(theme.space("10"), theme.space("6"),
                                    theme.space("10"), theme.space("8"))
        self._tl.setSpacing(theme.space("3"))
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        rolagem.setWidget(self.tabela)
        rolagem.setMinimumHeight(theme.space("24") * 4)
        rolagem.setMaximumHeight(theme.space("24") * 7)
        lay.addWidget(rolagem)
        self._fill_table()
        return painel

    # ── estado ────────────────────────────────────────────────────────────

    def _on_param(self, chave: str, valor) -> None:
        self.params[chave] = valor
        if chave in ("ambient", "temperature"):
            self._refresh_literature()

    def _refresh_literature(self) -> None:
        amb = self.params.get("ambient", "WETO2")
        try:
            t = int(round(parse_float(self.params.get("temperature")) or 0))
        except (TypeError, ValueError):
            t = 0
        chave = min(LITERATURA, key=lambda k: (k[0] != amb, abs(k[1] - t)))
        if chave[0] != amb:
            self._lit.setText("sem valor tabelado para este ambiente")
            return
        B, BA = LITERATURA[chave]
        self._lit.setText(f"{chave[0]} a {chave[1]} °C (Deal & Grove, 1965)\n"
                          f"B = {B:g} µm²/h    B/A = {BA:g} µm/h")

    def times(self) -> list[float]:
        """Os tempos escritos no campo, em minutos, já limpos e ordenados.

        A vírgula faz dois papéis em português: separa itens e marca decimal.
        A regra aqui é a que o campo anuncia — vírgula **entre dígitos** é
        decimal (``0,5``), e vírgula seguida de espaço, ponto e vírgula ou
        espaço separam itens (``10, 30; 60 120``). Sem isso, ``0,5`` viraria
        dois tempos, 0 e 5, sem o usuário perceber.
        """
        bruto = str(self.params.get("times") or "")
        marcado = re.sub(r"(?<=\d),(?=\d)", "\x00", bruto)
        out: list[float] = []
        for parte in re.split(r"[,;\s]+", marcado):
            v = parse_float(parte.replace("\x00", ","))
            if v is not None and v > 0:
                out.append(v)
        return sorted(set(out))

    # ── execução ──────────────────────────────────────────────────────────

    def _start(self) -> None:
        if self._worker is not None:
            return
        tempos = self.times()
        if len(tempos) < 2:
            self.erro.show_error(
                "Poucos tempos para ajustar",
                "O ajuste de Deal-Grove precisa de pelo menos dois tempos "
                "distintos. Escreva-os separados por vírgula.", "")
            return
        self.erro.hide()
        self.sweep = None
        self.chart.clear()
        self._set_metrics({})
        params = {"ambient": self.params.get("ambient", "WETO2"),
                  "temperature": parse_float(self.params.get("temperature"))
                  or 1000.0,
                  "orientation": self.params.get("orientation", "100"),
                  "doping": str(self.params.get("doping") or "1E15")}
        self._btn_run.setEnabled(False)
        self._btn_stop.setVisible(True)
        self._total = len(tempos)
        self._andamento.setText(f"0 de {self._total} corridas")
        self._worker = _SweepWorker(tempos, params, self)
        self._worker.point.connect(self._on_point)
        self._worker.finished_sweep.connect(self._on_done)
        self._worker.start()
        self.run_requested.emit()

    def _stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._andamento.setText("parando depois da corrida atual…")

    def _on_point(self, i: int, ponto) -> None:
        feito = i + 1
        extra = "" if ponto.ok else f" — {ponto.error}"
        self._andamento.setText(f"{feito} de {self._total} corridas"
                                f" · {fmt_number(ponto.time_min)} min{extra}")

    def _on_done(self, resultado) -> None:
        self._worker = None
        self._btn_run.setEnabled(True)
        self._btn_stop.setVisible(False)
        self.sweep = resultado
        self.chart.set_sweep(resultado)
        self._set_metrics(resultado.fit)
        self._fill_table()
        self._btn_csv.setEnabled(bool(resultado.valid()))
        validos = len(resultado.valid())
        if resultado.error and not resultado.fit:
            self.erro.show_error("A varredura não produziu ajuste",
                                 resultado.error, "")
            self._andamento.setText(resultado.error)
        else:
            self._andamento.setText(
                f"{validos} de {len(resultado.points)} corridas mediram "
                f"espessura")

    # ── apresentação ──────────────────────────────────────────────────────

    def _set_metrics(self, fit: dict) -> None:
        for chave, (valor, _un) in self._metricas.items():
            v = fit.get(chave)
            if v is None:
                valor.setText("—")
            elif chave == "r2":
                valor.setText(f"{v:.4f}".replace(".", ","))
            else:
                valor.setText(fmt_number(v))

    def _fill_table(self) -> None:
        while self._tl.count():
            item = self._tl.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        cab = row(eyebrow("tempo"), stretch(), eyebrow("medido"),
                  eyebrow("modelo"), eyebrow("regime"))
        self._tl.addWidget(cab)
        self._tl.addWidget(hline())
        if not self.sweep or not self.sweep.points:
            vazio = label("Nenhuma corrida ainda.")
            theme.mark(vazio, role="muted")
            self._tl.addWidget(vazio)
            return
        fit = self.sweep.fit or {}
        A, B_min = fit.get("A", 0.0), fit.get("B_min", 0.0)
        for ponto in self.sweep.points:
            t = label(f"{fmt_number(ponto.time_min)} min", "mono")
            if not ponto.ok:
                medido = label(ponto.error or "falhou")
                theme.mark(medido, role="muted")
                self._tl.addWidget(row(t, stretch(), medido))
                continue
            medido = label(f"{fmt_number(ponto.thickness_um)} µm", "mono")
            if B_min:
                prev = oxidation.deal_grove_xo(ponto.time_min, A, B_min)
                modelo = label(f"{fmt_number(prev)} µm", "mono")
                reg = label(oxidation.regime(ponto.thickness_um, A))
            else:
                modelo, reg = label("—", "mono"), label("—")
            theme.mark(modelo, role="muted")
            theme.mark(reg, role="muted")
            self._tl.addWidget(row(t, stretch(), medido, modelo, reg))

    # ── exportar ──────────────────────────────────────────────────────────

    def report_text(self) -> str:
        """CSV com os tempos, as espessuras medidas e o que o modelo prevê."""
        linhas = ["tempo_min,espessura_um,modelo_um,regime"]
        if not self.sweep:
            return "\n".join(linhas) + "\n"
        fit = self.sweep.fit or {}
        A, B_min = fit.get("A", 0.0), fit.get("B_min", 0.0)
        for p in self.sweep.points:
            if not p.ok:
                linhas.append(f"{p.time_min:g},,,{p.error}")
                continue
            prev = (oxidation.deal_grove_xo(p.time_min, A, B_min)
                    if B_min else 0.0)
            linhas.append(f"{p.time_min:g},{p.thickness_um:.6g},"
                          f"{prev:.6g},{oxidation.regime(p.thickness_um, A)}")
        if fit:
            linhas.append("")
            linhas.append(f"# B = {fit.get('B_h', 0):.6g} um2/h")
            linhas.append(f"# A = {fit.get('A', 0):.6g} um")
            linhas.append(f"# B/A = {fit.get('BA_h', 0):.6g} um/h")
            linhas.append(f"# R2 = {fit.get('r2', 0):.6f}")
        return "\n".join(linhas) + "\n"

    def _csv(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Exportar a varredura", "oxidacao.csv", "CSV (*.csv)")
        if caminho:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(self.report_text())
