"""Janela principal: cabeçalho, áreas, faixa de execução e rodapé.

É aqui que a receita, o motor e as telas se encontram. A janela não conhece
detalhes do SUPREM: ela pede o deck à tela de Processo, entrega ao
:class:`~mos_studio.ui.run_controller.RunController` e distribui o resultado.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QInputDialog, QMenu,
                               QStackedWidget, QVBoxLayout, QWidget)

from ..core import deck as deck_mod
from ..core import evolution as evo
from ..core import (engines, examples4, field2d, library, mesh as mesh_mod,
                    minimos, models4, recipe4, suprem, suprem4, workspace)
from . import theme
from .run_controller import RunController
from .screens.console import ConsoleScreen
from .screens.dispositivo import DeviceScreen
from .screens.estrutura import StructureScreen
from .screens.exemplos import ExamplesScreen
from .screens.inicio import HomeScreen
from .screens.malha import MeshScreen
from .screens.modelos import ModelsScreen
from .screens.oxidacao import OxidationScreen
from .screens.processo import ProcessScreen
from .screens.processo2d import Process2DScreen
from .screens.resultados import ResultsScreen
from .screens.resultados2d import Results2DScreen
from .widgets.common import hline
from .widgets.footer import Footer
from .widgets.header import Header
from .widgets.status_strip import StatusStrip
from .widgets.tour_overlay import TourOverlay

#: Telas do motor 2-D. A janela usa isto para saber a qual dimensão uma área
#: pertence sem perguntar ao cabeçalho.
AREAS_2D = frozenset(("malha", "processo2d", "resultados2d", "modelos",
                      "console", "estrutura"))

APP_NAME = "MOS-Studio"


class MainWindow(QWidget):
    """A janela do aplicativo."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(theme.dimension("window-min-width"),
                            theme.dimension("window-min-height"))

        self.project = workspace.Project.from_recipe(library.get("diodo-pn"))
        self.runs: list[suprem.RunResult] = []
        self._evolucao: QThread | None = None
        self._run = RunController(self)
        #: Dimensão em foco: ``"1d"`` (SUPREM-III) ou ``"2d"`` (SUPREM-IV).
        self.dimension = "1d"
        #: Grandeza que a próxima varredura 2-D vai pedir ao ``select``.
        self._scan_species = "doping"

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        self.header = Header()
        raiz.addWidget(self.header)
        raiz.addWidget(hline())

        self.inicio = HomeScreen()
        self.processo = ProcessScreen()
        self.resultados = ResultsScreen()
        self.dispositivo = DeviceScreen()
        self.oxidacao = OxidationScreen()
        self.malha = MeshScreen()
        self.processo2d = Process2DScreen()
        self.resultados2d = Results2DScreen()
        self.modelos = ModelsScreen()
        self.console = ConsoleScreen()
        self.estrutura = StructureScreen()
        self.exemplos = ExamplesScreen()
        self.areas = QStackedWidget()
        self._indices = {
            "inicio": self.areas.addWidget(self.inicio),
            "processo": self.areas.addWidget(self.processo),
            "resultados": self.areas.addWidget(self.resultados),
            "dispositivo": self.areas.addWidget(self.dispositivo),
            "oxidacao": self.areas.addWidget(self.oxidacao),
            "malha": self.areas.addWidget(self.malha),
            "processo2d": self.areas.addWidget(self.processo2d),
            "resultados2d": self.areas.addWidget(self.resultados2d),
            "modelos": self.areas.addWidget(self.modelos),
            "console": self.areas.addWidget(self.console),
            "estrutura": self.areas.addWidget(self.estrutura),
            "exemplos": self.areas.addWidget(self.exemplos),
        }
        raiz.addWidget(self.areas, 1)

        self.strip = StatusStrip()
        raiz.addWidget(self.strip)
        raiz.addWidget(hline())
        self.footer = Footer()
        raiz.addWidget(self.footer)

        self.tour = TourOverlay(self)
        self._register_tour_targets()
        self._tour_cut_moved = False

        self._connect()
        self._refresh_engines()
        self._refresh_run_button()
        self.resultados.reload()
        self.inicio.refresh()
        self.go("inicio")

    # ── ligações ──────────────────────────────────────────────────────────

    def _connect(self) -> None:
        self.header.area_changed.connect(self.go)
        self.header.dimension_changed.connect(self.set_dimension)
        self.header.run_requested.connect(self.start_run)
        self.header.cancel_requested.connect(self._run.cancel)
        self.header.issues_requested.connect(self._go_to_first_issue)

        self.header.project_menu_requested.connect(self._project_menu)

        self.inicio.new_project.connect(self.new_project)
        self.inicio.open_project.connect(self.open_project)
        self.inicio.import_deck.connect(self.import_deck)
        self.inicio.import_legacy.connect(self.import_legacy)
        self.inicio.change_working_dir.connect(self.change_working_dir)
        self.inicio.recheck_engines.connect(self.recheck_engines)
        self.inicio.tour_requested.connect(self.start_tour)
        self.inicio.guided_requested.connect(self.start_guided_project)

        self.resultados.open_deck_requested.connect(self._open_deck_text)
        self.dispositivo.run_started.connect(self._on_device_started)
        self.dispositivo.run_finished.connect(self._on_device_finished)
        self.dispositivo.motor_changed.connect(
            lambda: (self._refresh_engines(), self._refresh_run_button()))
        self.oxidacao.run_requested.connect(
            lambda: self.strip.show_running("Varrendo a oxidação…", 0.0, 0.2))

        self.processo.recipe_changed.connect(self._on_recipe_changed)
        self.processo.run_literal_requested.connect(self.start_run)
        self.processo.erro.retry_requested.connect(self._retry)

        # ── 2-D ──
        self.malha.mesh_changed.connect(self._on_mesh_changed)
        self.processo2d.recipe_changed.connect(self._on_recipe4_changed)
        self.processo2d.run_literal_requested.connect(self.start_run)
        self.processo2d.guided_step_requested.connect(self.add_guided_step)
        self.processo2d.erro.retry_requested.connect(self._retry)
        self.modelos.models_changed.connect(self._on_models_changed)
        self.resultados2d.scan_requested.connect(self._rescan)
        self.resultados2d._slider.valueChanged.connect(
            lambda _v: setattr(self, "_tour_cut_moved", True))
        self.resultados2d.view.cut_changed.connect(
            lambda _x: setattr(self, "_tour_cut_moved", True))
        self.console.deck_requested.connect(self._send_recipe_to_console)
        self.estrutura.add_step_requested.connect(self._add_step_2d)
        self.estrutura.command_requested.connect(self._send_to_console)
        self.exemplos.example_chosen.connect(self.open_example)
        self.exemplos.recipe_chosen.connect(self.open_recipe_1d)

        self.strip.cancel_requested.connect(self._run.cancel)
        self.strip.result_requested.connect(lambda: self.go("resultados"))
        self.strip.dismiss_requested.connect(self.strip.dismiss)

        self._run.started.connect(self._on_run_started)
        self._run.tick.connect(self._on_run_tick)
        self._run.stage_changed.connect(self._on_run_tick_stage)
        self._run.succeeded.connect(self._on_run_succeeded)
        self._run.failed.connect(self._on_run_failed)
        self._run.was_cancelled.connect(self._on_run_cancelled)

        QShortcut(QKeySequence("Ctrl+R"), self, self.start_run)
        # Desfazer, refazer e o deck agem na receita da dimensão em foco.
        QShortcut(QKeySequence("Ctrl+Z"), self,
                  lambda: self._recipe_screen().undo())
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self,
                  lambda: self._recipe_screen().redo())
        QShortcut(QKeySequence("Ctrl+D"), self,
                  lambda: self._recipe_screen().toggle_deck())
        QShortcut(QKeySequence("Ctrl+N"), self, lambda: self.new_project(""))
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_project)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_project)
        QShortcut(QKeySequence("Ctrl+0"), self, lambda: self.go("inicio"))
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.go("processo"))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self.go("resultados"))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self.go("dispositivo"))
        QShortcut(QKeySequence("Ctrl+4"), self, lambda: self.go("oxidacao"))
        QShortcut(QKeySequence("Ctrl+5"), self, lambda: self.go("exemplos"))
        QShortcut(QKeySequence("F1"), self, self.start_tour)
        QShortcut(QKeySequence("Ctrl+T"), self,
                  lambda: self.set_dimension(
                      "2d" if self.dimension == "1d" else "1d"))

    # ── roteiros guiados ──────────────────────────────────────────────────

    def _register_tour_targets(self) -> None:
        """Dá nome aos widgets que o destaque pode iluminar.

        O roteiro em :mod:`mos_studio.core.tour` fala por nome; assim ele
        continua sendo dado, sem conhecer a árvore de widgets.
        """
        self.tour.register("dim", self.header._dims)
        self.tour.register("run", self.header._pilha)
        for chave, botao in self.header._buttons.items():
            self.tour.register(f"nav-{chave}", botao)
            self.tour.register(f"tool-{chave}", botao)
        self.tour.register("mesh-lines", self.malha)
        self.tour.register("mesh-preview", self.malha.view)
        self.tour.register("recipe2d", self.processo2d.lista)
        self.tour.register("cut", self.resultados2d._slider)
        self.tour.register("console-input", self.console.input)
        self.tour.register("addstep", self.processo2d.b_guiado)

    def start_tour(self) -> None:
        """O passeio pelas telas do motor 2-D."""
        from ..core import tour as tour_mod

        self._tour_cut_moved = False
        self._register_tour_targets()
        self.tour.finished.connect(self._end_ui_tour)
        self.tour.start(tour_mod.UI_TOUR, "tour · interface")

    def _end_ui_tour(self) -> None:
        """Marca o passeio como concluído quando chega ao fim."""
        try:
            self.tour.finished.disconnect(self._end_ui_tour)
        except (RuntimeError, TypeError):
            pass
        if self.tour.index + 1 >= len(tour_mod_steps(self.tour)):
            self.inicio.mark_tutorial_done("ui")

    def start_guided_project(self) -> None:
        """O projeto guiado: monta o transistor LDD etapa por etapa.

        A receita 2-D é esvaziada para o usuário montá-la, e a malha volta
        ao padrão do exam5 — é a malha que o roteiro pressupõe.
        """
        from ..core import tour as tour_mod

        self.set_dimension("2d", area="processo2d")
        self.malha.reset()
        self.processo2d.steps = []
        self.processo2d._selected = None
        self.processo2d._undo.clear()
        self.processo2d._redo.clear()
        self.processo2d.title = "TRANSISTOR LDD - PROJETO GUIADO"
        self.processo2d.refresh()
        self.processo2d.set_guided(True, len(tour_mod.LDD_STEPS),
                                   len(tour_mod.LDD_STEPS))
        self.tour.finished.connect(self._end_guided)
        self._register_tour_targets()
        self.tour.start(tour_mod.ldd_tour(), "projeto guiado · ldd")

    def _end_guided(self) -> None:
        """Sai do modo guiado quando o roteiro termina ou é abandonado."""
        self.processo2d.set_guided(False)
        if self.tour.index + 1 >= len(self.tour.steps() or [1]):
            self.inicio.mark_tutorial_done("ldd")
        try:
            self.tour.finished.disconnect(self._end_guided)
        except (RuntimeError, TypeError):
            pass

    def add_guided_step(self) -> None:
        """Acrescenta a próxima etapa do projeto guiado à receita."""
        from ..core import recipe4 as r4
        from ..core import tour as tour_mod

        i = len(self.processo2d.steps)
        if i >= len(tour_mod.LDD_STEPS):
            return
        modelo = tour_mod.LDD_STEPS[i]
        passo = r4.Step4.new(modelo.type)
        passo.params.update(modelo.params)
        self.processo2d._push_undo()
        self.processo2d.steps.append(passo)
        self.processo2d._selected = passo.uid
        self.processo2d.refresh()
        self.processo2d.set_guided(True, len(tour_mod.LDD_STEPS) - i - 1,
                                   len(tour_mod.LDD_STEPS))
        self.processo2d.recipe_changed.emit()

    # ── navegação ─────────────────────────────────────────────────────────

    def go(self, area: str) -> None:
        """Troca a área visível, acompanhando a dimensão quando preciso.

        Ir para uma tela do outro motor troca a dimensão junto: o botão de
        execução, a navegação e o deck precisam concordar com a tela.
        """
        if area not in self._indices:
            return
        if area in AREAS_2D and self.dimension != "2d":
            self.set_dimension("2d", area=area)
            return
        if area not in AREAS_2D and area != "inicio" and area != "exemplos" \
                and self.dimension != "1d":
            self.set_dimension("1d", area=area)
            return
        self.areas.setCurrentIndex(self._indices[area])
        self.header.set_area(area)
        if area == "console":
            self.console.ensure_started()
        if area == "estrutura":
            self.estrutura.set_directory(self._structure_dir())
        self._refresh_run_button()

    def set_dimension(self, dim: str, area: str = "") -> None:
        """Troca o motor em foco e vai para a tela correspondente."""
        from .widgets.header import area_for

        if dim not in ("1d", "2d"):
            return
        destino = area or area_for(dim, self.current_area())
        mudou = dim != self.dimension
        self.dimension = dim
        self.project.dimension = dim
        if mudou:
            self.project.dirty = True
        self.header.set_dimension(dim)
        if destino in self._indices:
            self.areas.setCurrentIndex(self._indices[destino])
            self.header.set_area(destino)
            if destino == "console":
                self.console.ensure_started()
            if destino == "estrutura":
                self.estrutura.set_directory(self._structure_dir())
        self._refresh_engines()
        self._refresh_run_button()

    def _recipe_screen(self):
        """A tela de receita da dimensão em foco."""
        return self.processo2d if self.dimension == "2d" else self.processo

    def _structure_dir(self):
        """Pasta onde procurar estruturas: a da última execução 2-D."""
        for r in reversed(self.runs):
            if getattr(r, "out_dir", None) is not None:
                return r.out_dir
        from .. import paths
        return paths.RESULTS_DIR

    def current_area(self) -> str:
        atual = self.areas.currentIndex()
        for nome, indice in self._indices.items():
            if indice == atual:
                return nome
        return "processo"

    def _go_to_first_issue(self) -> None:
        self.go("processo")
        self.processo.focus_first_issue()

    # ── motores ───────────────────────────────────────────────────────────

    def _refresh_engines(self) -> None:
        self._suprem_problems = suprem.check_engine(suprem.find_run_dir())
        self._suprem4_problems = suprem4.check_engine(suprem4.find_run_dir())
        self._minimos_problems = minimos.problemas_motor()
        self.footer.set_engines(self._suprem_problems, self._minimos_problems,
                                self._suprem4_problems,
                                minimos.NOMES_MOTOR[minimos.motor_escolhido()])
        self._refresh_footer_right()

    def _refresh_footer_right(self) -> None:
        """A direita do rodapé: onde o projeto está e o que o motor vai ver."""
        from .. import paths

        partes: list[str] = []
        caminho = getattr(self.project, "path", None)
        partes.append(paths.curto(caminho) if caminho
                      else f"{paths.RESULTS_DIR.name}/")
        if self.dimension == "2d":
            s = self.malha.stats()
            partes.append("SUPREM-IV")
            partes.append(f"{s.nodes} nós" if s.ok else "malha inválida")
        else:
            partes.append("SUPREM-III")
            partes.append(f"preferências em {paths.curto(paths.config_dir())}")
        self.footer.set_right(" · ".join(partes))

    def _process_problems(self) -> list[str]:
        """Problemas do motor de processo da dimensão em foco."""
        return (self._suprem4_problems if self.dimension == "2d"
                else self._suprem_problems)

    def _refresh_run_button(self) -> None:
        """Decide a forma do botão da direita: simular, bloqueado ou rodando."""
        if self._run.running:
            self.header.show_running(self._run.elapsed)
            return
        area = self.current_area()
        if area in ("inicio", "exemplos", "estrutura"):
            self.header.show_idle()
            self.header.set_run_enabled(False)
            self._refresh_project_chip()
            return
        if area == "dispositivo":
            self.header.show_idle()
            self.header.set_run_enabled(not self._minimos_problems)
            self._refresh_project_chip()
            return
        if area == "oxidacao":
            self.header.show_idle()
            self.header.set_run_enabled(not self._suprem_problems)
            self._refresh_project_chip()
            return
        if area == "console":
            self.header.show_idle()
            self.header.set_run_enabled(not self._suprem4_problems)
            self._refresh_project_chip()
            return
        problemas = (self.processo2d.issues() if self.dimension == "2d"
                     else self.processo.issues())
        if problemas:
            self.header.show_blocked(len(problemas))
        else:
            self.header.show_idle()
            self.header.set_run_enabled(not self._process_problems())
        self._refresh_project_chip()

    def _refresh_project_chip(self) -> None:
        nome = (self.project.name or "").strip()
        marca = " •" if self.project.dirty else ""
        self.header.set_project(f"{nome}{marca}" if nome else "")

    # ── execução ──────────────────────────────────────────────────────────

    def start_run(self) -> None:
        """Roda a receita no motor da dimensão em foco."""
        if self._run.running:
            return
        area = self.current_area()
        if area in ("inicio", "exemplos", "estrutura"):
            return
        if area == "dispositivo":
            self.dispositivo.run()
            return
        if area == "oxidacao":
            self.oxidacao._start()
            return
        if area == "console":
            self._send_recipe_to_console()
            return
        if area == "malha":
            # Aqui "gerar malha" é só isso: pedir ao motor que a construa e
            # devolva a contagem. Rodar o processo inteiro seria prometer uma
            # coisa e fazer outra.
            nos, erro = self.malha.check_with_engine()
            if erro or not nos:
                self.strip.show_stopped(erro or "A malha não foi gerada.", 0.0)
            else:
                self.strip.show_done(f"O motor gerou a malha: {nos} nós", 0.0)
            return
        if self.dimension == "2d":
            self._start_run_2d()
            return
        if self._suprem_problems:
            self.go("processo")
            self.processo.erro.show_error(
                "O SUPREM-III não está disponível",
                "Os binários do motor não puderam ser usados. Corrija os itens "
                "abaixo e tente de novo.",
                "\n".join(self._suprem_problems), can_retry=False)
            return
        if self.processo.issues():
            self._go_to_first_issue()
            return
        self.go("processo")
        self.processo.erro.hide()
        self._run.start(self.processo.deck_text())

    def _start_run_2d(self) -> None:
        """Roda a receita 2-D e já pede a varredura que desenha o resultado.

        O deck não é o da tela de Processo: é ele mais os cartões de modelo
        alterados e uma sequência de cortes ``print.1d x.value=``. Sem os
        cortes a execução não produziria tabela nenhuma — esta compilação não
        desenha — e a tela de Resultados ficaria vazia.
        """
        if self._suprem4_problems:
            self.go("processo2d")
            self.processo2d.erro.show_error(
                "O SUPREM-IV não está disponível",
                "Os binários do motor não puderam ser usados. Corrija os "
                "itens abaixo e tente de novo.",
                "\n".join(self._suprem4_problems), can_retry=False)
            return
        if self.processo2d.issues():
            self.go("processo2d")
            self.processo2d.focus_first_issue()
            return
        estat = self.malha.stats()
        if estat.risky:
            # Deixar rodar seria gastar minutos para o motor morrer sem
            # mensagem: acima deste tamanho ele termina em falha de
            # segmentação (ver mesh.MAX_SAFE_NODES).
            self.go("malha")
            self.strip.show_stopped(
                f"Malha grande demais: {estat.nodes} nós. O SUPREM-IV cai "
                f"acima de cerca de {mesh_mod.MAX_SAFE_NODES}.", 0.0)
            return
        self.go("processo2d")
        self.processo2d.erro.hide()
        self._run.start(self._scan_deck(), engines.SUPREM4)

    def _scan_deck(self) -> str:
        """O deck da execução 2-D, com modelos e cortes."""
        if self.processo2d.manual_deck():
            return self.processo2d.deck.text()
        malha = self.processo2d.mesh()
        x0, x1 = mesh_mod.extent(malha)[0], mesh_mod.extent(malha)[1]
        self._scan_xs = field2d.scan_positions(x0, x1)
        cartoes = [c for p in self.processo2d.steps
                   for c in recipe4.step_to_cards(p)]
        # Os modelos vêm antes das etapas: o motor aplica o coeficiente a
        # partir do cartão, e depois da difusão já não adiantaria.
        cartoes = self.modelos.cards() + cartoes
        return field2d.build_scan_deck(self.processo2d.title,
                                       mesh_mod.to_cards(malha), cartoes,
                                       self._scan_xs, self._scan_species)

    def _rescan(self, especie: str) -> None:
        """Roda de novo pedindo outra grandeza ao ``select``."""
        self._scan_species = especie
        self.go("resultados2d")
        self._start_run_2d()

    def _on_run_succeeded_2d(self, result) -> None:
        """Lê a varredura e entrega à tela de Resultados 2-D."""
        campo = field2d.parse_scan(result.raw(), getattr(self, "_scan_xs", []),
                                   self._scan_species)
        self.resultados2d.set_field(
            campo, f"{self.project.name or self.processo2d.title} · "
                   f"{len(self.processo2d.steps)} etapas")
        self.estrutura.set_directory(self._structure_dir())
        if not campo.ok:
            self.strip.show_stopped(
                "A execução terminou, mas nenhum corte trouxe tabela. "
                "Confira se a receita chega a criar estrutura.",
                result.elapsed)
        else:
            self.strip.show_done(
                f"Seção varrida em {len(campo.columns)} cortes",
                result.elapsed)
        self.go("resultados2d")

    def _on_run_started(self) -> None:
        self.strip.set_engine(engines.get(self._run.engine_id).label)
        if self.dimension == "2d":
            self.processo2d.set_progress(0, 0)
        else:
            self.processo.set_progress(0, 0)
        self.header.show_running(0.0)
        self.strip.show_running("Preparando o deck…", 0.0, 0.0)

    def _on_run_tick(self, elapsed: float) -> None:
        self.header.show_running(elapsed)
        self.strip.show_running(self._stage_text(), elapsed,
                                self._stage_progress())

    def _on_run_tick_stage(self, _stage: str) -> None:
        self.strip.show_running(self._stage_text(), self._run.elapsed,
                                self._stage_progress())

    def _stage_text(self) -> str:
        rotulos = {"setup": "Preparando os arquivos de entrada (setup)",
                   "genii": "Lendo o deck e gerando a malha (genii)",
                   "sup3": "Simulando o processo (sup3)"}
        return rotulos.get(self._run.stage, "Executando…")

    def _stage_progress(self) -> float:
        ordem = {"setup": 0.2, "genii": 0.5, "sup3": 0.8}
        return ordem.get(self._run.stage, 0.05)

    def _on_run_succeeded(self, result) -> None:
        self.runs.append(result)
        if self._run.engine_id == engines.SUPREM4:
            self.processo2d.set_progress(-1, len(self.processo2d.steps))
            self._refresh_run_button()
            self._on_run_succeeded_2d(result)
            return
        self.processo.set_progress(-1, len(self.processo.steps))
        registro = workspace.record_run(result, name=self.project.name or
                                        self.processo.title)
        self._save_evolution(result)
        self.resultados.reload(registro)
        self.dispositivo.set_process(self.processo.steps, result.profile())
        self.inicio.refresh()
        perfil = result.profile()
        resumo = (f"Execução concluída · {len(perfil)} pontos de perfil em "
                  f"{result.profile_source()}" if perfil
                  else "Execução concluída, mas nenhuma saída trouxe a tabela "
                       "de concentração")
        self.strip.show_done(resumo, result.elapsed)
        self._refresh_run_button()
        self.go("resultados")

    def _on_run_failed(self, message: str) -> None:
        primeira = message.strip().splitlines()[0] if message.strip() else "Falha"
        self.strip.show_stopped(primeira, self._run.elapsed)
        self._refresh_run_button()
        if self._run.engine_id == engines.SUPREM4:
            self.processo2d.set_progress(-1, -1)
            self.go("processo2d")
            self.processo2d.erro.show_error(
                "O SUPREM-IV não concluiu a simulação",
                "O motor parou e devolveu a mensagem abaixo. Em 2-D a causa "
                "mais comum é geométrica: corroer o que não está na lâmina, "
                "ou uma malha fina demais para o tempo disponível.",
                message)
            return
        self.processo.set_progress(-1, -1)
        self.go("processo")
        self.processo.erro.show_error(
            "O SUPREM-III não concluiu a simulação",
            "O motor parou e devolveu a mensagem abaixo. Se você editou o deck "
            "à mão, confira as linhas de continuação: elas precisam começar "
            "com “+” na coluna 1, sem espaço antes.",
            message)

    def _on_run_cancelled(self) -> None:
        self.processo2d.set_progress(-1, -1)
        self.processo.set_progress(-1, -1)
        self.strip.show_stopped(
            "Execução cancelada. Nenhum resultado foi gravado.",
            self._run.elapsed)
        self._refresh_run_button()

    def _retry(self) -> None:
        """Fecha o painel de erro e roda de novo."""
        self.processo.erro.hide()
        self.start_run()

    # ── projetos ──────────────────────────────────────────────────────────

    def _collect_project(self) -> None:
        """Copia o estado das telas para o projeto, antes de gravar."""
        self.project.dimension = self.dimension
        self.project.steps = list(self.processo.steps)
        self.project.mesh = mesh_mod.to_dict(self.malha.mesh())
        self.project.steps4 = [workspace.Step(s.type, dict(s.params))
                               for s in self.processo2d.steps]
        self.project.models = self.modelos.models.to_dict()

    def _on_recipe_changed(self) -> None:
        """A receita mudou: o projeto fica sujo e a ponte precisa refazer."""
        self.project.steps = list(self.processo.steps)
        self.project.title = self.processo.title
        self.project.dirty = True
        self.dispositivo.set_process(self.processo.steps,
                                     self.dispositivo._profile)
        self._refresh_run_button()

    def _on_mesh_changed(self) -> None:
        self.processo2d.set_mesh(self.malha.mesh())
        self.project.mesh = mesh_mod.to_dict(self.malha.mesh())
        self.project.dirty = True
        self._refresh_footer_right()
        self._refresh_run_button()

    def _on_recipe4_changed(self) -> None:
        self.project.steps4 = [workspace.Step(s.type, dict(s.params))
                               for s in self.processo2d.steps]
        self.project.title = self.processo2d.title
        self.project.dirty = True
        self._refresh_run_button()

    def _on_models_changed(self) -> None:
        self.project.models = self.modelos.models.to_dict()
        self.project.dirty = True

    def _send_to_console(self, comando: str) -> None:
        """Manda um comando ao Console e mostra a tela."""
        self.go("console")
        self.console.run(comando)

    def _send_recipe_to_console(self) -> None:
        """Roda a receita 2-D dentro da sessão do Console, por ``source``."""
        self.go("console")
        self.console.run_deck(self._scan_deck())

    def _add_step_2d(self, tipo: str) -> None:
        self.go("processo2d")
        self.processo2d.add_step(tipo)

    def open_recipe_1d(self, recipe_id: str) -> None:
        """Abre um exemplo 1-D como projeto editável na tela de Processo.

        Diferente dos decks de fábrica, que são texto: aqui as etapas entram
        na receita, dá para mudar a dose e rodar de novo.
        """
        from ..core import examples3

        ex = examples3.get(recipe_id)
        if ex is None:
            return
        projeto = workspace.Project(
            name=f"{ex.name} · {ex.emphasis}".strip(" ·"),
            title=ex.title, steps=ex.build())
        self._apply_project(projeto)
        self.set_dimension("1d", area="processo")
        self._refresh_project_chip()
        if ex.expect:
            self.strip.show_done(f"{ex.name}: {ex.expect}", 0.0)

    def open_example(self, example_id: str) -> None:
        """Abre um exemplo de fábrica: mostra o deck e, se der, roda."""
        ex = examples4.get(example_id)
        if ex is None:
            return
        texto = examples4.read(ex)
        if not texto:
            return
        self._open_deck_text(texto)
        if not ex.runnable:
            self.strip.show_stopped(
                f"{ex.name}: deck defeituoso de fábrica. {ex.broken}", 0.0)
            return
        # Os exemplos rodam como estão, na própria pasta, porque muitos leem
        # arquivos vizinhos e alguns continuam a estrutura de outro deck.
        import tempfile
        from pathlib import Path

        work = Path(tempfile.mkdtemp(prefix="mos_exemplo_"))
        prep = examples4.prepare(ex, work)
        self.go("console")
        self.console.ensure_started()
        self.console.run(f"source {prep.deck_name}"
                         if not ex.after else f"source {ex.after}")
        if ex.after:
            self.console.run(f"source {prep.deck_name}")

    def _apply_project(self, projeto: workspace.Project) -> None:
        """Põe um projeto em cena: receita, dispositivo e oxidação."""
        self.project = projeto
        self.processo.steps = list(projeto.steps)
        self.processo.title = projeto.title
        self.processo._selected = (projeto.steps[0].uid if projeto.steps
                                   else None)
        self.processo._undo.clear()
        self.processo._redo.clear()
        self.processo.refresh()
        if projeto.device:
            self.dispositivo.params.update(projeto.device)
        if projeto.oxidation:
            self.oxidacao.params.update(projeto.oxidation)
        self.dispositivo.set_process(projeto.steps, [])

        # ── o lado 2-D do projeto ──
        self.malha.set_mesh(mesh_mod.from_dict(projeto.mesh))
        passos4 = recipe4.steps_from_dicts(
            [{"tipo": s.type, "parametros": s.params} for s in projeto.steps4])
        if passos4:
            self.processo2d.steps = passos4
            self.processo2d._selected = passos4[0].uid
        self.processo2d.title = projeto.title
        self.processo2d._undo.clear()
        self.processo2d._redo.clear()
        self.processo2d.set_mesh(self.malha.mesh())
        self.modelos.set_models(models4.Models4.from_dict(projeto.models))
        self.resultados2d.clear()
        self.set_dimension(projeto.dimension or "1d",
                           area=self.current_area())
        self._refresh_run_button()

    def new_project(self, recipe_key: str = "") -> None:
        """Começa um projeto novo, de uma receita da biblioteca ou vazio."""
        receita = library.get(recipe_key) if recipe_key else None
        if receita is None:
            receita = library.get("diodo-pn")
        self._apply_project(workspace.Project.from_recipe(receita))
        self.go("processo")

    def new_project_2d(self) -> None:
        """Projeto novo já no SUPREM-IV, com a malha e a receita do LDD.

        A tela de Início não oferece isto como botão, como no arquivo de
        design: lá o caminho para o 2-D é a chave de dimensão do cabeçalho,
        que aparece assim que há projeto. O método fica para o menu do
        projeto e para os testes.
        """
        from .screens.processo2d import TITULO_INICIAL, receita_inicial

        self.new_project("")
        self.project.name = "Transistor LDD"
        self.project.title = TITULO_INICIAL
        self.malha.reset()
        self.processo2d.steps = receita_inicial()
        self.processo2d._selected = self.processo2d.steps[0].uid
        self.processo2d.title = TITULO_INICIAL
        self.processo2d._undo.clear()
        self.processo2d._redo.clear()
        self.processo2d.set_mesh(self.malha.mesh())
        self.modelos.set_models(models4.Models4())
        self.resultados2d.clear()
        self.set_dimension("2d", area="processo2d")
        self._refresh_project_chip()

    def open_project(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir projeto", str(workspace.working_dir()),
            f"Projetos do MOS-Studio (*{workspace.PROJECT_SUFFIX})")
        if not caminho:
            return
        try:
            projeto = workspace.Project.load(caminho)
        except (OSError, ValueError) as exc:
            self.go("processo")
            self.processo.erro.show_error(
                "Não foi possível abrir o projeto",
                "O arquivo não pôde ser lido como projeto do MOS-Studio.",
                str(exc), can_retry=False)
            return
        self._apply_project(projeto)
        self.go("processo")

    def save_project(self, novo_caminho: bool = False) -> None:
        self._collect_project()
        self.project.title = (self.processo2d.title if self.dimension == "2d"
                              else self.processo.title)
        self.project.device = dict(self.dispositivo.params)
        self.project.oxidation = dict(self.oxidacao.params)
        destino = None
        if novo_caminho or self.project.path is None:
            sugerido = str(workspace.working_dir()
                           / f"{workspace.slug(self.project.name)}"
                             f"{workspace.PROJECT_SUFFIX}")
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar projeto", sugerido,
                f"Projetos do MOS-Studio (*{workspace.PROJECT_SUFFIX})")
            if not caminho:
                return
            destino = caminho
        self.project.save(destino)
        self._refresh_run_button()
        self.inicio.refresh()
        self.strip.show_done(f"Projeto salvo em {self.project.path}", 0.0)

    def rename_project(self) -> None:
        nome, ok = QInputDialog.getText(self, "Nome do projeto",
                                        "Como chamar este projeto?",
                                        text=self.project.name)
        if ok and nome.strip():
            self.project.name = nome.strip()
            self.project.dirty = True
            self._refresh_run_button()

    def _project_menu(self, posicao) -> None:
        menu = QMenu(self)
        menu.addAction("Novo projeto…", lambda: self.new_project(""))
        menu.addAction("Abrir projeto…", self.open_project)
        menu.addSeparator()
        menu.addAction("Salvar", lambda: self.save_project(False))
        menu.addAction("Salvar como…", lambda: self.save_project(True))
        menu.addSeparator()
        menu.addAction("Renomear…", self.rename_project)
        menu.exec(posicao)

    def import_deck(self) -> None:
        """Importa um deck ``.IN`` como projeto novo."""
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Importar um deck do SUPREM", str(workspace.working_dir()),
            "Decks do SUPREM (*.IN *.in);;Todos os arquivos (*)")
        if not caminho:
            return
        from pathlib import Path
        try:
            texto = Path(caminho).read_text(encoding="latin-1")
        except OSError as exc:
            self.strip.show_stopped(f"Não foi possível ler o deck: {exc}", 0.0)
            return
        projeto = workspace.Project.from_deck(texto, Path(caminho).stem)
        if not projeto.steps:
            self.go("processo")
            self.processo.erro.show_error(
                "O deck não trouxe nenhuma etapa reconhecível",
                "O arquivo foi lido, mas nenhuma linha correspondeu aos "
                "comandos que o montador conhece. Ele pode ser aberto no "
                "painel do deck e rodado literalmente.",
                texto[:2000], can_retry=False)
            return
        self._apply_project(projeto)
        self.go("processo")
        self.strip.show_done(f"{len(projeto.steps)} etapas importadas de "
                             f"{Path(caminho).name}", 0.0)

    def import_legacy(self) -> None:
        """Passa a listar as execuções que a versão anterior deixou."""
        quantas = workspace.import_legacy()
        self.resultados.reload()
        self.inicio.refresh()
        self.strip.show_done(
            f"{quantas} execuções anteriores entraram no índice; os arquivos "
            f"ficaram onde estavam.", 0.0)

    def change_working_dir(self) -> None:
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher a pasta de trabalho",
            str(workspace.working_dir()))
        if not pasta:
            return
        workspace.set_working_dir(pasta)
        self.resultados.reload()
        self.inicio.refresh()
        self._refresh_engines()

    def recheck_engines(self) -> None:
        self._refresh_engines()
        self.dispositivo.recheck_engine()
        self.inicio.refresh()
        self._refresh_run_button()

    # ── resultados e evolução ─────────────────────────────────────────────

    def _save_evolution(self, result: suprem.RunResult) -> None:
        """Calcula a evolução por etapa, em segundo plano.

        É uma série de corridas derivadas, uma por etapa, e pode demorar mais
        que a simulação principal — por isso não trava a interface e não
        atrasa o resultado. Se falhar, a execução segue válida sem ela; os
        resultados só recarregam quando a série termina.
        """
        if result is None or result.out_dir is None:
            return
        pedido = _EvolutionWorker(self.processo.title,
                                  [s.as_dict() for s in self.processo.steps],
                                  result.out_dir, self)
        pedido.done.connect(self._on_evolution_done)
        self._evolucao = pedido          # mantém a referência viva
        pedido.start()

    def _on_evolution_done(self, ok: bool, mensagem: str) -> None:
        self._evolucao = None
        if ok:
            self.resultados.refresh()
        elif mensagem:
            self.footer.set_right(f"evolução por etapa indisponível: "
                                  f"{mensagem[:60]}")

    def _open_deck_text(self, texto: str) -> None:
        """Abre no painel de deck um deck vindo dos resultados."""
        self.go("processo")
        self.processo.show_deck()
        self.processo.deck.set_manual(texto)

    def _on_device_started(self) -> None:
        """A faixa passa a assinar o MINIMOS, não o motor de processo."""
        self.strip.set_engine("MINIMOS 6.1")
        self.strip.show_running("Simulando o dispositivo…", 0.0, 0.3)

    def _on_device_finished(self, caixa) -> None:
        """A corrida do MINIMOS entra no mesmo índice das do SUPREM."""
        registro = workspace.record_dir(
            caixa.get("__dir__"),
            name=f"{self.project.name} — dispositivo",
            engine="MINIMOS 6.1")
        if registro is not None:
            self.resultados.reload()
            self.inicio.refresh()
        tem_curva = bool((caixa.get("iv") or "").strip())
        self.strip.show_done(
            "Simulação de dispositivo concluída" if tem_curva else
            "O MINIMOS terminou, mas não escreveu a tabela de correntes", 0.0)

    # ── encerramento ──────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        if self._run.running:
            self._run.cancel()
        # A sessão do Console é um processo do motor vivo; sem isto ele fica
        # órfão quando a janela fecha.
        self.console.close_session()
        self.inicio.shutdown()
        for thread in (self._evolucao, self.dispositivo._worker,
                       self.oxidacao._worker):
            if thread is not None:
                if hasattr(thread, "stop"):
                    thread.stop()
                thread.wait(5000)
        super().closeEvent(event)


def tour_mod_steps(tour) -> tuple:
    """Os passos do roteiro em curso, ou uma tupla vazia."""
    return tour.steps() or ()


class _EvolutionWorker(QThread):
    """Roda a série de corridas derivadas da evolução fora da interface."""

    done = Signal(bool, str)

    def __init__(self, title: str, steps: list[dict], out_dir, parent=None
                 ) -> None:
        super().__init__(parent)
        self._title = title
        self._steps = steps
        self._out = out_dir

    def run(self) -> None:          # noqa: D102 - API do QThread
        try:
            evolucao = evo.compute(self._title, self._steps)
            if evolucao is None:
                self.done.emit(False, "a série não produziu etapas")
                return
            evolucao.save(self._out)
            self.done.emit(True, "")
        except Exception as exc:    # noqa: BLE001 - não invalida a corrida
            self.done.emit(False, str(exc))
