"""Os parsers leem a saída real dos motores e não mudaram de comportamento."""

from __future__ import annotations

import unittest
from pathlib import Path

from mos_studio.core import parsers

from . import legacy

RAIZ = Path(__file__).resolve().parent.parent

PERFIL = """\x0cNet Chemical

     depth   concentration
     0.0000    9.00000E+17
     0.0500    6.00000E+17
     0.1000    2.00000E+17
     0.1500    1.00000E+16
     0.2000   -5.00000E+15
     0.2500   -9.00000E+15
     0.3000   -1.00000E+16
"""

CAMADAS = """
 layer    material type      thickness   dx    dxmin top  bottom  orientation
  no.                        (microns)   (microns)   node  node  or grain size
   2    OXIDE                   0.0760 0.0100 0.0010  418   425
   1    SILICON                 0.3666 0.0050 0.0010  426   500      <100>
"""

IV = """\
##  UB (V)  UD (V)  UG (V)  US (V)  IB (A)  ID (A)  IG (A)  IS (A)
 0.0  0.100  2.000  0.0  1.0E-14  1.14E-04  0.0  -1.14E-04
 0.0  0.600  2.000  0.0  1.2E-14  5.90E-04  0.0  -5.90E-04
"""


class TestPerfil(unittest.TestCase):
    def test_le_pares_profundidade_concentracao(self):
        pts = parsers.parse_out_file(PERFIL)
        self.assertEqual(len(pts), 7)
        self.assertAlmostEqual(pts[0][0], 0.0)
        self.assertAlmostEqual(pts[0][1], 9.0e17)
        self.assertAlmostEqual(pts[-1][1], -1.0e16)

    def test_ordena_por_profundidade(self):
        pts = parsers.parse_out_file(PERFIL)
        self.assertEqual(pts, sorted(pts, key=lambda p: p[0]))

    def test_texto_sem_tabela_devolve_vazio(self):
        self.assertEqual(parsers.parse_out_file("nada aqui\n"), [])

    def test_blocos_em_ordem(self):
        blocos = parsers.parse_suprem_profiles(PERFIL + PERFIL)
        self.assertEqual(len(blocos), 2)
        self.assertEqual(len(blocos[0][0]), 7)


class TestJuncoes(unittest.TestCase):
    def test_encontra_a_troca_de_tipo(self):
        pts = parsers.parse_out_file(PERFIL)
        juncoes = parsers.detect_junctions(pts, min_mag=1e15)
        self.assertEqual(len(juncoes), 1)
        self.assertTrue(0.15 < juncoes[0] < 0.20)

    def test_limiar_derivado_do_substrato(self):
        pts = parsers.parse_out_file(PERFIL)
        limiar = parsers.junction_threshold(pts)
        self.assertAlmostEqual(limiar, 1e15)       # 10% de 1e16
        self.assertTrue(parsers.detect_junctions(pts, min_mag=limiar))

    def test_limiar_tem_piso_e_teto(self):
        self.assertEqual(parsers.junction_threshold([(0.0, 1e10)]), 1e13)
        self.assertEqual(parsers.junction_threshold([(0.0, 1e21)]), 1e16)
        self.assertEqual(parsers.junction_threshold([]), 1e16)

    def test_perfil_de_um_tipo_so_nao_tem_juncao(self):
        pts = [(i * 0.01, 1e17) for i in range(50)]
        self.assertEqual(parsers.detect_junctions(pts), [])


class TestCamadasEOxido(unittest.TestCase):
    def test_le_a_pilha_de_materiais(self):
        self.assertEqual(parsers.parse_layers(CAMADAS),
                         [("OXIDE", 0.076), ("SILICON", 0.3666)])

    def test_le_a_espessura_do_oxido(self):
        self.assertAlmostEqual(parsers.parse_oxide_thickness(CAMADAS), 0.076)

    def test_sem_oxido_devolve_none(self):
        self.assertIsNone(parsers.parse_oxide_thickness("   1  SILICON  0.5\n"))


class TestMinimos(unittest.TestCase):
    def test_le_curva_iv(self):
        headers, rows = parsers.parse_minimos_iv(IV)
        self.assertEqual(headers[:4], ["UB", "UD", "UG", "US"])
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[1][1], 0.6)

    def test_iv_vazio(self):
        self.assertEqual(parsers.parse_minimos_iv(""), ([], []))

    def test_pif_vazio(self):
        self.assertEqual(parsers.parse_minimos_pif(""), ([], [], {}))


