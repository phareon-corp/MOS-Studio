"""Leitura da saída do ``print.1d`` do SUPREM-IV.GS.

As amostras aqui são recortes literais da saída do motor compilado, com as
tabulações preservadas — é por causa delas que o parser existe em vez de um
``split()``.
"""

from __future__ import annotations

import unittest

from mos_studio.core import parsers as P

#: Perfil com camada depositada (coordenada negativa) e substrato.
PERFIL = (
    "SUPREM-IV.GS B.9305\n"
    "\t(c) 1991-1993 Stanford University\n"
    "Reading Models...\n"
    "Solving            0 +          0.1 =          0.1,      100%, np 43\n"
    "x coordinate in um\t          doping\tMaterial\n"
    "       -0.07500000\t-2.452499e+15   \toxide           \n"
    "        0.00000000\t-1.142918e+19   \toxide           \n"
    "        0.00000000\t-5.861329e+18   \tsilicon         \n"
    "        0.02000000\t-5.823987e+18   \tsilicon         \n"
    "        0.50000000\t-1.000589e+15   \tsilicon         \n"
)

#: Tabela de camadas, com a espessura negativa que o motor usa para o que
#: está acima da superfície original.
CAMADAS = (
    "layer  material        thickness  Integrated\n"
    "num    type            microns    doping\n"
    " 0     oxide           -0.075     0.000000e+00    \n"
    " 1     oxide           0.003      1.291786e-04    \n"
    " 2     silicon         2.000      3.264734e-03    \n"
    "invoked interactively\n"
)

#: Dois print.1d na mesma execução.
DOIS = (
    "x coordinate in um\t          doping\tMaterial\n"
    "        0.00000000\t-1.000000e+15   \tsilicon         \n"
    "        0.10000000\t-1.000000e+15   \tsilicon         \n"
    "Solving            0 +          0.1 =          0.1,      100%, np 43\n"
    "x coordinate in um\t          doping\tMaterial\n"
    "        0.00000000\t-2.000000e+18   \tsilicon         \n"
    "        0.10000000\t-5.000000e+17   \tsilicon         \n"
    "        0.20000000\t-1.000000e+15   \tsilicon         \n"
)


class TestBlocos(unittest.TestCase):
    def test_le_um_bloco(self):
        blocos = P.parse_print_1d(PERFIL)
        self.assertEqual(len(blocos), 1)
        self.assertEqual(len(blocos[0]), 5)

    def test_preserva_coordenada_negativa(self):
        """A origem fica na superfície do substrato: o que está acima é < 0."""
        self.assertAlmostEqual(P.parse_print_1d(PERFIL)[0][0][0], -0.075)

    def test_le_o_material_de_cada_ponto(self):
        materiais = [m for _, _, m in P.parse_print_1d(PERFIL)[0]]
        self.assertEqual(materiais, ["oxide", "oxide", "silicon", "silicon",
                                     "silicon"])

    def test_ignora_as_linhas_do_solver(self):
        for _, valor, _ in P.parse_print_1d(PERFIL)[0]:
            self.assertLess(valor, 0)        # nenhum "100%" virou dado

    def test_separa_blocos_consecutivos(self):
        blocos = P.parse_print_1d(DOIS)
        self.assertEqual(len(blocos), 2)
        self.assertEqual([len(b) for b in blocos], [2, 3])

    def test_entrada_vazia_ou_sem_tabela(self):
        self.assertEqual(P.parse_print_1d(""), [])
        self.assertEqual(P.parse_print_1d("Reading Models...\n"), [])
        self.assertEqual(P.parse_print_1d(CAMADAS), [])


class TestPerfil(unittest.TestCase):
    def test_recorta_no_silicio_e_reancora_em_zero(self):
        perfil = P.parse_print_1d_profile(PERFIL)
        self.assertEqual(len(perfil), 3)
        self.assertAlmostEqual(perfil[0][0], 0.0)
        self.assertAlmostEqual(perfil[-1][0], 0.5)

    def test_material_vazio_devolve_a_pilha_inteira(self):
        perfil = P.parse_print_1d_profile(PERFIL, material="")
        self.assertEqual(len(perfil), 5)
        self.assertAlmostEqual(perfil[0][0], -0.075)

    def test_usa_o_ultimo_bloco(self):
        """Num deck com vários print.1d, o estado final é o que interessa."""
        perfil = P.parse_print_1d_profile(DOIS)
        self.assertEqual(len(perfil), 3)
        self.assertAlmostEqual(perfil[0][1], -2e18)

    def test_ordenado_por_profundidade(self):
        profundidades = [d for d, _ in P.parse_print_1d_profile(PERFIL)]
        self.assertEqual(profundidades, sorted(profundidades))

    def test_material_ausente_devolve_vazio(self):
        self.assertEqual(P.parse_print_1d_profile(PERFIL, material="nitride"), [])

    def test_preserva_o_sinal_do_doping(self):
        """Negativo é tipo p: trocar o sinal inverteria o tipo do substrato."""
        self.assertTrue(all(c < 0 for _, c in P.parse_print_1d_profile(PERFIL)))


