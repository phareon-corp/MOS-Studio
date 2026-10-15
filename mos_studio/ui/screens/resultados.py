"""Tela de Resultados: execuções, perfil por etapa, camadas e comparação.

É a tela do arquivo de design: a lista de execuções à esquerda, o seletor de
etapas e as três vistas no meio, e as medidas à direita. Marcar mais de uma
execução sobrepõe as curvas.
"""

from __future__ import annotations

import csv

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QStackedWidget, QVBoxLayout, QWidget)

from ...core import evolution as evo
from ...core import workspace
from ...core.parsers import detect_junctions, junction_threshold, parse_layers
from ...core.recipe import MATERIAL_LABELS, fmt_number
from .. import theme
from ..widgets.common import (button, column, eyebrow, hline, label, row,
                              stretch, vline)
from ..widgets.layer_stack import LayerStack
from ..widgets.profile_chart import ChartData, ChartLegend, ProfileChart, Series
from ..widgets.run_list import RunList

#: Cores das execuções sobrepostas, na ordem.
COMPARE_COLORS = ("ink", "accent", "amber", "ink-dim")
#: Cor de cada espécie na vista de espécies.
SPECIES_COLORS = {"Net": "ink", "Boron": "ink-dim", "Phosphorus": "accent",
                  "Arsenic": "amber", "Antimony": "ink-faint"}

VIEWS = (("especies", "Espécies"), ("evolucao", "Evolução"),
         ("camadas", "Camadas"))


