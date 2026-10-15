"""Tela de Resultados 2-D: a seção transversal e o corte que sai dela.

Esta compilação do SUPREM-IV.GS não desenha: a biblioteca gráfica são talões
vazios (``gpsup/gpfake.c``), e ``plot.2d``, ``contour`` e ``plot.1d`` passam
sem produzir nada. Então a tela não pede desenho ao motor — pede **números**:
varre a seção com N cortes verticais ``print.1d x.value=`` e monta tudo a
partir deles (:mod:`mos_studio.core.field2d`).

O painel de comandos mostra justamente isso, e não a sequência clássica
``plot.2d bound fill`` / ``contour val=(…)``: essa seria a forma canônica no
SUPREM-IV original, mas aqui não sairia nada, e oferecê-la como "comando
equivalente" mandaria o usuário para um beco sem saída.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QScrollArea, QSlider, QSplitter,
                               QVBoxLayout, QWidget)

from ...core import field2d
from .. import theme
from ..widgets.common import (button, column, eyebrow, hline, label, row,
                              stretch)
from ..widgets.cross_section import CrossSection, LABELS, level_label
from ..widgets.profile_chart import ChartData, ProfileChart, Series

#: Níveis de contorno oferecidos, em cm⁻³.
LEVELS = (1e16, 1e17, 1e18, 1e19, 1e20)

#: Níveis ligados quando a tela abre.
DEFAULT_LEVELS = (1e16, 1e17, 1e18, 1e19)

#: Grandezas que o ``select`` sabe mostrar. ``doping`` é a dopagem líquida
#: **ativa**; as espécies são o perfil químico, que existe mesmo antes de um
#: recozimento ativar o implante.
SPECIES = (("doping", "Líquido"), ("arsenic", "Arsênio"),
           ("phosphorus", "Fósforo"), ("boron", "Boro"))

#: Passos do controle de corte, em centésimos de µm.
CUT_STEPS = 100


class Results2DScreen(QWidget):
    """A tela inteira de Resultados 2-D."""

    #: Pede uma nova varredura com esta grandeza (``doping``, ``arsenic``…).
    scan_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._field = field2d.Field2D()
        self._levels = list(DEFAULT_LEVELS)
        self._species = "doping"
        self._title = ""

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        divisor = QSplitter(Qt.Orientation.Horizontal)
        divisor.setChildrenCollapsible(False)
        divisor.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(divisor)
        divisor.addWidget(self._build_main())
        divisor.addWidget(self._build_aside())
        divisor.setSizes([860, theme.dimension("sidebar-width")
                          + theme.space("24")])
        divisor.setStretchFactor(0, 1)
        self._refresh()

    # ── montagem ──────────────────────────────────────────────────────────

    def _build_main(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("10"), theme.space("10"),
                               theme.space("10"), theme.space("10"))
        lay.setSpacing(theme.space("7"))

        self._eyebrow = eyebrow("suprem-iv", accent=True)
        cabecalho = QWidget()
        cl = QHBoxLayout(cabecalho)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.space("8"))
        cl.addWidget(column(self._eyebrow,
                            label("Corte transversal e contornos", "title"),
                            spacing="2"))
        cl.addStretch(1)
        self._chips_especie: dict[str, object] = {}
        chips = QWidget()
        chl = QHBoxLayout(chips)
        chl.setContentsMargins(0, 0, 0, 0)
        chl.setSpacing(theme.space("3"))
        for chave, rotulo in SPECIES:
            b = button(rotulo, "segment", checkable=True)
            b.setChecked(chave == self._species)
            b.clicked.connect(
                lambda _c=False, k=chave: self._pick_species(k))
            self._chips_especie[chave] = b
            chl.addWidget(b)
        cl.addWidget(chips)
        lay.addWidget(cabecalho)

        self.view = CrossSection()
        self.view.cut_changed.connect(self._on_cut)
        lay.addWidget(self.view, 1)

        controle = QWidget()
        ctl = QHBoxLayout(controle)
        ctl.setContentsMargins(0, 0, 0, 0)
        ctl.setSpacing(theme.space("6"))
        ctl.addWidget(label("print.1d  x.value =", "mono"))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, CUT_STEPS)
        self._slider.setValue(CUT_STEPS // 2)
        self._slider.valueChanged.connect(self._on_slider)
        ctl.addWidget(self._slider, 1)
        self._cut_label = label("—", "mono")
        self._cut_label.setMinimumWidth(theme.space("20"))
        ctl.addWidget(self._cut_label)
        self._b_profundidade = button("Ver até o fundo", "small",
                                      checkable=True)
        self._b_profundidade.setToolTip(
            "Por padrão o desenho para logo abaixo da junção mais funda; o "
            "substrato inteiro espremeria o dispositivo numa faixa de poucos "
            "pixels.")
        self._b_profundidade.toggled.connect(self._on_full_depth)
        ctl.addWidget(self._b_profundidade)
        lay.addWidget(controle)

        self._legenda = label("", "hint", wrap=True)
        lay.addWidget(self._legenda)
        return host

    def _build_aside(self) -> QWidget:
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setMinimumWidth(theme.dimension("sidebar-width"))
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(theme.space("9"), theme.space("10"),
                               theme.space("9"), theme.space("10"))
        lay.setSpacing(theme.space("8"))

        self._xj_titulo = eyebrow("profundidade de junção")
        self._xj = label("—", "metric")
        self._xj_nota = label("", "hint", wrap=True)
        lay.addWidget(column(self._xj_titulo,
                             row(self._xj, label("µm", "serif"), stretch(),
                                 spacing="3"),
                             self._xj_nota, spacing="3"))
        lay.addWidget(hline())

        lay.addWidget(eyebrow("corte 1-d no ponto escolhido"))
        self.chart = ProfileChart()
        self.chart.set_compact(True)
        self.chart.set_empty_message("Mova o corte sobre a seção.")
        self.chart.setMinimumHeight(theme.space("24") * 6)
        lay.addWidget(self.chart)
        lay.addSpacing(theme.space("4"))
        lay.addWidget(hline())

        lay.addWidget(eyebrow("níveis de contorno"))
        self._chips_nivel: dict[float, object] = {}
        faixa = QWidget()
        fl = QHBoxLayout(faixa)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(theme.space("3"))
        for nivel in LEVELS:
            b = button(level_label(nivel), "segment", checkable=True)
            b.setChecked(nivel in self._levels)
            b.setToolTip(f"{nivel:.0e} cm⁻³".replace("e+", "×10"))
            b.toggled.connect(
                lambda on, v=nivel: self._toggle_level(v, on))
            self._chips_nivel[nivel] = b
            fl.addWidget(b)
        fl.addStretch(1)
        lay.addWidget(faixa)
        lay.addWidget(hline())

        lay.addWidget(eyebrow("como este desenho foi obtido"))
        self._comandos = label("", "mono", wrap=True)
        theme.mark(self._comandos, surface="code")
        self._comandos.setContentsMargins(theme.space("6"), theme.space("5"),
                                          theme.space("6"), theme.space("5"))
        lay.addWidget(self._comandos)
        lay.addWidget(label(
            "No SUPREM-IV original o caminho seria plot.2d e contour. Nesta "
            "compilação eles não desenham nada — a biblioteca gráfica são "
            "talões vazios —, então a seção é varrida com cortes print.1d e "
            "desenhada aqui.", "hint", wrap=True))
        lay.addStretch(1)
        rolagem.setWidget(host)
        return rolagem

    # ── dados ─────────────────────────────────────────────────────────────

    def set_field(self, fld: field2d.Field2D, title: str = "") -> None:
        """Recebe a varredura e redesenha tudo."""
        self._field = fld
        self._title = title
        self._species = fld.z_expr or "doping"
        for chave, b in self._chips_especie.items():
            b.setChecked(chave == self._species)
        if fld.ok:
            x0, x1, _, _ = fld.extent()
            meio = x0 + (x1 - x0) * 0.9
            self.view.set_field(fld)
            self.view.set_cut(meio)
            self._slider.blockSignals(True)
            self._slider.setValue(int(round((meio - x0) / max(1e-9, x1 - x0)
                                            * CUT_STEPS)))
            self._slider.blockSignals(False)
        else:
            self.view.set_field(fld)
        self._refresh()

    def field(self) -> field2d.Field2D:
        return self._field

    def species(self) -> str:
        return self._species

    def levels(self) -> list[float]:
        return list(self._levels)

    def clear(self) -> None:
        self.set_field(field2d.Field2D())

    # ── interação ─────────────────────────────────────────────────────────

    def _pick_species(self, chave: str) -> None:
        for k, b in self._chips_especie.items():
            b.setChecked(k == chave)
        if chave == self._species:
            return
        self._species = chave
        # A grandeza é escolhida no deck (``select z=…``), então trocar de
        # espécie exige rodar de novo: o motor não guarda o que não foi pedido.
        self.scan_requested.emit(chave)

    def _toggle_level(self, nivel: float, ligado: bool) -> None:
        if ligado and nivel not in self._levels:
            self._levels.append(nivel)
        elif not ligado and nivel in self._levels:
            self._levels.remove(nivel)
        self.view.set_levels(self._levels)
        self._refresh_commands()

    def _on_slider(self, valor: int) -> None:
        if not self._field.ok:
            return
        x0, x1, _, _ = self._field.extent()
        self.view.set_cut(x0 + (x1 - x0) * valor / CUT_STEPS)
        self._refresh_cut()

    def _on_cut(self, x: float) -> None:
        if not self._field.ok:
            return
        x0, x1 = self._field.extent()[0], self._field.extent()[1]
        self._slider.blockSignals(True)
        self._slider.setValue(int(round((x - x0) / max(1e-9, x1 - x0)
                                        * CUT_STEPS)))
        self._slider.blockSignals(False)
        self._refresh_cut()

    def _on_full_depth(self, ligado: bool) -> None:
        _, _, _, y1 = self._field.extent()
        self.view.set_depth_limit(y1 if ligado else 0.0)

    # ── redesenho ─────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self.view.set_levels(self._levels)
        etapas = self._title or "sem execução"
        self._eyebrow.setText(f"SUPREM-IV · {etapas}".upper())
        materiais = self.view.materials()
        if not materiais:
            self._legenda.setText("")
        else:
            texto = ("Materiais na seção: "
                     + ", ".join(LABELS.get(m, m) for m in materiais) + ".")
            if self._species == "doping":
                texto += " A linha tracejada é a junção."
            else:
                texto += (f" Perfil químico de "
                          f"{dict(SPECIES)[self._species]}: não há junção, "
                          "porque uma espécie não troca de sinal.")
            self._legenda.setText(texto)
        # Sem early return: a medida da junção e o painel de comandos têm o
        # próprio estado vazio, e pular os dois deixava a tela em branco
        # antes da primeira execução.
        self._refresh_cut()
        self._refresh_commands()

    def _refresh_cut(self) -> None:
        x = self.view.cut()
        self._cut_label.setText(f"{x:.2f} µm".replace(".", ","))
        if not self._field.ok:
            self._xj.setText("—")
            self._xj_nota.setText("Rode o processo para medir a junção.")
            self._xj_titulo.setText("PROFUNDIDADE DE JUNÇÃO")
            self.chart.clear()
            return
        self._xj_titulo.setText(
            f"PROFUNDIDADE DE JUNÇÃO EM X = {x:.2f}".replace(".", ","))
        xj = field2d.junction_depth_at(self._field, x)
        if xj is None:
            self._xj.setText("—")
            self._xj_nota.setText(self._no_junction_note())
        else:
            self._xj.setText(f"{xj:.3f}".replace(".", ","))
            self._xj_nota.setText(
                "Medida da superfície do silício, não do topo da pilha.")
        self._refresh_chart()
        self._refresh_commands()

    def _no_junction_note(self) -> str:
        """Por que não há junção neste corte.

        Vale distinguir os dois casos: sob a porta o implante foi barrado pela
        máscara, e esse é o resultado certo; sem nenhuma junção na seção
        inteira, o mais provável é que o implante não tenha sido recozido e a
        dopagem ativa ainda não o enxergue.
        """
        if self._species != "doping":
            return ("A junção só existe na dopagem líquida; o perfil químico "
                    "de uma espécie não troca de sinal.")
        tem_alguma = any(
            field2d.junction_depth_at(self._field, c.x) is not None
            for c in self._field.columns)
        if tem_alguma:
            return ("Sem junção neste corte: a máscara barrou o implante "
                    "aqui. É o resultado esperado sob a porta.")
        # Sem junção em lugar nenhum: ou a lâmina só tem o dopante do
        # substrato, ou há implante e falta recozer. A dopagem líquida conta
        # apenas dopante ativo, e um implante cru não aparece nela.
        return ("Nenhuma junção na seção: a lâmina tem um tipo só. Se a "
                "receita tem implante, falta um tratamento térmico para "
                "ativá-lo — a dopagem líquida só conta dopante ativo.")

    def _refresh_chart(self) -> None:
        col = field2d.column_at(self._field, self.view.cut())
        if col is None or not col.depth:
            self.chart.clear()
            return
        sup = col.surface() or 0.0
        # O mesmo recorte de profundidade do desenho ao lado: com os dois
        # micra inteiros do substrato, o perfil vira uma reta horizontal e a
        # parte que interessa some nos primeiros pixels.
        fundo = max(self.view.visible_depth() - sup, 0.05)
        # Piso de concentração: um perfil químico cai a valores como 1 cm⁻³
        # longe do implante, e sem piso o eixo logarítmico abriria vinte e
        # duas décadas para mostrar ruído numérico.
        _, pico = self._field.value_range()
        piso = max(pico * 1e-7, 1e12)
        pontos = [(d - sup, v) for d, v, m in
                  zip(col.depth, col.value, col.material)
                  if m in field2d.BULK and abs(v) >= piso and d - sup <= fundo]
        if not pontos:
            self.chart.clear()
            return
        nome = dict(SPECIES).get(self._species, self._species)
        # A junção do gráfico é a mesma medida que o número grande mostra —
        # recalcular por troca de sinal entre nós daria um valor sem
        # interpolação, e as duas leituras discordariam na tela.
        xj = field2d.junction_depth_at(self._field, self.view.cut())
        self.chart.set_data(ChartData(
            series=[Series(label=nome, points=[(d, abs(v)) for d, v in pontos],
                           color="accent")],
            junctions=[xj] if xj is not None and xj <= fundo else [],
            y_label="concentração (cm⁻³)"))

    def _refresh_commands(self) -> None:
        if not self._field.ok:
            self._comandos.setText("—")
            return
        xs = self._field.xs
        linhas = [f"select z={self._species}"]
        if len(xs) > 3:
            linhas.append(f"print.1d x.value={xs[0]:g}")
            linhas.append(f"print.1d x.value={xs[1]:g}")
            linhas.append(f"…  ({len(xs)} cortes ao todo)")
            linhas.append(f"print.1d x.value={xs[-1]:g}")
        else:
            linhas += [f"print.1d x.value={x:g}" for x in xs]
        linhas.append(f"print.1d x.value={xs[-1]:g} layers")
        niveis = " ".join(str(int(round(math.log10(v))))
                          for v in sorted(self._levels))
        if niveis:
            linhas.append(f"#  contornos desenhados aqui: 10^({niveis})")
        self._comandos.setText("\n".join(linhas))