#: Corte vertical de um transistor LDD em x = 0,8 µm, saída real do motor.
#: O silício aparece em duas linhas porque o motor quebra a camada na junção
#: e troca o sinal da dopagem integrada entre as duas partes.
LDD = (
    "layer  material        thickness  Integrated\n"
    "num    type            microns    doping\n"
    " 0     oxide           0.000      0.000000e+00    \n"
    " 1     oxide           0.000      1.167658e+13    \n"
    " 2     oxide           0.016      5.644136e+11    \n"
    " 3     silicon         0.273      2.609546e+15    \n"
    " 4     silicon         2.000      -1.721565e+11   \n"
)


class TestCamadas(unittest.TestCase):
    """A coluna "thickness" do motor é posição de interface, não espessura.

    Conferido contra o motor: 0,075 µm de óxido depositado mais 15 min de O₂
    seco a 1000 °C num substrato de 0,5 µm dão as linhas −0,079 / 0,003 /
    0,500. Logo o óxido tem 0,082 µm (0,075 depositados mais 0,007 crescidos,
    dos quais 0,003 consumiram silício) e o silício 0,497 µm — e não 0,079 /
    0,003 / 0,500 como a leitura literal da coluna sugeriria.
    """

    def test_linhas_cruas_sao_posicoes(self):
        linhas = P.parse_print_1d_rows(CAMADAS)
        self.assertEqual([m for m, _, _ in linhas],
                         ["oxide", "oxide", "silicon"])
        self.assertAlmostEqual(linhas[0][1], -0.075)
        self.assertAlmostEqual(linhas[2][1], 2.0)

    def test_espessura_e_a_diferenca_entre_interfaces(self):
        self.assertEqual(P.parse_print_1d_layers(CAMADAS),
                         [("oxide", 0.078), ("silicon", 1.997)])

    def test_pilha_traz_topo_e_base(self):
        pilha = P.parse_print_1d_stack(CAMADAS)
        self.assertAlmostEqual(pilha[0].top, -0.075)
        self.assertAlmostEqual(pilha[0].bottom, 0.003)
        self.assertAlmostEqual(pilha[0].thickness, 0.078)
        self.assertAlmostEqual(pilha[1].top, 0.003)

    def test_primeira_linha_e_o_topo_nao_uma_camada(self):
        """Três linhas descrevem duas camadas, não três."""
        self.assertEqual(len(P.parse_print_1d_stack(CAMADAS)), 2)

    def test_descarta_camada_de_espessura_zero(self):
        """Uma deposição corroída naquele corte deixa linhas repetidas."""
        materiais = [m for m, _ in P.parse_print_1d_layers(LDD)]
        self.assertEqual(materiais, ["oxide", "silicon", "silicon"])

    def test_ldd_separa_regiao_dopada_do_substrato(self):
        camadas = P.parse_print_1d_layers(LDD)
        self.assertAlmostEqual(dict(enumerate(camadas))[0][1], 0.016)
        self.assertAlmostEqual(camadas[1][1], 0.257)
        self.assertAlmostEqual(camadas[2][1], 1.727)

    def test_dopagem_integrada_tem_sinal(self):
        pilha = P.parse_print_1d_stack(LDD)
        self.assertGreater(pilha[1].integrated, 0)      # região n
        self.assertLess(pilha[2].integrated, 0)         # substrato p

    def test_ignora_o_cabecalho_de_duas_linhas(self):
        for material, _ in P.parse_print_1d_layers(CAMADAS):
            self.assertIn(material, P.S4_MATERIALS)

    def test_sem_tabela_devolve_vazio(self):
        self.assertEqual(P.parse_print_1d_layers(PERFIL), [])
        self.assertEqual(P.parse_print_1d_layers(""), [])
        self.assertEqual(P.parse_print_1d_stack(""), [])


class TestJuncao(unittest.TestCase):
    """A junção sai da tabela de camadas, sem precisar varrer o perfil."""

    def test_le_a_profundidade_de_juncao(self):
        """Medida da superfície do silício, não do topo da pilha."""
        self.assertAlmostEqual(P.parse_print_1d_junction(LDD), 0.257)

    def test_sem_juncao_devolve_none(self):
        self.assertIsNone(P.parse_print_1d_junction(CAMADAS))

    def test_entrada_vazia(self):
        self.assertIsNone(P.parse_print_1d_junction(""))


class TestOxido(unittest.TestCase):
    def test_soma_as_camadas_de_oxido(self):
        """Oxidar sobre óxido depositado dá duas camadas; vale o total."""
        self.assertAlmostEqual(P.parse_print_1d_oxide(CAMADAS), 0.078, places=6)

    def test_sem_oxido_devolve_none(self):
        texto = ("layer  material        thickness  Integrated\n"
                 "num    type            microns    doping\n"
                 " 0     silicon         2.000      1.0e-03    \n")
        self.assertIsNone(P.parse_print_1d_oxide(texto))

    def test_sem_tabela_devolve_none(self):
        self.assertIsNone(P.parse_print_1d_oxide(PERFIL))


class TestNaoColideComOSuprem3(unittest.TestCase):
    """Os parsers dos dois motores convivem no mesmo módulo."""

    def test_parser_do_suprem3_nao_le_saida_do_suprem4(self):
        self.assertEqual(P.parse_out_file(PERFIL), [])

    def test_parser_do_suprem4_nao_le_saida_do_suprem3(self):
        s3 = ("   depth      concentration\n"
              "  0.0000     1.000E+15\n"
              "  0.0100     2.000E+15\n")
        self.assertEqual(P.parse_print_1d(s3), [])


if __name__ == "__main__":
    unittest.main()