class ResultsScreen(QWidget):
    """Tudo o que uma execução produziu."""

    open_deck_requested = Signal(str)      # texto do deck

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._records: list[workspace.RunRecord] = []
        self._current: workspace.RunRecord | None = None
        self._compared: list[workspace.RunRecord] = []
        self._evolutions: dict[str, evo.Evolution] = {}
        self._step = 0
        self._view = "especies"
        self._filter = ""

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._build_sidebar())
        raiz.addWidget(vline())
        raiz.addWidget(self._build_center(), 1)
        raiz.addWidget(vline())
        raiz.addWidget(self._build_side_panel())

    # ── barra lateral ─────────────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        painel = QWidget()
        painel.setFixedWidth(theme.space("24") * 6)
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        topo = QWidget()
        tl = QVBoxLayout(topo)
        tl.setContentsMargins(theme.space("8"), theme.space("9"),
                              theme.space("8"), theme.space("6"))
        tl.setSpacing(theme.space("6"))
        self._contagem = label("", "mono")
        tl.addWidget(row(eyebrow("execuções"), stretch(), self._contagem))
        self._busca = QLineEdit()
        self._busca.setPlaceholderText("Buscar por nome ou parâmetro")
        self._busca.textChanged.connect(self._on_filter)
        tl.addWidget(self._busca)
        lay.addWidget(topo)
        lay.addWidget(hline())

        self.lista = RunList()
        self.lista.selected.connect(self.show_record)
        self.lista.toggled.connect(self._toggle_compare)
        lay.addWidget(self.lista, 1)

        lay.addWidget(hline())
        self._dica = label("", "hint", wrap=True)
        self._dica.setContentsMargins(theme.space("8"), theme.space("6"),
                                      theme.space("8"), theme.space("6"))
        lay.addWidget(self._dica)
        return painel

    # ── centro ────────────────────────────────────────────────────────────

    def _build_center(self) -> QWidget:
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cabeca = QWidget()
        cl = QHBoxLayout(cabeca)
        cl.setContentsMargins(theme.space("14"), theme.space("10"),
                              theme.space("14"), theme.space("8"))
        cl.setSpacing(theme.space("8"))
        texto = QVBoxLayout()
        texto.setSpacing(theme.space("2"))
        self._eyebrow = eyebrow("")
        self._titulo = label("", "title")
        texto.addWidget(self._eyebrow)
        texto.addWidget(self._titulo)
        cl.addLayout(texto, 1)

        self._b_renomear = button("Renomear", "small", on_click=self._rename)
        self._b_apagar = button("Apagar", "small", on_click=self._delete)
        self._b_deck = button("Ver deck", "small", on_click=self._show_deck)
        acoes = row(self._b_renomear, self._b_apagar, self._b_deck,
                    button("Exportar CSV", "small", on_click=self._export_csv),
                    button("Relatório", "small", on_click=self._export_report),
                    spacing="3")
        cl.addWidget(acoes, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(cabeca)
        lay.addWidget(hline())

        self._scrubber = QWidget()
        self._scrubber_lay = QHBoxLayout(self._scrubber)
        self._scrubber_lay.setContentsMargins(theme.space("14"), theme.space("6"),
                                              theme.space("14"), 0)
        self._scrubber_lay.setSpacing(theme.space("1"))
        lay.addWidget(self._scrubber)

        barra = QWidget()
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(theme.space("14"), theme.space("6"),
                              theme.space("14"), theme.space("4"))
        bl.setSpacing(theme.space("8"))
        self._legenda = ChartLegend()
        bl.addWidget(self._legenda, 1)
        self._vistas = {}
        caixa_vistas = QHBoxLayout()
        caixa_vistas.setSpacing(theme.space("2"))
        for chave, rotulo in VIEWS:
            b = button(rotulo, "segment", checkable=True,
                       on_click=lambda _c=False, k=chave: self.set_view(k))
            self._vistas[chave] = b
            caixa_vistas.addWidget(b)
        bl.addLayout(caixa_vistas)
        lay.addWidget(barra)

        self._pilha = QStackedWidget()
        self._grafico = ProfileChart()
        self._camadas = LayerStack()
        self._mensagem = label("", "dim", wrap=True)
        self._mensagem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mensagem.setContentsMargins(theme.space("24"), theme.space("24"),
                                          theme.space("24"), theme.space("24"))
        for w in (self._grafico, self._camadas, self._mensagem):
            self._pilha.addWidget(w)
        lay.addWidget(self._pilha, 1)
        return host

    # ── painel direito ────────────────────────────────────────────────────

    def _build_side_panel(self) -> QWidget:
        painel = QWidget()
        painel.setFixedWidth(theme.dimension("sidebar-width"))
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(theme.space("12"), theme.space("12"),
                               theme.space("12"), theme.space("12"))
        lay.setSpacing(theme.space("5"))

        self._painel_medidas = QWidget()
        ml = QVBoxLayout(self._painel_medidas)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(theme.space("5"))
        ml.addWidget(eyebrow("profundidade de junção"))
        self._xj = label("—", "metric")
        self._xj_unidade = label("µm", "serif")
        ml.addWidget(row(self._xj, self._xj_unidade, stretch(), spacing="4"))
        self._xj_nota = label("", "hint", wrap=True)
        ml.addWidget(self._xj_nota)
        ml.addWidget(hline())
        ml.addWidget(eyebrow("concentração na superfície"))
        self._ns = label("—", "mono")
        self._ns.setFont(theme.font("mono", "medium"))
        ml.addWidget(self._ns)
        ml.addWidget(eyebrow("óxido na superfície"))
        self._ox = label("—", "mono")
        self._ox.setFont(theme.font("mono", "medium"))
        ml.addWidget(self._ox)
        ml.addWidget(eyebrow("camadas"))
        self._camadas_lista = QWidget()
        self._camadas_lay = QVBoxLayout(self._camadas_lista)
        self._camadas_lay.setContentsMargins(0, 0, 0, 0)
        self._camadas_lay.setSpacing(theme.space("2"))
        ml.addWidget(self._camadas_lista)
        ml.addWidget(eyebrow("anotação"))
        self._nota = QPlainTextEdit()
        self._nota.setFixedHeight(theme.space("24") * 2)
        self._nota.setPlaceholderText("Referência para o relatório…")
        self._nota.focusOutEvent = self._save_note(self._nota.focusOutEvent)
        ml.addWidget(self._nota)
        ml.addStretch(1)

        self._painel_comparacao = QWidget()
        cl = QVBoxLayout(self._painel_comparacao)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(theme.space("5"))
        self._cmp_titulo = eyebrow("junção por execução")
        cl.addWidget(self._cmp_titulo)
        self._cmp_lista = QWidget()
        self._cmp_lay = QVBoxLayout(self._cmp_lista)
        self._cmp_lay.setContentsMargins(0, 0, 0, 0)
        self._cmp_lay.setSpacing(theme.space("4"))
        cl.addWidget(self._cmp_lista)
        cl.addWidget(label(
            "Referência: a primeira execução marcada. A diferença é medida "
            "sobre a mesma etapa.", "hint", wrap=True))
        cl.addStretch(1)

        lay.addWidget(self._painel_medidas)
        lay.addWidget(self._painel_comparacao)
        self._painel_comparacao.hide()
        return painel

    def _save_note(self, original):
        def handler(event):
            if self._current is not None:
                self._current.set_note(self._nota.toPlainText())
            original(event)
        return handler

    # ── dados ─────────────────────────────────────────────────────────────

    def reload(self, select: workspace.RunRecord | None = None) -> None:
        """Relê as execuções do disco."""
        self._records = workspace.list_runs()
        alvo = select or self._current
        if alvo is not None:
            alvo = next((r for r in self._records if r.path == alvo.path), None)
        if alvo is None:
            alvo = self._records[0] if self._records else None
        self._current = alvo
        self._compared = [alvo] if alvo else []
        self._step = 0
        self._refresh_list()
        self.refresh()

    def show_record(self, registro: workspace.RunRecord) -> None:
        """Mostra uma execução sozinha."""
        self._current = registro
        self._compared = [registro]
        self._step = 0
        self._refresh_list()
        self.refresh()

    def _toggle_compare(self, registro: workspace.RunRecord) -> None:
        if registro.status != "ok":
            return
        caminhos = [r.path for r in self._compared]
        if registro.path in caminhos:
            if len(self._compared) > 1:
                self._compared = [r for r in self._compared
                                  if r.path != registro.path]
        else:
            self._compared = (self._compared + [registro])[-4:]
        self._current = self._compared[0]
        self._refresh_list()
        self.refresh()

    def _on_filter(self, texto: str) -> None:
        self._filter = texto.strip().lower()
        self._refresh_list()

    def _visible_records(self) -> list[workspace.RunRecord]:
        if not self._filter:
            return self._records
        resultado = []
        for r in self._records:
            alvo = f"{r.name} {r.when_text} {r.status}".lower()
            if self._filter in alvo or self._filter in r.deck().lower():
                resultado.append(r)
        return resultado

    def _refresh_list(self) -> None:
        visiveis = self._visible_records()
        self.lista.populate(visiveis, selected=self._current,
                            compared={str(r.path) for r in self._compared})
        total = len(self._records)
        self._contagem.setText(
            f"{len(visiveis)} de {total}" if self._filter else str(total))
        self._dica.setText(
            f"{len(self._compared)} execuções sobrepostas. Clique numa linha "
            "para voltar a uma só." if len(self._compared) > 1 else
            "Marque a caixa de outras execuções para sobrepor as curvas.")

    # ── evolução ──────────────────────────────────────────────────────────

    def _evolution(self, registro: workspace.RunRecord) -> evo.Evolution | None:
        """Evolução de uma execução, do cache ou do disco."""
        chave = str(registro.path)
        if chave in self._evolutions:
            return self._evolutions[chave]
        guardada = evo.Evolution.load(registro.path)
        if guardada is not None:
            self._evolutions[chave] = guardada
        return guardada

    # ── desenho ───────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Redesenha o centro e o painel direito."""
        comparando = len(self._compared) > 1
        self._painel_medidas.setVisible(not comparando)
        self._painel_comparacao.setVisible(comparando)
        for b in (self._b_renomear, self._b_apagar, self._b_deck):
            b.setVisible(not comparando)

        if self._current is None:
            self._eyebrow.setText("NENHUMA EXECUÇÃO AINDA")
            self._titulo.setText("Sem resultado")
            self._show_message("Monte a receita em Processo e clique em "
                               "Simular processo.")
            self._clear(self._scrubber_lay)
            self._legenda.set_series([])
            return

        if comparando:
            self._eyebrow.setText(f"COMPARAÇÃO · {len(self._compared)} EXECUÇÕES")
            self._titulo.setText("Execuções sobrepostas")
        else:
            r = self._current
            self._eyebrow.setText(
                f"EXECUÇÃO #{r.number} · {r.when_text.upper()} · {r.engine}")
            self._titulo.setText(r.name)
            self._nota.blockSignals(True)
            self._nota.setPlainText(r.note)
            self._nota.blockSignals(False)

        self._refresh_scrubber()
        self._refresh_view_buttons()
        self._refresh_center()
        if comparando:
            self._refresh_compare_panel()
        else:
            self._refresh_metrics()

    def _refresh_scrubber(self) -> None:
        self._clear(self._scrubber_lay)
        ev = self._evolution(self._current) if self._current else None
        if ev is None or not ev.ok:
            self._scrubber.hide()
            return
        passos = ev.steps()
        if self._step not in [n for n, _ in passos]:
            self._step = passos[-1][0]
        self._scrubber.show()
        for numero, rotulo in passos:
            ativo = numero == self._step
            passado = numero < self._step
            b = button("", "link", on_click=lambda _c=False, n=numero:
                       self.set_step(n))
            b.setText(f"{numero:02d}  {rotulo}")
            b.setToolTip(rotulo)
            b.setFont(theme.font("sans", "tiny",
                                 "medium" if ativo else "regular"))
            theme.mark(b, variant="link")
            caixa = QWidget()
            cl = QVBoxLayout(caixa)
            cl.setContentsMargins(0, 0, 0, theme.space("2"))
            cl.setSpacing(theme.space("2"))
            barra = _Bar("accent" if ativo else
                         ("line-strong" if passado else "line"))
            barra.setFixedHeight(3)
            cl.addWidget(barra)
            cl.addWidget(b)
            self._scrubber_lay.addWidget(caixa, 1)

    def set_step(self, numero: int) -> None:
        self._step = numero
        self._refresh_scrubber()
        self._refresh_center()
        if len(self._compared) > 1:
            self._refresh_compare_panel()
        else:
            self._refresh_metrics()

    def set_view(self, chave: str) -> None:
        self._view = chave
        self._refresh_view_buttons()
        self._refresh_center()

    def _refresh_view_buttons(self) -> None:
        comparando = len(self._compared) > 1
        for chave, b in self._vistas.items():
            b.setChecked(chave == self._view)
            b.setEnabled(not (comparando and chave != "especies"))

    def _show_message(self, texto: str) -> None:
        self._mensagem.setText(texto)
        self._pilha.setCurrentWidget(self._mensagem)

    def _refresh_center(self) -> None:
        if self._current is None:
            return
        if len(self._compared) > 1:
            self._draw_comparison()
            return
        estado = self._current.status
        if estado == "erro":
            self._show_message(
                "O motor recusou este deck: nenhuma tabela foi gravada. "
                "Abra o deck desta execução para ver o que foi enviado.")
            self._legenda.set_series([])
            return
        if estado == "cancelada":
            self._show_message("Execução cancelada. Nenhum resultado foi gravado.")
            self._legenda.set_series([])
            return
        if self._view == "camadas":
            self._draw_layers()
        elif self._view == "evolucao":
            self._draw_evolution()
        else:
            self._draw_species()

    def _draw_species(self) -> None:
        ev = self._evolution(self._current)
        series: list[Series] = []
        if ev is not None and ev.ok:
            for s in ev.at(self._step):
                series.append(Series(
                    s.quantity_label, [(x, abs(c)) for x, c in s.points],
                    SPECIES_COLORS.get(s.quantity, "ink"),
                    dashed=s.quantity != "Net",
                    width=2.4 if s.quantity == "Net" else 1.6,
                    sublabel="|N_D − N_A|" if s.quantity == "Net" else ""))
            liquido = next((s for s in ev.at(self._step) if s.quantity == "Net"),
                           None)
            pontos = liquido.points if liquido else []
        else:
            pontos = self._current.profile()
            if pontos:
                series.append(Series("Líquido", [(x, abs(c)) for x, c in pontos],
                                     "ink", width=2.4, sublabel="|N_D − N_A|"))
        if not series:
            self._show_message(
                "A execução terminou, mas nenhuma saída trouxe a tabela de "
                "concentração. Confira se há uma etapa PRINT com "
                "“Concentração por profundidade”.")
            self._legenda.set_series([])
            return
        juncoes = (detect_junctions(pontos, min_mag=junction_threshold(pontos))
                   if pontos else [])
        self._grafico.set_data(ChartData(series=series, junctions=juncoes))
        self._legenda.set_series(series)
        self._pilha.setCurrentWidget(self._grafico)

    def _draw_evolution(self) -> None:
        ev = self._evolution(self._current)
        if ev is None or not ev.ok:
            self._show_message(
                "A evolução por etapa não foi calculada para esta execução. "
                "Rode a receita de novo para gerá-la.")
            self._legenda.set_series([])
            return
        series = []
        instantaneos = [s for s in ev.net_series() if s.step <= self._step]
        for i, s in enumerate(instantaneos):
            ultimo = i == len(instantaneos) - 1
            series.append(Series(
                f"Etapa {s.step:02d}", [(x, abs(c)) for x, c in s.points],
                "accent" if ultimo else "ink-dim",
                dashed=not ultimo, width=2.2 if ultimo else 1.4,
                sublabel=s.step_label if ultimo else ""))
        self._grafico.set_data(ChartData(series=series))
        self._legenda.set_series(series[-3:])
        self._pilha.setCurrentWidget(self._grafico)

    def _draw_layers(self) -> None:
        camadas = self._current.layers()
        pontos = self._current.profile()
        juncoes = (detect_junctions(pontos, min_mag=junction_threshold(pontos))
                   if pontos else [])
        self._camadas.set_layers(camadas, juncoes[0] if juncoes else None)
        self._legenda.set_series([])
        self._pilha.setCurrentWidget(self._camadas)

    def _draw_comparison(self) -> None:
        series = []
        for i, registro in enumerate(self._compared):
            ev = self._evolution(registro)
            if ev is not None and ev.ok:
                alvo = min(self._step, ev.last_step()) or ev.last_step()
                instantaneo = next((s for s in ev.at(alvo)
                                    if s.quantity == "Net"), None)
                pontos = instantaneo.points if instantaneo else registro.profile()
            else:
                pontos = registro.profile()
            if not pontos:
                continue
            series.append(Series(
                f"#{registro.number} {registro.name}",
                [(x, abs(c)) for x, c in pontos],
                COMPARE_COLORS[i % len(COMPARE_COLORS)], width=2.0))
        if not series:
            self._show_message("Nenhuma das execuções marcadas tem perfil.")
            self._legenda.set_series([])
            return
        self._grafico.set_data(ChartData(series=series))
        self._legenda.set_series(series)
        self._pilha.setCurrentWidget(self._grafico)

    # ── painéis ───────────────────────────────────────────────────────────

    def _profile_at_step(self, registro) -> list[tuple[float, float]]:
        ev = self._evolution(registro)
        if ev is not None and ev.ok:
            alvo = min(self._step, ev.last_step()) or ev.last_step()
            instantaneo = next((s for s in ev.at(alvo) if s.quantity == "Net"),
                               None)
            if instantaneo:
                return instantaneo.points
        return registro.profile()

    def _refresh_metrics(self) -> None:
        registro = self._current
        pontos = self._profile_at_step(registro)
        if pontos:
            juncoes = detect_junctions(pontos, min_mag=junction_threshold(pontos))
            if juncoes:
                self._xj.setText(f"{juncoes[0]:.3f}".replace(".", ","))
                self._xj_nota.setText(
                    "Primeira troca de tipo no perfil líquido ativo."
                    + (f" Outras em {', '.join(f'{x:.3f}'.replace('.', ',') for x in juncoes[1:])} µm."
                       if len(juncoes) > 1 else ""))
            else:
                self._xj.setText("—")
                self._xj_nota.setText(
                    "Não há troca de tipo na profundidade simulada.")
            self._ns.setText(f"{fmt_number(abs(pontos[0][1]))} cm⁻³")
        else:
            self._xj.setText("—")
            self._xj_nota.setText("Perfil não lido nesta execução.")
            self._ns.setText("—")

        camadas = registro.layers()
        oxido = next((e for m, e in camadas if m == "OXIDE"), None)
        self._ox.setText(f"{oxido:.4f} µm".replace(".", ",") if oxido else "nenhum")
        self._clear(self._camadas_lay)
        if not camadas:
            self._camadas_lay.addWidget(label(
                "Adicione uma etapa PRINT com a tabela “Camadas”.", "hint",
                wrap=True))
        for material, espessura in camadas:
            nome = MATERIAL_LABELS.get(material, material.capitalize())
            valor = label(f"{espessura:.4f}".replace(".", ",") + " µm", "mono")
            self._camadas_lay.addWidget(
                row(label(nome, "base"), stretch(), valor, spacing="4"))

    def _refresh_compare_panel(self) -> None:
        self._clear(self._cmp_lay)
        base = self._compared[0]
        pontos_base = self._profile_at_step(base)
        xj_base = detect_junctions(pontos_base,
                                   min_mag=junction_threshold(pontos_base)) \
            if pontos_base else []
        for i, registro in enumerate(self._compared):
            pontos = self._profile_at_step(registro)
            juncoes = (detect_junctions(pontos, min_mag=junction_threshold(pontos))
                       if pontos else [])
            xj = juncoes[0] if juncoes else None
            cor = COMPARE_COLORS[i % len(COMPARE_COLORS)]
            traco = _Bar(cor)
            traco.setFixedSize(theme.space("8"), 2)
            titulo = label(f"#{registro.number} {registro.name}", "base")
            valor = label(f"{xj:.3f} µm".replace(".", ",") if xj else "—", "mono")
            valor.setFont(theme.font("mono", "base"))
            self._cmp_lay.addWidget(row(traco, titulo, stretch(), valor,
                                        spacing="4"))
            if i and xj and xj_base:
                delta = xj - xj_base[0]
                sinal = "+" if delta >= 0 else "−"
                detalhe = (f"Δxj {sinal}{abs(delta):.3f} µm".replace(".", ",")
                           + f" · {self._diff_text(base, registro)}")
            else:
                detalhe = "Referência" if i == 0 else self._diff_text(base, registro)
            nota = label(detalhe, "hint", wrap=True)
            nota.setContentsMargins(theme.space("12"), 0, 0, theme.space("4"))
            self._cmp_lay.addWidget(nota)

    @staticmethod
    def _diff_text(a, b) -> str:
        """Diferença entre dois decks, em uma linha."""
        linhas_a = [l.strip() for l in a.deck().replace("\r\n", "\n").split("\n")]
        linhas_b = [l.strip() for l in b.deck().replace("\r\n", "\n").split("\n")]
        diferentes = [(x, y) for x, y in zip(linhas_a, linhas_b) if x != y]
        if not diferentes and len(linhas_a) == len(linhas_b):
            return "Mesmos parâmetros"
        if len(diferentes) == 1:
            return f"Deck: {diferentes[0][1][:60]}"
        return f"{len(diferentes) or abs(len(linhas_a) - len(linhas_b))} linhas diferentes"

    def _clear(self, lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    # ── ações ─────────────────────────────────────────────────────────────

    def _rename(self) -> None:
        if self._current is None:
            return
        novo, ok = QInputDialog.getText(self, "Renomear execução",
                                        "Nome:", text=self._current.name)
        if ok and novo.strip():
            self._current.rename(novo.strip())
            self._refresh_list()
            self.refresh()

    def _delete(self) -> None:
        if self._current is None:
            return
        resposta = QMessageBox.question(
            self, "Apagar execução",
            f"Apagar “{self._current.name}” e todos os seus arquivos?")
        if resposta == QMessageBox.StandardButton.Yes:
            self._current.delete()
            self.reload()

    def _show_deck(self) -> None:
        if self._current is not None:
            self.open_deck_requested.emit(self._current.deck())

    def _export_csv(self) -> None:
        if self._current is None:
            return
        pontos = self._profile_at_step(self._current)
        if not pontos:
            QMessageBox.information(self, "Exportar CSV",
                                    "Esta execução não tem perfil para exportar.")
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, "Exportar perfil", f"{self._current.name}.csv",
            "CSV (*.csv)")
        if not destino:
            return
        with open(destino, "w", newline="", encoding="utf-8") as f:
            escritor = csv.writer(f)
            escritor.writerow(["profundidade_um", "concentracao_cm3"])
            escritor.writerows(pontos)

    def _export_report(self) -> None:
        if self._current is None:
            return
        destino, _ = QFileDialog.getSaveFileName(
            self, "Relatório da execução", f"{self._current.name}.txt",
            "Texto (*.txt)")
        if not destino:
            return
        with open(destino, "w", encoding="utf-8") as f:
            f.write(self.report_text())

    def report_text(self) -> str:
        """Relatório em texto da execução em foco."""
        r = self._current
        if r is None:
            return "Nenhuma execução selecionada.\n"
        pontos = self._profile_at_step(r)
        juncoes = (detect_junctions(pontos, min_mag=junction_threshold(pontos))
                   if pontos else [])
        linhas = [f"MOS-Studio — relatório da execução #{r.number}", "",
                  f"Nome:    {r.name}",
                  f"Quando:  {r.when_text}",
                  f"Motor:   {r.engine}",
                  f"Estado:  {r.status}",
                  f"Pasta:   {r.path}", ""]
        if pontos:
            linhas.append(f"Pontos de perfil: {len(pontos)}")
            linhas.append(f"Concentração na superfície: "
                          f"{fmt_number(abs(pontos[0][1]))} cm⁻³")
        linhas.append("Junções: " + (", ".join(f"{x:.4f} µm" for x in juncoes)
                                     if juncoes else "nenhuma"))
        camadas = r.layers()
        if camadas:
            linhas.append("")
            linhas.append("Camadas:")
            for material, espessura in camadas:
                linhas.append(f"  {MATERIAL_LABELS.get(material, material):14} "
                              f"{espessura:.4f} µm")
        if r.note:
            linhas += ["", "Anotação:", r.note]
        linhas += ["", "Deck enviado ao motor:", "",
                   r.deck().replace("\r\n", "\n")]
        return "\n".join(linhas) + "\n"


class _Bar(QWidget):
    """Barra de cor sólida (seletor de etapas e legenda da comparação)."""

    def __init__(self, token: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._token = token

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.fillRect(self.rect(), theme.qcolor(self._token))
        p.end()
