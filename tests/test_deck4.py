"""Tradução da receita para os cartões do SUPREM-IV.GS.

Testes de texto, sem motor: o que se verifica aqui é que a receita vira o
dialeto certo — nomes de impureza, unidades e a malha explícita que o
SUPREM-IV exige e o SUPREM-III dispensava.
"""

from __future__ import annotations

import unittest

from mos_studio.core import deck4 as D4
from mos_studio.core.recipe import DEFAULTS, STEP_TYPES, Step


def codigo(step_type: str, **params) -> list[str]:
    p = dict(DEFAULTS[step_type])
    p.update(params)
    return D4.step_to_code({"type": step_type, "params": p})


class TestMalha(unittest.TestCase):
    """A malha explícita que substitui o par DX/THICKNES."""

    def test_sempre_tem_topo_e_fundo(self):
        for espessura, dx in ((0.5, 5e-3), (0.05, 1e-3), (20.0, 5e-3)):
            with self.subTest(espessura=espessura):
                linhas = D4.mesh_lines(espessura, dx)
                self.assertGreaterEqual(len(linhas), 2)
                self.assertEqual(linhas[0][0], 0.0)
                self.assertAlmostEqual(linhas[-1][0], espessura, places=6)

    def test_posicoes_crescem_sem_repetir(self):
        linhas = D4.mesh_lines(0.5, 5e-3)
        posicoes = [p for p, _ in linhas]
        self.assertEqual(posicoes, sorted(posicoes))
        self.assertEqual(len(posicoes), len(set(posicoes)))

    def test_superficie_tem_o_passo_fino_pedido(self):
        linhas = D4.mesh_lines(2.0, 5e-3)
        self.assertAlmostEqual(linhas[0][1], 5e-3, places=6)

    def test_fundo_tem_passo_mais_folgado_que_a_superficie(self):
        """O perfil mora na superfície; o fundo só precisa fechar o substrato."""
        linhas = D4.mesh_lines(2.0, 5e-3)
        self.assertGreater(linhas[-1][1], linhas[0][1])

    def test_respeita_o_orcamento_de_nos(self):
        """Profundidade grande com passo fino afrouxa o passo em vez de estourar."""
        linhas = D4.mesh_lines(20.0, 1e-5)
        nos = sum(1 for _ in linhas)
        self.assertLessEqual(nos, D4.MAX_MESH_LINES)
        # Afrouxou o passo fino, não a profundidade pedida.
        self.assertGreater(linhas[0][1], 1e-5)
        self.assertAlmostEqual(linhas[-1][0], 20.0, places=6)

    def test_profundidade_rasa_nao_gera_linha_duplicada(self):
        linhas = D4.mesh_lines(0.01, 5e-3)
        posicoes = [round(p, 6) for p, _ in linhas]
        self.assertEqual(len(posicoes), len(set(posicoes)))


class TestInitialize(unittest.TestCase):
    """Um cartão da receita virou cinco do SUPREM-IV."""

    def setUp(self):
        self.linhas = codigo("INITIALIZE")
        self.texto = "\n".join(self.linhas)

    def test_declara_modo_unidimensional(self):
        self.assertEqual(self.linhas[0], "mode one.dim")

    def test_tem_regiao_e_contornos_amarrados_pelas_tags(self):
        self.assertIn("region silicon xlo=topo xhi=fundo", self.texto)
        self.assertIn("boundary exposed xlo=topo xhi=topo", self.texto)
        self.assertIn("boundary backside xlo=fundo xhi=fundo", self.texto)

    def test_as_tags_existem_nas_linhas_de_malha(self):
        """Sem a tag na linha de malha, region/boundary não resolvem."""
        self.assertIn("tag=topo", self.texto)
        self.assertIn("tag=fundo", self.texto)

    def test_superficie_exposta(self):
        """Sem 'exposed' no topo a difusão em O₂ não cresce óxido."""
        self.assertIn("boundary exposed", self.texto)

    def test_init_traduz_o_dopante_e_a_orientacao(self):
        self.assertIn("init boron conc=1e+15 orient=100", self.texto)

    def test_dopante_fosforo_vira_phosphorus(self):
        """'PHOSPHOR' do SUPREM-III não é nome válido no SUPREM-IV."""
        texto = "\n".join(codigo("INITIALIZE", dopant="PHOSPHOR"))
        self.assertIn("init phosphorus", texto)
        self.assertNotIn("phosphor ", texto)


