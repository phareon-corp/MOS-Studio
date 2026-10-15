"""A interface monta, navega e edita a receita de ponta a ponta.

Roda com a plataforma ``offscreen`` do Qt, sem precisar de tela.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    TEM_QT = True
except ImportError:                                  # pragma: no cover
    TEM_QT = False


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class BaseUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mos_studio.app import build_application
        cls.app = QApplication.instance() or QApplication([])
        from mos_studio.ui import theme
        theme.apply(cls.app, "claro")

    def setUp(self):
        from mos_studio.ui.main_window import MainWindow
        self.janela = MainWindow()

    def tearDown(self):
        self.janela.close()
        self.janela.deleteLater()
        self.app.processEvents()


class TestMontagem(BaseUI):
    def test_abre_na_tela_de_inicio(self):
        """O app abre na tela de Início, como no mockup."""
        self.assertEqual(self.janela.current_area(), "inicio")

    def test_todas_as_areas_do_design_existem(self):
        """As cinco telas 1-D, as seis do 2-D e os Exemplos, que servem aos
        dois motores."""
        self.assertEqual(sorted(self.janela._indices),
                         ["console", "dispositivo", "estrutura", "exemplos",
                          "inicio", "malha", "modelos", "oxidacao",
                          "processo", "processo2d", "resultados",
                          "resultados2d"])

    def test_no_inicio_nao_se_simula(self):
        """Nada para simular antes de abrir um projeto."""
        self.janela.go("inicio")
        self.janela.start_run()
        self.assertFalse(self.janela._run.running)

    def test_navega_entre_as_areas(self):
        for area in ("resultados", "dispositivo", "oxidacao", "processo"):
            self.janela.go(area)
            with self.subTest(area=area):
                self.assertEqual(self.janela.current_area(), area)

    def test_receita_inicial_e_valida(self):
        self.assertTrue(self.janela.processo.steps)
        self.assertEqual(self.janela.processo.issues(), [])

    def test_rodape_mostra_os_dois_motores(self):
        self.assertIn("SUPREM", self.janela.footer._txt_sup.text().upper())
        self.assertIn("MINIMOS", self.janela.footer._txt_mm.text().upper())


class TestEdicaoDaReceita(BaseUI):
    def setUp(self):
        super().setUp()
        self.tela = self.janela.processo

    def test_adicionar_etapa(self):
        antes = len(self.tela.steps)
        self.tela.add_step("IMPLANTI")
        self.assertEqual(len(self.tela.steps), antes + 1)
        self.assertEqual(self.tela.selected_step.type, "IMPLANTI")

    def test_adicionar_insere_depois_da_selecionada(self):
        self.tela.select_step(self.tela.steps[0].uid)
        self.tela.add_step("ETCH")
        self.assertEqual(self.tela.steps[1].type, "ETCH")

    def test_remover_etapa(self):
        antes = len(self.tela.steps)
        self.tela.select_step(self.tela.steps[1].uid)
        self.tela.remove_selected()
        self.assertEqual(len(self.tela.steps), antes - 1)

    def test_duplicar_etapa(self):
        self.tela.select_step(self.tela.steps[1].uid)
        antes = len(self.tela.steps)
        self.tela.duplicate_selected()
        self.assertEqual(len(self.tela.steps), antes + 1)
        self.assertEqual(self.tela.steps[1].type, self.tela.steps[2].type)
        self.assertNotEqual(self.tela.steps[1].uid, self.tela.steps[2].uid)

    def test_mover_etapa(self):
        primeira, segunda = self.tela.steps[0].uid, self.tela.steps[1].uid
        self.tela.select_step(segunda)
        self.tela.move_selected(-1)
        self.assertEqual([s.uid for s in self.tela.steps[:2]], [segunda, primeira])

    def test_reordenar_por_arrastar(self):
        ordem = [s.uid for s in self.tela.steps]
        self.tela._on_reordered(0, 2)
        self.assertEqual([s.uid for s in self.tela.steps][:3],
                         [ordem[1], ordem[2], ordem[0]])

    def test_desfazer_e_refazer(self):
        antes = len(self.tela.steps)
        self.tela.add_step("ETCH")
        self.assertEqual(len(self.tela.steps), antes + 1)
        self.tela.undo()
        self.assertEqual(len(self.tela.steps), antes)
        self.tela.redo()
        self.assertEqual(len(self.tela.steps), antes + 1)

    def test_desfazer_sem_historico_nao_quebra(self):
        self.tela.undo()
        self.tela.redo()
        self.assertTrue(self.tela.steps)

    def test_lista_acompanha_a_receita(self):
        self.tela.add_step("ETCH")
        self.assertEqual(self.tela.lista.count(), len(self.tela.steps))

    def test_alterar_parametro_muda_o_deck(self):
        passo = next(s for s in self.tela.steps if s.type == "DIFFUSION")
        self.tela.select_step(passo.uid)
        self.tela._on_param_changed(passo.uid, "temperature", "1123")
        self.assertIn("TEMPERAT=1123", self.tela.deck_text())


class TestVerificacaoNaInterface(BaseUI):
    def setUp(self):
        super().setUp()
        self.tela = self.janela.processo

    def test_valor_fora_da_faixa_bloqueia_a_simulacao(self):
        self.janela.go("processo")
        passo = next(s for s in self.tela.steps if s.type == "DIFFUSION")
        self.tela._on_param_changed(passo.uid, "temperature", "1400")
        self.assertTrue(self.tela.issues())
        self.janela._refresh_run_button()
        self.assertEqual(self.janela.header._pilha.currentIndex(), 1)  # bloqueado

    def test_receita_valida_libera_a_simulacao(self):
        self.janela.go("processo")
        self.janela._refresh_run_button()
        self.assertEqual(self.janela.header._pilha.currentIndex(), 0)

    def test_ir_para_o_primeiro_problema_seleciona_a_etapa(self):
        passo = next(s for s in self.tela.steps if s.type == "DIFFUSION")
        self.tela._on_param_changed(passo.uid, "time", "0")
        self.janela._go_to_first_issue()
        self.assertEqual(self.tela.selected_step.uid, passo.uid)


class TestDeck(BaseUI):
    def setUp(self):
        super().setUp()
        self.tela = self.janela.processo

    def test_deck_gerado_bate_com_a_receita(self):
        from mos_studio.core.deck import build_in_file
        esperado = build_in_file(self.tela.title,
                                 [s.as_dict() for s in self.tela.steps])
        self.assertEqual(self.tela.deck_text(), esperado)

    def test_edicao_manual_tem_precedencia(self):
        self.tela._start_manual_edit()
        self.assertTrue(self.tela.manual_deck)
        self.tela.deck.view.setPlainText("TITLE MANUAL\nSTOP")
        self.assertIn("TITLE MANUAL", self.tela.deck_text())

    def test_descartar_volta_para_a_receita(self):
        self.tela._start_manual_edit()
        self.tela.deck.view.setPlainText("TITLE MANUAL\nSTOP")
        self.tela._discard_manual_edit()
        self.assertFalse(self.tela.manual_deck)
        self.assertIn(self.tela.title, self.tela.deck_text())

    def test_clicar_na_linha_seleciona_a_etapa(self):
        linhas = self.tela.deck_lines()
        indice = next(i for i, (_t, uid) in enumerate(linhas) if uid is not None)
        self.tela.deck._on_line_clicked(indice + 1)
        self.assertEqual(self.tela.selected_step.uid, linhas[indice][1])

    def test_deck_pode_ser_escondido(self):
        self.tela.hide_deck()
        self.assertFalse(self.tela.deck.isVisible())
        self.tela.show_deck()


class TestFormulario(BaseUI):
    def test_mostra_rotulo_unidade_e_faixa(self):
        from mos_studio.core.recipe import Step
        from mos_studio.ui.widgets.step_form import StepForm
        form = StepForm()
        passo = Step.new("DIFFUSION")
        form.show_step(passo, 1, 1)
        linha = form._rows["temperature"]
        self.assertEqual(linha.field.label, "Temperatura")
        self.assertEqual(linha.field.unit, "°C")
        self.assertIn("700", linha._hint.text())

    def test_marca_o_campo_invalido(self):
        from mos_studio.core.recipe import Step
        from mos_studio.ui.widgets.step_form import StepForm
        form = StepForm()
        passo = Step.new("DIFFUSION")
        passo.params["temperature"] = "1400"
        form.show_step(passo, 1, 1)
        linha = form._rows["temperature"]
        self.assertEqual(linha._editor.property("state"), "invalid")

    def test_todo_tipo_monta_formulario(self):
        from mos_studio.core.recipe import STEP_TYPES, Step
        from mos_studio.ui.widgets.step_form import StepForm
        form = StepForm()
        for tipo in STEP_TYPES:
            with self.subTest(tipo=tipo):
                form.show_step(Step.new(tipo), 1, 1)
                self.assertTrue(form._rows)


class TestGrafico(BaseUI):
    def test_estado_vazio(self):
        from mos_studio.ui.widgets.profile_chart import ProfileChart
        g = ProfileChart()
        self.assertFalse(g.has_data)

    def test_desenha_o_perfil(self):
        from PySide6.QtGui import QPixmap
        from mos_studio.ui.widgets.profile_chart import (ChartData, ProfileChart,
                                                         Series)
        g = ProfileChart()
        g.resize(600, 300)
        pontos = [(i * 0.01, 1e18 / (1 + i)) for i in range(60)]
        g.set_data(ChartData(series=[Series("Líquido", pontos)], junctions=[0.3]))
        self.assertTrue(g.has_data)
        pm = QPixmap(g.size())
        g.render(pm)                     # não pode levantar exceção
        self.assertFalse(pm.isNull())

    def test_passo_do_eixo_e_legivel(self):
        from mos_studio.ui.widgets.profile_chart import nice_step
        for span, esperado in ((0.49, 0.1), (1.0, 0.2), (2.0, 0.5), (12.0, 5.0)):
            with self.subTest(span=span):
                self.assertAlmostEqual(nice_step(span), esperado)


class TestResultados(BaseUI):
    """A tela de resultados agora mostra execuções gravadas, não objetos soltos.

    Cada teste escreve uma pasta de execução de mentira numa pasta de trabalho
    temporária, registra-a e pede à tela que a mostre — o mesmo caminho que o
    app percorre depois de uma corrida de verdade.
    """

    def setUp(self):
        super().setUp()
        import os
        import tempfile
        from pathlib import Path
        from mos_studio.core import workspace
        self._tmp = tempfile.TemporaryDirectory()
        self._xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        workspace.set_working_dir(Path(self._tmp.name) / "trabalho")

    def tearDown(self):
        import os
        if self._xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._xdg
        self._tmp.cleanup()
        super().tearDown()

    def _mostrar(self, tabela: list[tuple[float, float]]):
        """Escreve uma saída do SUPREM com esta tabela e a põe na tela."""
        from mos_studio.core import workspace
        pasta = workspace.runs_dir() / "corrida"
        pasta.mkdir(parents=True, exist_ok=True)
        # mesmo formato do SUPREM: cabeçalho da curva e duas colunas
        linhas = ["1-Net Active", "", "     depth   concentration"]
        for prof, net in tabela:
            linhas.append(f"     {prof:.4f}    {net:.5E}")
        (pasta / "A.OUT").write_text("\n".join(linhas) + "\n",
                                     encoding="latin-1")
        (pasta / "INPUT.IN").write_text("TITLE TESTE\r\nSTOP\r\n",
                                        encoding="latin-1")
        registro = workspace.record_dir(pasta, name="Teste")
        self.janela.resultados.reload(registro)
        return registro

    def test_mostra_o_perfil_e_a_juncao(self):
        perfil = [(i * 0.01, 9e17 * (1 - i / 30) if i < 30 else -1e15)
                  for i in range(60)]
        self._mostrar(perfil)
        self.assertTrue(self.janela.resultados._grafico.has_data)
        self.assertNotEqual(self.janela.resultados._xj.text(), "—")

    def test_execucao_sem_tabela_explica_o_que_houve(self):
        self._mostrar([])
        self.assertEqual(self.janela.resultados._xj.text(), "—")
        self.assertIn("não", self.janela.resultados._xj_nota.text().lower())


class TestTempoDecorrido(unittest.TestCase):
    def test_formato_do_design(self):
        from mos_studio.ui.run_controller import format_elapsed
        self.assertEqual(format_elapsed(4.84), "00:04,8")
        self.assertEqual(format_elapsed(0), "00:00,0")
        self.assertEqual(format_elapsed(65.2), "01:05,2")


if __name__ == "__main__":
    unittest.main()
