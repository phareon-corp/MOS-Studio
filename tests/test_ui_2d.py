"""As telas do motor 2-D, montadas e navegadas de ponta a ponta.

Roda com a plataforma ``offscreen`` do Qt, sem precisar de tela. O teste que
sobe o motor de verdade está em :class:`TestExecucao2D` e é pulado quando o
SUPREM-IV não está instalado.
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


def tem_motor4() -> bool:
    from mos_studio.core import suprem4

    return suprem4.find_run_dir() is not None


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class BaseUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from mos_studio.ui import theme
        theme.apply(cls.app, "claro")

    def setUp(self):
        from mos_studio.ui.main_window import MainWindow
        self.janela = MainWindow()
        # Mostrada de propósito: layout, visibilidade e redimensionamento só
        # se comportam como na vida real depois do show().
        self.janela.show()
        self.app.processEvents()

    def tearDown(self):
        self.janela.close()
        self.janela.deleteLater()
        self.app.processEvents()


class TestCabecalho(BaseUI):
    def test_abre_em_uma_dimensao(self):
        self.assertEqual(self.janela.dimension, "1d")

    def test_a_navegacao_muda_com_a_dimensao(self):
        self.janela.header.set_project("teste")
        self.janela.set_dimension("1d")
        um = self.janela.header.areas()
        self.janela.set_dimension("2d")
        dois = self.janela.header.areas()
        self.assertIn("dispositivo", um)
        self.assertNotIn("dispositivo", dois)
        self.assertIn("malha", dois)
        self.assertNotIn("malha", um)

    def test_as_ferramentas_mudam_com_a_dimensao(self):
        self.janela.set_dimension("1d")
        self.assertIn("oxidacao", self.janela.header.areas())
        self.janela.set_dimension("2d")
        self.assertIn("console", self.janela.header.areas())
        self.assertIn("estrutura", self.janela.header.areas())

    def test_exemplos_existe_nas_duas(self):
        """Os exemplos de fábrica servem aos dois motores."""
        for dim in ("1d", "2d"):
            self.janela.set_dimension(dim)
            self.assertIn("exemplos", self.janela.header.areas(), dim)

    def test_o_rotulo_do_botao_segue_a_tela(self):
        self.janela.go("dispositivo")
        self.assertIn("dispositivo", self.janela.header._b_run.text().lower())
        self.janela.go("malha")
        self.assertIn("malha", self.janela.header._b_run.text().lower())

    def test_sem_projeto_a_pilula_some(self):
        self.janela.header.set_project("")
        self.assertTrue(self.janela.header._dims.isHidden())


class TestNavegacao(BaseUI):
    def test_ir_para_uma_tela_2d_troca_a_dimensao(self):
        self.janela.go("malha")
        self.assertEqual(self.janela.dimension, "2d")
        self.assertEqual(self.janela.current_area(), "malha")

    def test_voltar_para_uma_tela_1d_troca_de_volta(self):
        self.janela.go("modelos")
        self.janela.go("dispositivo")
        self.assertEqual(self.janela.dimension, "1d")

    def test_a_troca_mantem_a_tela_equivalente(self):
        self.janela.go("resultados")
        self.janela.set_dimension("2d")
        self.assertEqual(self.janela.current_area(), "resultados2d")
        self.janela.set_dimension("1d")
        self.assertEqual(self.janela.current_area(), "resultados")

    def test_tela_sem_equivalente_cai_no_processo(self):
        self.janela.go("dispositivo")
        self.janela.set_dimension("2d")
        self.assertEqual(self.janela.current_area(), "processo2d")

    def test_todas_as_telas_2d_abrem(self):
        for area in ("malha", "processo2d", "resultados2d", "modelos",
                     "console", "estrutura", "exemplos"):
            self.janela.go(area)
            self.assertEqual(self.janela.current_area(), area)

    def test_o_rodape_nomeia_os_dois_motores_de_processo(self):
        texto = self.janela.footer._txt_sup.text()
        self.assertIn("SUPREM-III", texto)
        self.assertIn("SUPREM-IV", texto)

    def test_o_rodape_nomeia_o_motor_que_falhou(self):
        self.janela.footer.set_engines([], [], ["falta o binário suprem"])
        texto = self.janela.footer._txt_sup.text()
        self.assertIn("SUPREM-IV", texto)
        self.assertIn("BINÁRIO", texto)
        self.janela.footer.set_engines(["falta o genii"], [], [])
        self.assertIn("SUPREM-III", self.janela.footer._txt_sup.text())

    def test_a_direita_do_rodape_conta_os_nos_em_2d(self):
        self.janela.set_dimension("2d")
        self.assertIn("450 nós", self.janela.footer._direita.text())
        self.janela.set_dimension("1d")
        self.assertNotIn("nós", self.janela.footer._direita.text())


class TestMalha(BaseUI):
    def test_abre_com_a_malha_do_exam5(self):
        self.assertEqual(self.janela.malha.stats().nodes, 450)

    def test_editar_uma_linha_refaz_a_contagem(self):
        antes = self.janela.malha.stats().nodes
        self.janela.malha._tabelas["y"]._edit(0, "spacing", "0.01")
        self.assertGreater(self.janela.malha.stats().nodes, antes)

    def test_posicao_invalida_vira_problema(self):
        self.janela.malha._tabelas["x"]._edit(1, "loc", "-1")
        self.assertTrue(self.janela.malha.issues())

    def test_a_malha_chega_ao_deck_do_processo(self):
        self.janela.malha._tabelas["y"]._edit(0, "spacing", "0.01")
        self.janela._on_mesh_changed()
        self.assertIn("spacing=0.01", self.janela.processo2d.deck_text())

    def test_restaurar_volta_ao_padrao(self):
        self.janela.malha._tabelas["y"]._edit(0, "spacing", "0.01")
        self.janela.malha.reset()
        self.assertEqual(self.janela.malha.stats().nodes, 450)

    def test_um_texto_invalido_nao_quebra_a_malha(self):
        self.janela.malha._tabelas["x"]._edit(0, "loc", "abacaxi")
        self.assertEqual(self.janela.malha.issues(), [])


class TestMalhaGrandeDemais(BaseUI):
    """O motor cai acima de ~9.000 nós, sem mensagem.

    Medido bisseccionando uma malha uniforme com só um ``initialize``: 10.653
    nós passam, 11.256 terminam em falha de segmentação. Deixar rodar seria
    gastar minutos para não receber resultado nenhum.
    """

    def _malha_grande(self):
        from mos_studio.core import mesh as M

        return M.Mesh(x=[M.Line(0.0, 0.02), M.Line(1.0, 0.02)],
                      y=[M.Line(0.0, 0.005), M.Line(2.0, 0.02)])

    def test_a_tela_avisa_antes(self):
        self.janela.malha.set_mesh(self._malha_grande())
        self.app.processEvents()
        self.assertTrue(self.janela.malha.stats().risky)
        self.assertIn("cai", self.janela.malha._aviso.text())

    def test_nao_deixa_rodar(self):
        self.janela.set_dimension("2d")
        self.janela.malha.set_mesh(self._malha_grande())
        self.janela._on_mesh_changed()
        self.janela.go("processo2d")
        self.janela.start_run()
        self.app.processEvents()
        self.assertFalse(self.janela._run.running)
        self.assertEqual(self.janela.current_area(), "malha")

    def test_a_malha_padrao_roda(self):
        self.janela.set_dimension("2d")
        self.janela.malha.reset()
        self.app.processEvents()
        self.assertFalse(self.janela.malha.stats().risky)


class TestProcesso2D(BaseUI):
    def test_abre_com_a_receita_do_ldd(self):
        self.assertEqual(len(self.janela.processo2d.steps), 10)
        self.assertEqual(self.janela.processo2d.issues(), [])

    def test_o_deck_traz_malha_e_etapas(self):
        texto = self.janela.processo2d.deck_text()
        self.assertIn("mode two.dim", texto)
        self.assertIn("init boron", texto)
        self.assertLess(texto.index("line x"), texto.index("init boron"))

    def test_cada_linha_do_deck_sabe_de_que_etapa_veio(self):
        pares = self.janela.processo2d.deck_lines()
        uids = {s.uid for s in self.janela.processo2d.steps} | {None}
        for _texto, uid in pares:
            self.assertIn(uid, uids)

    def test_desfazer_e_refazer(self):
        tela = self.janela.processo2d
        antes = len(tela.steps)
        tela.add_step("IMPLANT")
        self.assertEqual(len(tela.steps), antes + 1)
        tela.undo()
        self.assertEqual(len(tela.steps), antes)
        tela.redo()
        self.assertEqual(len(tela.steps), antes + 1)

    def test_problema_na_malha_aparece_na_receita(self):
        self.janela.malha._tabelas["x"]._edit(1, "loc", "-1")
        self.janela._on_mesh_changed()
        self.assertTrue(any("Malha" in p.message
                            for p in self.janela.processo2d.issues()))

    def test_problema_bloqueia_a_simulacao(self):
        self.janela.go("processo2d")
        self.janela.processo2d.steps[0].params["conc"] = "1E30"
        self.janela.processo2d.refresh()
        self.janela.start_run()
        self.assertFalse(self.janela._run.running)


class TestResultados2D(BaseUI):
    def test_sem_execucao_a_tela_explica_em_vez_de_ficar_em_branco(self):
        tela = self.janela.resultados2d
        self.assertEqual(tela._xj.text(), "—")
        self.assertIn("Rode o processo", tela._xj_nota.text())
        self.assertTrue(tela._comandos.text())

    def test_os_niveis_de_contorno_ligam_e_desligam(self):
        tela = self.janela.resultados2d
        antes = len(tela.levels())
        tela._toggle_level(1e20, True)
        self.assertEqual(len(tela.levels()), antes + 1)
        tela._toggle_level(1e20, False)
        self.assertEqual(len(tela.levels()), antes)

    def test_trocar_de_especie_pede_nova_varredura(self):
        """A grandeza é escolhida no deck; o motor não guarda o que não foi
        pedido, então mudar de espécie exige rodar de novo."""
        pedidos = []
        self.janela.resultados2d.scan_requested.connect(pedidos.append)
        self.janela.resultados2d._pick_species("arsenic")
        self.assertEqual(pedidos, ["arsenic"])

    def test_a_mesma_especie_nao_pede_nada(self):
        pedidos = []
        self.janela.resultados2d.scan_requested.connect(pedidos.append)
        self.janela.resultados2d._pick_species("doping")
        self.assertEqual(pedidos, [])


class TestModelos(BaseUI):
    def test_abre_sem_nada_alterado(self):
        self.assertEqual(self.janela.modelos.cards(), [])

    def test_alterar_um_valor_gera_cartao(self):
        from mos_studio.core import models4

        tela = self.janela.modelos
        tela.select_group("int")
        tela._on_value("D.0", "2e6")
        self.assertEqual(tela.cards(), ["interstitial silicon D.0=2e6"])

    def test_voltar_ao_padrao_tira_o_cartao(self):
        tela = self.janela.modelos
        tela.select_group("int")
        tela._on_value("D.0", "2e6")
        tela._reset_group()
        self.assertEqual(tela.cards(), [])

    def test_o_cartao_entra_no_deck_da_execucao(self):
        tela = self.janela.modelos
        tela.select_group("int")
        tela._on_value("D.0", "2e6")
        self.janela.set_dimension("2d")
        self.assertIn("interstitial silicon D.0=2e6",
                      self.janela._scan_deck())

    def test_os_modelos_vem_antes_das_etapas(self):
        """Um coeficiente aplicado depois da difusão já não valeria."""
        tela = self.janela.modelos
        tela.select_group("int")
        tela._on_value("D.0", "2e6")
        deck = self.janela._scan_deck()
        self.assertLess(deck.index("interstitial silicon"),
                        deck.index("init boron"))


class TestExemplos(BaseUI):
    @unittest.skipUnless(tem_motor4(), "SUPREM-IV não está instalado")
    def test_lista_os_exemplos_instalados(self):
        self.assertGreaterEqual(len(self.janela.exemplos.examples()), 10)

    @unittest.skipUnless(tem_motor4(), "SUPREM-IV não está instalado")
    def test_o_filtro_de_dimensao(self):
        tela = self.janela.exemplos
        tela._filter("1-D")
        self.assertTrue(all(e.dim == "1-D" for e in tela.examples()))
        tela._filter("2-D")
        self.assertTrue(all(e.dim == "2-D" for e in tela.examples()))


class TestRoteiros(BaseUI):
    def test_o_passeio_tem_treze_passos(self):
        self.janela.start_tour()
        self.assertEqual(len(self.janela.tour.steps()), 13)
        self.janela.tour.stop()

    def test_o_passeio_avanca_quando_a_acao_e_feita(self):
        self.janela.start_tour()
        self.janela.tour.next()                       # "Escolha o motor"
        self.assertEqual(self.janela.tour.current().target, "dim")
        self.janela.set_dimension("2d")
        self.janela.tour._poll()
        self.assertEqual(self.janela.tour.current().target, "nav-malha")
        self.janela.tour.stop()

    def test_todo_alvo_do_passeio_esta_registrado(self):
        from mos_studio.core import tour as tour_mod

        self.janela.set_dimension("2d")
        self.janela._register_tour_targets()
        for passo in tour_mod.UI_TOUR:
            if passo.target:
                self.assertIn(passo.target, self.janela.tour._targets,
                              passo.title)

    def test_o_projeto_guiado_comeca_vazio(self):
        self.janela.start_guided_project()
        self.assertEqual(len(self.janela.processo2d.steps), 0)
        self.assertEqual(self.janela.dimension, "2d")
        self.janela.tour.stop()

    def test_o_projeto_guiado_monta_as_doze_etapas(self):
        from mos_studio.core import tour as tour_mod

        self.janela.start_guided_project()
        for _ in tour_mod.LDD_STEPS:
            self.janela.add_guided_step()
        self.assertEqual(len(self.janela.processo2d.steps),
                         len(tour_mod.LDD_STEPS))
        self.assertEqual(self.janela.processo2d.issues(), [])
        self.assertEqual(self.janela.processo2d.warnings(), [])
        self.janela.tour.stop()

    def test_o_guiado_nao_passa_do_roteiro(self):
        from mos_studio.core import tour as tour_mod

        self.janela.start_guided_project()
        for _ in range(len(tour_mod.LDD_STEPS) + 5):
            self.janela.add_guided_step()
        self.assertEqual(len(self.janela.processo2d.steps),
                         len(tour_mod.LDD_STEPS))
        self.janela.tour.stop()

    def test_sair_do_guiado_esconde_o_botao(self):
        self.janela.start_guided_project()
        self.janela.tour.stop()
        self.app.processEvents()
        self.assertTrue(self.janela.processo2d.b_guiado.isHidden())


class TestResponsividade(BaseUI):
    """O cabeçalho e as grades acompanham a largura da janela.

    Antes, no tamanho mínimo da própria janela (1280×760), o Qt espremia os
    botões da navegação e cortava cada palavra — "Proces", "Resulta",
    "Model" — e as grades de cartões tinham número fixo de colunas.
    """

    def _larguras(self):
        return (1920, 1600, 1440, 1366, 1280)

    def test_nenhum_rotulo_da_navegacao_e_cortado(self):
        for dim in ("1d", "2d"):
            for larg in self._larguras():
                self.janela.resize(larg, 800)
                self.janela.set_dimension(dim)
                self.app.processEvents()
                for chave, b in self.janela.header._buttons.items():
                    self.assertGreaterEqual(
                        b.width(), b.sizeHint().width() - 1,
                        f"{chave} cortado em {dim} a {larg}px")

    def test_a_largura_folgada_mostra_tudo(self):
        self.janela.resize(1920, 900)
        self.janela.set_dimension("2d")
        self.app.processEvents()
        self.assertEqual(self.janela.header._compact, 0)
        self.assertFalse(self.janela.header._ferramentas.isHidden())
        self.assertIn("01", self.janela.header._buttons["malha"].text())

    def test_a_largura_apertada_sacrifica_na_ordem(self):
        """Primeiro a palavra "ferramentas", depois os números."""
        h = self.janela.header
        self.janela.set_dimension("2d")
        self.janela.resize(1920, 900)
        self.app.processEvents()
        folgado = h._compact
        self.janela.resize(1280, 800)
        self.app.processEvents()
        self.assertGreater(h._compact, folgado)

    def test_o_nivel_volta_ao_alargar(self):
        h = self.janela.header
        self.janela.set_dimension("2d")
        self.janela.resize(1280, 800)
        self.app.processEvents()
        apertado = h._compact
        self.janela.resize(1920, 900)
        self.app.processEvents()
        self.assertLess(h._compact, apertado)

    def test_a_pilha_do_botao_segue_a_pagina_visivel(self):
        """Senão a página de "executando" manda na largura o tempo todo."""
        h = self.janela.header
        h.show_idle()
        self.app.processEvents()
        parado = h._pilha.width()
        h.show_running(1.0)
        self.app.processEvents()
        self.assertNotEqual(h._pilha.width(), 0)
        h.show_idle()
        self.app.processEvents()
        self.assertEqual(h._pilha.width(), parado)

    def _colunas(self, area: str, grade_attr: str, larg: int) -> int:
        """Colunas da grade daquela tela com a janela nesta largura."""
        self.janela.resize(larg, 820)
        self.janela.go(area)
        for _ in range(3):
            self.app.processEvents()
        return getattr(getattr(self.janela, area), grade_attr).columns()

    def test_a_grade_de_exemplos_refluir(self):
        largo = self._colunas("exemplos", "_grade", 1920)
        estreito = self._colunas("exemplos", "_grade", 1280)
        self.assertLess(estreito, largo)
        self.assertGreaterEqual(estreito, 1)

    def test_a_grade_de_estruturas_refluir(self):
        largo = self._colunas("estrutura", "_cartoes", 1920)
        estreito = self._colunas("estrutura", "_cartoes", 1280)
        self.assertLess(estreito, largo)
        self.assertGreaterEqual(estreito, 1)

    def test_a_grade_nunca_passa_do_numero_de_itens(self):
        from mos_studio.ui.screens.estrutura import ACTIONS

        colunas = self._colunas("estrutura", "_cartoes", 3000)
        self.assertLessEqual(colunas, len(ACTIONS))


class TestCartaoDoRoteiro(BaseUI):
    """O cartão do passeio, como no arquivo de design."""

    def test_tem_a_barra_de_progresso_e_a_identificacao(self):
        self.janela.start_tour()
        t = self.janela.tour
        self.assertEqual(t._progresso._total, len(t.steps()))
        self.assertIn("1 / 13", t._eyebrow.text())
        t.stop()

    def test_o_botao_muda_de_rotulo(self):
        t = self.janela.tour
        self.janela.start_tour()
        self.assertEqual(t._b_proximo.text(), "Próximo")
        t.next()                                   # passo que pede ação
        self.assertTrue(t.waiting())
        self.assertEqual(t._b_proximo.text(), "Pular")
        t._index = len(t.steps()) - 1
        t._refresh(animate=False)
        self.assertEqual(t._b_proximo.text(), "Concluir")
        t.stop()

    def test_voltar_so_aparece_depois_do_primeiro(self):
        t = self.janela.tour
        self.janela.start_tour()
        self.app.processEvents()
        self.assertTrue(t._b_voltar.isHidden())
        t.next()
        self.app.processEvents()
        self.assertFalse(t._b_voltar.isHidden())
        t.stop()

    def test_o_cartao_nunca_sai_da_janela(self):
        t = self.janela.tour
        for larg, alt in ((1920, 1080), (1440, 860), (1280, 760)):
            self.janela.resize(larg, alt)
            self.app.processEvents()
            self.janela.set_dimension("2d")
            self.janela.start_tour()
            L, A = self.janela.width(), self.janela.height()
            for i in range(len(t.steps())):
                t._index = i
                t._refresh(animate=False)
                self.app.processEvents()
                r = t._card.geometry()
                self.assertGreaterEqual(r.left(), 0, f"passo {i} a {L}px")
                self.assertGreaterEqual(r.top(), 0, f"passo {i} a {L}px")
                self.assertLessEqual(r.right(), L, f"passo {i} a {L}px")
                self.assertLessEqual(r.bottom(), A, f"passo {i} a {L}px")
            t.stop()

    def test_o_cartao_nao_tapa_o_destaque(self):
        t = self.janela.tour
        self.janela.resize(1600, 900)
        self.app.processEvents()
        self.janela.set_dimension("2d")
        self.janela.start_tour()
        for i in range(len(t.steps())):
            t._index = i
            t._refresh(animate=False)
            self.app.processEvents()
            if not t._wanted.isNull():
                self.assertFalse(t._card.geometry().intersects(t._wanted),
                                 f"o cartão tapa o alvo no passo {i}")
        t.stop()

    def test_o_cartao_cede_largura_numa_janela_estreita(self):
        t = self.janela.tour
        self.janela.start_tour()
        self.janela.resize(1600, 900)
        self.app.processEvents()
        t._fit_card_width()
        largo = t._card.width()
        t.setGeometry(0, 0, 360, 600)
        t._fit_card_width()
        self.assertLess(t._card.width(), largo)
        t.stop()

    def test_sair_encerra_o_roteiro(self):
        t = self.janela.tour
        self.janela.start_tour()
        self.assertTrue(t.running)
        t.stop()
        self.assertFalse(t.running)


class TestExemplos1D(BaseUI):
    """A aba de Exemplos traz as receitas 1-D ao lado dos decks de fábrica."""

    def test_lista_as_receitas_editaveis(self):
        ids = [e.id for e in self.janela.exemplos.recipes()]
        self.assertIn("nmos-porta", ids)

    def test_o_filtro_2d_esconde_as_receitas_1d(self):
        tela = self.janela.exemplos
        tela._filter("2-D")
        self.assertEqual(tela.recipes(), [])
        tela._filter("1-D")
        self.assertTrue(tela.recipes())

    def test_a_secao_some_quando_nao_ha_receita(self):
        tela = self.janela.exemplos
        tela._filter("2-D")
        self.app.processEvents()
        self.assertTrue(tela._grade_1d.isHidden())
        tela._filter("")
        self.app.processEvents()
        self.assertFalse(tela._grade_1d.isHidden())

    def test_abrir_uma_receita_vira_projeto_1d(self):
        from mos_studio.core import examples3

        self.janela.set_dimension("2d")
        self.janela.open_recipe_1d("nmos-porta")
        self.app.processEvents()
        self.assertEqual(self.janela.dimension, "1d")
        self.assertEqual(self.janela.current_area(), "processo")
        self.assertEqual(len(self.janela.processo.steps),
                         examples3.NMOS_PORTA.step_count)
        self.assertEqual(self.janela.processo.issues(), [])

    def test_a_receita_aberta_e_editavel_e_independente(self):
        self.janela.open_recipe_1d("nmos-porta")
        self.app.processEvents()
        antes = len(self.janela.processo.steps)
        self.janela.processo.add_step("ETCH")
        self.assertEqual(len(self.janela.processo.steps), antes + 1)
        # Abrir de novo traz a receita original, não a editada.
        self.janela.open_recipe_1d("nmos-porta")
        self.app.processEvents()
        self.assertEqual(len(self.janela.processo.steps), antes)

    def test_a_faixa_diz_o_que_esperar(self):
        self.janela.open_recipe_1d("nmos-porta")
        self.app.processEvents()
        self.assertIn("28 nm", self.janela.strip._text.text())

    def test_id_desconhecido_nao_quebra(self):
        antes = self.janela.project.name
        self.janela.open_recipe_1d("nao.existe")
        self.assertEqual(self.janela.project.name, antes)


class TestEixoDoPerfil(BaseUI):
    """O eixo logarítmico não abre mais décadas do que cabe ler.

    Um perfil por espécie cai a valores como 10⁻²⁸ cm⁻³ longe da superfície —
    zero numérico do motor. Sem piso, o eixo abria quarenta e oito décadas e
    espremia a curva inteira numa faixa de poucos pixels.
    """

    def test_limita_o_numero_de_decadas(self):
        from mos_studio.ui.widgets.profile_chart import (ChartData,
                                                         MAX_DECADES, Series)

        grafico = self.janela.resultados2d.chart
        grafico.set_data(ChartData(series=[Series(
            label="t", points=[(0.0, 1e20), (0.5, 1e2), (1.0, 1e-28)])]))
        _, lo, hi = grafico._bounds()
        self.assertLessEqual(hi - lo, MAX_DECADES)

    def test_um_perfil_estreito_mantem_a_propria_faixa(self):
        from mos_studio.ui.widgets.profile_chart import ChartData, Series

        grafico = self.janela.resultados2d.chart
        grafico.set_data(ChartData(series=[Series(
            label="t", points=[(0.0, 1e18), (1.0, 1e16)])]))
        _, lo, hi = grafico._bounds()
        self.assertAlmostEqual(lo, 16.0)
        self.assertAlmostEqual(hi, 18.0)


class TestCliqueNoRoteiro(BaseUI):
    """O clique precisa chegar ao alvo destacado, de primeira.

    O cartão do roteiro é irmão da camada escura, não filho: para o clique
    passar para a interface, a camada fica transparente ao mouse, e o Qt não
    desce o teste de acerto por dentro de um widget transparente — o que
    levava os botões do cartão junto. A tentativa anterior ligava e desligava
    a transparência por 350 ms a cada clique, e o usuário tinha de clicar
    várias vezes até acertar a janela de tempo.
    """

    def _clicar(self, widget) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        for _ in range(3):
            self.app.processEvents()

    def test_o_cartao_nao_e_filho_da_camada(self):
        t = self.janela.tour
        self.assertIsNot(t._card.parent(), t)
        self.assertIs(t._card.parent(), self.janela)

    def test_a_camada_some_para_o_mouse_quando_ha_destaque(self):
        from PySide6.QtCore import Qt

        t = self.janela.tour
        self.janela.start_tour()
        self.app.processEvents()
        # O primeiro passo não tem alvo: a camada bloqueia.
        self.assertTrue(t._rect.isNull())
        self.assertFalse(t.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        t.next()                                  # passo com alvo
        self.app.processEvents()
        self.assertFalse(t._rect.isNull())
        self.assertTrue(t.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        t.stop()

    def test_o_clique_chega_ao_alvo_de_primeira(self):
        self.janela.resize(1440, 860)
        self.app.processEvents()
        self.janela.start_guided_project()
        self.app.processEvents()
        self.janela.tour.next()
        self.app.processEvents()
        botao = self.janela.processo2d.b_guiado
        self._clicar(botao)
        self.assertEqual(len(self.janela.processo2d.steps), 1)
        self.janela.tour.stop()

    def test_o_alvo_recebe_o_clique_e_nao_a_camada(self):
        self.janela.resize(1440, 860)
        self.app.processEvents()
        self.janela.start_guided_project()
        self.janela.tour.next()
        self.app.processEvents()
        botao = self.janela.processo2d.b_guiado
        centro = botao.mapTo(self.janela, botao.rect().center())
        self.assertIs(self.janela.childAt(centro), botao)
        self.janela.tour.stop()

    def test_o_cartao_continua_recebendo_clique(self):
        """Era o que o truque antigo quebrava junto."""
        self.janela.resize(1440, 860)
        self.app.processEvents()
        self.janela.start_guided_project()
        t = self.janela.tour
        t.next()
        self.app.processEvents()
        antes = t.index
        self._clicar(t._b_proximo)               # "Pular"
        self.assertEqual(t.index, antes + 1)
        t.stop()

    def test_um_clique_por_etapa_monta_o_ldd(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from mos_studio.core import tour as tour_mod

        self.janela.resize(1440, 860)
        self.app.processEvents()
        self.janela.start_guided_project()
        t = self.janela.tour
        t.next()
        botao = self.janela.processo2d.b_guiado
        for i in range(len(tour_mod.LDD_STEPS)):
            self.assertEqual(t.current().target, "addstep",
                             f"o roteiro parou na etapa {i + 1}")
            QTest.mouseClick(botao, Qt.MouseButton.LeftButton)
            for _ in range(3):
                self.app.processEvents()
            QTest.qWait(300)                      # o destaque confere a ação
            self.app.processEvents()
            self.assertEqual(len(self.janela.processo2d.steps), i + 1)
        self.assertEqual(self.janela.processo2d.issues(), [])
        t.stop()


class TestPularFazAAcao(BaseUI):
    """"Pular" pula o fazer-você-mesmo, não o efeito do passo.

    Sem isto, quem clicasse no botão da direita do começo ao fim terminava o
    passeio com o aplicativo ainda na tela de Início — treze cartões falando
    de telas que nunca apareceram.
    """

    def _andar(self, limite: int = 20) -> list[str]:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        t = self.janela.tour
        areas = []
        for _ in range(limite):
            if not t.running:
                break
            QTest.mouseClick(t._b_proximo, Qt.MouseButton.LeftButton)
            for _ in range(4):
                self.app.processEvents()
            QTest.qWait(120)
            self.app.processEvents()
            areas.append(self.janela.current_area())
        return areas

    def test_todo_passo_com_acao_sabe_faze_la(self):
        from mos_studio.core import tour as tour_mod

        for roteiro in (tour_mod.UI_TOUR, tour_mod.ldd_tour()):
            for passo in roteiro:
                if passo.action:
                    self.assertIsNotNone(passo.perform, passo.title)

    def test_o_passeio_percorre_as_telas_so_com_o_botao(self):
        self.janela.go("inicio")
        self.app.processEvents()
        self.janela.start_tour()
        self.app.processEvents()
        areas = self._andar()
        self.assertFalse(self.janela.tour.running)
        # Saiu do Início e passou pelas telas do motor 2-D.
        for esperada in ("malha", "processo2d", "resultados2d", "modelos",
                         "console"):
            self.assertIn(esperada, areas, f"o passeio não abriu {esperada}")
        self.assertEqual(self.janela.dimension, "2d")

    def test_o_projeto_guiado_se_monta_so_com_o_botao(self):
        from mos_studio.core import tour as tour_mod

        self.janela.start_guided_project()
        self.app.processEvents()
        self._andar()
        self.assertEqual(len(self.janela.processo2d.steps),
                         len(tour_mod.LDD_STEPS))
        self.assertEqual(self.janela.processo2d.issues(), [])
        self.assertEqual(self.janela.current_area(), "resultados2d")

    def test_fazer_a_acao_dispensa_o_pular(self):
        """Quem age não vê o botão agir duas vezes."""
        self.janela.go("inicio")
        self.app.processEvents()
        self.janela.start_tour()
        t = self.janela.tour
        t.next()                                   # "Escolha o motor"
        self.app.processEvents()
        self.janela.set_dimension("2d")            # o usuário age
        t._poll()
        self.app.processEvents()
        self.assertEqual(t.current().target, "nav-malha")
        self.assertEqual(self.janela.dimension, "2d")
        t.stop()


class TestCartaoDeTutorial(BaseUI):
    """O cartão dos roteiros na tela de Início, como no arquivo de design."""

    def _cards(self):
        from mos_studio.ui.screens.inicio import _ClickableCard

        return self.janela.inicio.findChildren(_ClickableCard)

    def test_tem_os_dois_roteiros(self):
        self.assertEqual(len(self._cards()), 2)

    def test_mostra_o_progresso(self):
        self.assertIn("0 DE 2", self.janela.inicio._tut_progresso.text())

    def test_marca_um_roteiro_como_concluido(self):
        self.janela.inicio.mark_tutorial_done("ui")
        self.assertIn("1 DE 2", self.janela.inicio._tut_progresso.text())
        self.assertIn("CONCLUÍDO", self.janela.inicio._tut_marcas["ui"].text())

    def test_o_primeiro_cartao_abre_o_passeio(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(self._cards()[0], Qt.MouseButton.LeftButton)
        for _ in range(3):
            self.app.processEvents()
        self.assertTrue(self.janela.tour.running)
        self.assertEqual(len(self.janela.tour.steps()), 13)
        self.janela.tour.stop()

    def test_o_segundo_cartao_abre_o_projeto_guiado(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        QTest.mouseClick(self._cards()[1], Qt.MouseButton.LeftButton)
        for _ in range(3):
            self.app.processEvents()
        self.assertTrue(self.janela.tour.running)
        self.assertEqual(self.janela.current_area(), "processo2d")
        self.assertEqual(len(self.janela.processo2d.steps), 0)
        self.janela.tour.stop()

    def test_a_descricao_nao_fica_cortada(self):
        """Uma linha só significa que a segunda sumiu."""
        from PySide6.QtWidgets import QLabel

        self.janela.resize(1600, 980)
        self.janela.go("inicio")
        for _ in range(6):
            self.app.processEvents()
        for cartao in self._cards():
            textos = [w for w in cartao.findChildren(QLabel) if w.wordWrap()]
            self.assertTrue(textos)
            for t in textos:
                self.assertGreaterEqual(
                    t.height(), t.heightForWidth(t.width()),
                    "a descrição do tutorial está cortada")


class TestProjeto2D(BaseUI):
    def test_o_projeto_guarda_as_duas_dimensoes(self):
        """Trocar de dimensão não pode apagar o trabalho da outra."""
        self.janela.set_dimension("2d")
        self.janela.processo2d.add_step("IMPLANT")
        self.janela._collect_project()
        self.assertTrue(self.janela.project.steps)      # a receita 1-D
        self.assertTrue(self.janela.project.steps4)     # e a 2-D

    def test_salvar_e_abrir_preserva_o_lado_2d(self):
        import tempfile
        from pathlib import Path
        from mos_studio.core import workspace

        self.janela.set_dimension("2d")
        self.janela.malha._tabelas["y"]._edit(0, "spacing", "0.01")
        self.janela._on_mesh_changed()
        self.janela.modelos.select_group("int")
        self.janela.modelos._on_value("D.0", "2e6")
        self.janela._collect_project()

        destino = Path(tempfile.mkdtemp()) / "p.mosproj"
        self.janela.project.save(destino)
        lido = workspace.Project.load(destino)
        self.assertEqual(lido.dimension, "2d")
        self.assertEqual(len(lido.steps4), 10)
        self.assertAlmostEqual(lido.mesh["y"][0]["spacing"], 0.01)
        self.assertIn("int|_|D.0", lido.models["valores"])

    def test_projeto_antigo_abre_em_uma_dimensao(self):
        from mos_studio.core import workspace

        antigo = {"formato": 1, "nome": "Velho", "titulo": "X",
                  "etapas": [{"tipo": "INITIALIZE", "parametros": {}}]}
        p = workspace.Project.from_dict(antigo)
        self.janela._apply_project(p)
        self.assertEqual(self.janela.dimension, "1d")

    def test_projeto_2d_novo_vem_pronto(self):
        self.janela.new_project_2d()
        self.assertEqual(self.janela.dimension, "2d")
        self.assertEqual(self.janela.current_area(), "processo2d")
        self.assertEqual(self.janela.processo2d.issues(), [])


@unittest.skipUnless(tem_motor4(), "SUPREM-IV não está instalado")
class TestExecucao2D(BaseUI):
    """Sobe o motor de verdade e desenha o resultado."""

    def _rodar(self, timeout_ms: int = 240000) -> bool:
        from PySide6.QtCore import QEventLoop, QTimer

        laco = QEventLoop()
        estado = {}
        self.janela._run.succeeded.connect(
            lambda _r: (estado.update(ok=True), laco.quit()))
        self.janela._run.failed.connect(
            lambda m: (estado.update(erro=m), laco.quit()))
        QTimer.singleShot(timeout_ms, laco.quit)
        self.janela.start_run()
        laco.exec()
        self.app.processEvents()
        return bool(estado.get("ok"))

    def test_o_deck_da_execucao_tem_os_cortes(self):
        self.janela.set_dimension("2d")
        deck = self.janela._scan_deck()
        self.assertIn("select z=doping", deck)
        self.assertGreater(deck.count("print.1d x.value="), 10)

    def test_roda_e_desenha_a_secao(self):
        self.janela.set_dimension("2d")
        self.assertTrue(self._rodar(), "a execução 2-D não concluiu")
        campo = self.janela.resultados2d.field()
        self.assertTrue(campo.ok)
        self.assertEqual(self.janela.current_area(), "resultados2d")

    def test_a_faixa_assina_o_motor_certo(self):
        self.janela.set_dimension("2d")
        self.assertTrue(self._rodar())
        self.assertIn("SUPREM-IV", self.janela.strip._engine.text())

    def test_a_juncao_do_ldd_tem_o_perfil_esperado(self):
        """Rasa sob o espaçador, funda na fonte/dreno, ausente sob a porta."""
        from mos_studio.core import field2d

        self.janela.set_dimension("2d")
        self.assertTrue(self._rodar())
        campo = self.janela.resultados2d.field()
        self.assertIsNone(field2d.junction_depth_at(campo, 0.0))
        extensao = field2d.junction_depth_at(campo, 0.45)
        fonte = field2d.junction_depth_at(campo, 0.95)
        self.assertIsNotNone(extensao)
        self.assertIsNotNone(fonte)
        self.assertLess(extensao, fonte)


@unittest.skipUnless(tem_motor4(), "SUPREM-IV não está instalado")
class TestConsole(BaseUI):
    def test_o_console_sobe_ao_abrir(self):
        self.janela.go("console")
        self.assertTrue(self.janela.console._shell is not None)

    def test_responde_a_um_comando(self):
        self.janela.go("console")
        self.janela.console.run("echo ola")
        self.assertIn("ola", self.janela.console.view.toPlainText())

    def test_barra_comando_do_sistema(self):
        self.janela.go("console")
        self.janela.console.run("rm -rf /tmp/nao.existe.mos")
        self.assertIn("não é um cartão",
                      self.janela.console.view.toPlainText())

    def test_fechar_a_janela_encerra_a_sessao(self):
        self.janela.go("console")
        self.janela.console.ensure_started()
        self.janela.close()
        self.assertFalse(self.janela.console._shell is not None
                         and self.janela.console._shell.alive)


if __name__ == "__main__":
    unittest.main()