class TestDifusao(unittest.TestCase):
    def test_temperatura_em_celsius_e_tempo_em_minutos(self):
        """diffuse.c soma 273 ao 'temp' lido: o valor vai em °C, não em K."""
        linha = codigo("DIFFUSION", temperature="1000", time="15")[0]
        self.assertIn("temp=1000", linha)
        self.assertIn("time=15", linha)
        self.assertNotIn("1273", linha)

    def test_ambientes_traduzidos(self):
        for receita, esperado in (("DRYO2", "dryo2"), ("WETO2", "weto2"),
                                  ("NITROGEN", "nitrogen"),
                                  ("PHOSPHOR", "phosphorus"),
                                  ("BORON", "boron")):
            with self.subTest(ambiente=receita):
                self.assertIn(esperado, codigo("DIFFUSION", ambient=receita)[0])

    def test_fonte_gasosa_vira_gas_conc(self):
        linha = codigo("DIFFUSION", ambient="PHOSPHOR", gasConc="1E18")[0]
        self.assertIn("gas.conc=1e+18", linha)

    def test_solubilidade_solida(self):
        self.assertIn("solid.sol", codigo("DIFFUSION", solidSol=True)[0])
        self.assertNotIn("solid.sol", codigo("DIFFUSION", solidSol=False)[0])

    def test_rampa_vira_start_e_stop(self):
        """O SUPREM-IV não tem T.RATE: a rampa é start/stop em °C."""
        linha = codigo("DIFFUSION", temperature="900", time="10", tRate="10")[0]
        self.assertIn("ramp", linha)
        self.assertIn("start=900", linha)
        self.assertIn("stop=1000", linha)        # 900 + 10 °C/min × 10 min

    def test_sem_rampa_nao_emite_ramp(self):
        self.assertNotIn("ramp", codigo("DIFFUSION", tRate="")[0])


class TestImplanteDeposicaoCorrosao(unittest.TestCase):
    def test_implante(self):
        linha = codigo("IMPLANTI", dopant="BORON", dose="3E14", energy="70")[0]
        self.assertTrue(linha.startswith("implant boron "))
        self.assertIn("dose=3e+14", linha)
        self.assertIn("energy=70", linha)

    def test_distribuicoes_que_existem(self):
        self.assertIn("pearson", codigo("IMPLANTI", distribution="PEARSON")[0])
        self.assertIn("gauss", codigo("IMPLANTI", distribution="GAUSSIAN")[0])

    def test_distribuicao_inexistente_cai_no_padrao_do_motor(self):
        """BOLTZMAN não existe no SUPREM-IV: melhor omitir que inventar."""
        linha = codigo("IMPLANTI", distribution="BOLTZMAN")[0]
        self.assertNotIn("boltzman", linha.lower())
        self.assertTrue(linha.startswith("implant "))

    def test_deposicao_com_e_sem_dopante(self):
        simples = codigo("DEPOSITION", material="OXIDE", thickness="0.075",
                         dopant="", concentration="")[0]
        self.assertEqual(simples, "deposit oxide thick=0.075")
        dopada = codigo("DEPOSITION", material="POLYSILI", thickness="0.3",
                        dopant="PHOSPHOR", concentration="1E20")[0]
        self.assertIn("deposit poly", dopada)
        self.assertIn("phosphorus concentration=1e+20", dopada)

    def test_polissilicio_vira_poly(self):
        self.assertIn("deposit poly", codigo("DEPOSITION", material="POLYSILI")[0])

    def test_corrosao_total_e_por_espessura(self):
        self.assertEqual(codigo("ETCH", material="OXIDE", all=True)[0],
                         "etch oxide all")
        self.assertEqual(codigo("ETCH", material="NITRIDE", all=False,
                                thickness="0.05")[0],
                         "etch nitride dry thick=0.05")


class TestEpitaxiaEPrint(unittest.TestCase):
    def test_epitaxia_vira_deposicao_dopada(self):
        """Não existe cartão epitaxy; a geometria e a dopagem são preservadas."""
        linha = codigo("EPITAXY", dopant="PHOSPHOR", thickness="1.0",
                       concentration="5E15")[0]
        self.assertTrue(linha.startswith("deposit silicon "))
        self.assertIn("thick=1", linha)
        self.assertIn("phosphorus concentration=5e+15", linha)

    def test_print_vira_select_mais_print_1d(self):
        linhas = codigo("PRINT", what="NET", extra="CONCENTR")
        self.assertEqual(linhas, ["select z=doping", "print.1d"])

    def test_print_de_camadas(self):
        linhas = codigo("PRINT", extra="LAYER")
        self.assertEqual(linhas[1], "print.1d layers")

    def test_print_de_um_dopante(self):
        self.assertEqual(codigo("PRINT", what="BORON")[0], "select z=boron")