@unittest.skipUnless(legacy.available(), "suprem3.py não está no repositório")
class TestParidadeComOLegado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = legacy.namespace()
        cls.arquivos = sorted(RAIZ.glob("suprem-run/examples/**/*.out"))

    def test_mesma_leitura_das_saidas_reais(self):
        self.assertTrue(self.arquivos, "nenhuma saída de exemplo encontrada")
        for f in self.arquivos:
            raw = f.read_text(encoding="latin1", errors="replace")
            with self.subTest(arquivo=f.name):
                self.assertEqual(self.ns["parse_out_file"](raw),
                                 parsers.parse_out_file(raw))
                self.assertEqual(self.ns["parse_suprem_profiles"](raw),
                                 parsers.parse_suprem_profiles(raw))
                self.assertEqual(self.ns["parse_oxide_thickness"](raw),
                                 parsers.parse_oxide_thickness(raw))

    def test_mesma_deteccao_de_juncao_com_o_padrao_antigo(self):
        for f in self.arquivos:
            raw = f.read_text(encoding="latin1", errors="replace")
            pts = parsers.parse_out_file(raw)
            if not pts:
                continue
            with self.subTest(arquivo=f.name):
                self.assertEqual(self.ns["_detect_junctions"](pts),
                                 parsers.detect_junctions(pts))


class TestPerfilComOxidoNoTopo(unittest.TestCase):
    """Um perfil impresso com óxido ainda sobre a lâmina.

    No óxido a dopagem ativa é zero, e a tabela começa com linhas de
    ``0.00000E+00``. O leitor encerrava a tabela na primeira delas, porque o
    ``E`` do expoente contava como letra — ou seja, todo deck que imprime o
    perfil antes de corroer o óxido perdia o perfil inteiro. Recorte literal
    da saída do SUPREM-III.
    """

    AMOSTRA = (
        "\nNet Active\n\n"
        "     depth   concentration\n"
        "     0.0000    0.00000E+00\n"
        "     0.0108    0.00000E+00\n"
        "     0.0280    0.00000E+00\n"
        "     0.0280   -2.20694E+16\n"
        "     0.0320   -2.24628E+16\n"
        "     0.1220   -2.66158E+16\n"
        "     1.2120   -1.00000E+15\n"
    )

    def test_le_o_perfil_inteiro(self):
        pts = parsers.parse_out_file(self.AMOSTRA)
        self.assertEqual(len(pts), 4)

    def test_comeca_na_superficie_do_silicio(self):
        """Os pontos de concentração nula no óxido não viram perfil."""
        pts = parsers.parse_out_file(self.AMOSTRA)
        self.assertAlmostEqual(pts[0][0], 0.028)
        self.assertAlmostEqual(pts[0][1], -2.20694e16)

    def test_preserva_o_pico_do_canal(self):
        pts = dict(parsers.parse_out_file(self.AMOSTRA))
        self.assertAlmostEqual(pts[0.122], -2.66158e16)

    def test_texto_de_verdade_ainda_encerra_a_tabela(self):
        texto = self.AMOSTRA + " Better luck next time.\n     9.9999   -1.0E+99\n"
        self.assertEqual(len(parsers.parse_out_file(texto)), 4)


class TestCamadasNaoLeemOEcoDoDeck(unittest.TestCase):
    """O log do motor ecoa o deck, e o eco parecia uma camada.

    ``DEPOSITION POLYSILI THICKNES=0.35`` entrava como camada de 0,35 µm de
    polissilício; como o ``OUTPUT.OUT`` vem antes do arquivo de camadas na
    ordem alfabética, era esse eco que a tela mostrava.
    """

    TABELA = (
        " layer    material type      thickness   dx    dxmin top  bottom\n"
        "  no.                        (microns)   (microns)   node  node\n"
        "   3    POLYSILICON             0.3500 0.0100 0.0010  222   257\n"
        "   2    OXIDE                   0.0280 0.0100 0.0010  258   262\n"
        "   1    SILICON                 1.1840 0.0050 0.0010  263   500\n"
        "\n                        Integrated Dopant\n"
        "   3     2.5314E+15   2.9036E+15\n"
    )

    ECO = (
        "   7... DEPOSITION POLYSILI THICKNES=0.35 PHOSPHOR CONCENTR=1E20\n"
        "   8... DIFFUSION NITROGEN TEMPERAT=900 TIME=30\n"
    )

    def test_le_a_pilha_inteira(self):
        self.assertEqual(parsers.parse_layers(self.TABELA),
                         [("POLYSILICON", 0.35), ("OXIDE", 0.028),
                          ("SILICON", 1.184)])

    def test_o_cabecalho_de_duas_linhas_nao_encerra_a_tabela(self):
        self.assertEqual(len(parsers.parse_layers(self.TABELA)), 3)

    def test_o_eco_do_deck_nao_e_camada(self):
        self.assertEqual(parsers.parse_layers(self.ECO), [])

    def test_a_tabela_termina_depois_das_camadas(self):
        """A seção de dopagem integrada não acrescenta camadas."""
        self.assertEqual(len(parsers.parse_layers(self.TABELA + self.ECO)), 3)


if __name__ == "__main__":
    unittest.main()