class TestAproximacoes(unittest.TestCase):
    """O que a tradução não reproduz fielmente tem de ser dito, não omitido."""

    def test_epitaxia_e_relatada(self):
        avisos = D4.approximations([Step.new("EPITAXY").as_dict()])
        self.assertEqual(len(avisos), 1)
        self.assertIn("Epitaxia", avisos[0])

    def test_distribuicao_sem_equivalente_e_relatada(self):
        passo = Step.new("IMPLANTI").as_dict()
        passo["params"]["distribution"] = "BOLTZMAN"
        avisos = D4.approximations([passo])
        self.assertTrue(any("BOLTZMAN" in a for a in avisos))

    def test_rampa_e_relatada(self):
        passo = Step.new("DIFFUSION").as_dict()
        passo["params"]["tRate"] = "5"
        self.assertTrue(any("Rampa" in a for a in D4.approximations([passo])))

    def test_receita_fiel_nao_gera_aviso(self):
        passos = [Step.new(t).as_dict()
                  for t in ("INITIALIZE", "DIFFUSION", "IMPLANTI",
                            "DEPOSITION", "ETCH", "PRINT")]
        self.assertEqual(D4.approximations(passos), [])

    def test_nao_repete_o_mesmo_aviso(self):
        passos = [Step.new("EPITAXY").as_dict() for _ in range(3)]
        self.assertEqual(len(D4.approximations(passos)), 1)


class TestDeckCompleto(unittest.TestCase):
    def setUp(self):
        self.passos = [Step.new(t).as_dict()
                       for t in ("INITIALIZE", "IMPLANTI", "DIFFUSION", "PRINT")]
        self.deck = D4.build_in_file("Processo de teste", self.passos)

    def test_comeca_com_o_titulo_comentado_e_termina_em_quit(self):
        linhas = self.deck.strip().splitlines()
        self.assertEqual(linhas[0], "# Processo de teste")
        self.assertEqual(linhas[-1], "quit")

    def test_nao_usa_a_sintaxe_do_suprem3(self):
        """TITLE e STOP são cartões do SUPREM-III e o SUPREM-IV os recusa."""
        self.assertNotIn("TITLE ", self.deck)
        self.assertNotIn("STOP", self.deck)

    def test_option_quiet_corta_o_eco_dos_cartoes(self):
        self.assertIn("option quiet", self.deck)

    def test_titulo_volta_pelo_deck_title(self):
        self.assertEqual(D4.deck_title(self.deck), "Processo de teste")

    def test_deck_sem_print_ganha_um_no_fim(self):
        """Um deck sem print.1d roda e não produz tabela nenhuma."""
        sem = D4.build_in_file("Sem tabela",
                               [Step.new("INITIALIZE").as_dict()])
        self.assertIn("print.1d", sem)

    def test_ensure_profile_print_e_idempotente(self):
        uma = D4.ensure_profile_print(self.deck)
        self.assertEqual(uma.count("print.1d"), self.deck.count("print.1d"))

    def test_todos_os_tipos_de_etapa_geram_algo(self):
        """Nenhum tipo do catálogo pode virar deck vazio sem aviso."""
        for t in STEP_TYPES:
            with self.subTest(tipo=t):
                self.assertTrue(D4.step_to_code(Step.new(t).as_dict()),
                                f"{t} não gerou nenhum cartão")

    def test_tipo_desconhecido_nao_levanta(self):
        self.assertEqual(D4.step_to_code({"type": "XYZ", "params": {}}), [])


class TestStripPlot(unittest.TestCase):
    """A camada gráfica é de stubs; e o Bugs do fonte registra travamento."""

    def test_remove_plot_e_contour(self):
        deck = ("option quiet\nselect z=doping\nplot.1d x.max=2\n"
                "contour val=15\nplot.2d grid\nprint.1d\nquit\n")
        limpo = D4.strip_plot(deck)
        for proibido in ("plot.1d", "plot.2d", "contour"):
            self.assertNotIn(proibido, limpo)

    def test_preserva_o_resto(self):
        deck = "option quiet\nselect z=doping\nprint.1d\nquit\n"
        self.assertEqual(D4.strip_plot(deck).strip(), deck.strip())


class TestProfileDeck(unittest.TestCase):
    """Deck com um print.1d por etapa, para a tela de evolução."""

    def setUp(self):
        self.passos = [Step.new(t).as_dict()
                       for t in ("INITIALIZE", "IMPLANTI", "DIFFUSION")]
        self.deck, self.plano = D4.build_profile_deck("Evolução", self.passos)

    def test_um_print_por_etapa_de_processo(self):
        self.assertEqual(self.deck.count("print.1d"), 3)
        self.assertEqual(len(self.plano), 3)

    def test_plano_na_ordem_das_etapas(self):
        self.assertEqual([r for r, _ in self.plano],
                         ["Substrato", "Implante", "Difusão"])

    def test_etapas_print_da_receita_sao_ignoradas(self):
        """O plano já imprime a cada etapa; repetir duplicaria os blocos."""
        passos = self.passos + [Step.new("PRINT").as_dict()]
        deck, plano = D4.build_profile_deck("X", passos)
        self.assertEqual(len(plano), 3)
        self.assertEqual(deck.count("print.1d"), 3)


if __name__ == "__main__":
    unittest.main()
