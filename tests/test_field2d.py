"""A seção transversal 2-D, montada a partir de cortes do ``print.1d``.

O SUPREM-IV.GS desta compilação não tem camada gráfica: os ``gpsup/gpfake.c``
são talões vazios, e ``plot.2d``/``contour`` não desenham nada. Então a tela
de Resultados 2-D é montada varrendo a seção com N cortes verticais e
extraindo contornos, junção e faixas de material dos números do próprio motor.
Este módulo é essa montagem; os testes de :class:`TestContraOMotor` a
exercitam com uma varredura real.

O campo sintético usado nos testes de forma é um degrau: dopagem n rasa de um
lado, profunda do outro, que é o que um implante autoalinhado produz.
"""

from __future__ import annotations

import unittest

from mos_studio.core import field2d as F

#: Saída de duas colunas do motor, no formato literal do ``print.1d``.
SAIDA = (
    "SUPREM-IV.GS B.9305\n"
    "Reading Models...\n"
    "x coordinate in um\t          doping\tMaterial\n"
    "       -0.02000000\t-1.000000e+15   \toxide           \n"
    "        0.00000000\t 2.000000e+19   \tsilicon         \n"
    "        0.10000000\t 1.000000e+17   \tsilicon         \n"
    "        0.20000000\t-1.000000e+15   \tsilicon         \n"
    "y coordinate in um\t          doping\tMaterial\n"
    "       -0.02000000\t-1.000000e+15   \toxide           \n"
    "        0.00000000\t 5.000000e+19   \tsilicon         \n"
    "        0.30000000\t 1.000000e+17   \tsilicon         \n"
    "        0.40000000\t-1.000000e+15   \tsilicon         \n"
    "layer  material        thickness  Integrated\n"
    "num    type            microns    doping\n"
    " 0     oxide           -0.020     0.000000e+00    \n"
    " 1     oxide           0.000      1.000000e+12    \n"
    " 2     silicon         2.000      3.000000e+15    \n"
)


def degrau(n: int = 12, raso: float = 0.1, fundo: float = 0.3) -> F.Field2D:
    """Campo sintético: junção rasa até a metade, profunda depois."""
    cols = []
    for i in range(n):
        x = i / (n - 1)
        xj = raso if x < 0.5 else fundo
        col = F.Column(x=x)
        # Fundo suficiente para o lado profundo também trocar de sinal: com
        # 0,6 µm a troca do lado fundo cairia exatamente na última linha.
        for k in range(31):
            d = 0.9 * k / 30
            col.depth.append(d)
            # n acima da junção, p abaixo, com uma década por 0,1 µm.
            col.value.append(1e19 * 10 ** (-(d / xj) * 2) - 1e15)
            col.material.append("silicon")
        cols.append(col)
    return F.Field2D(columns=cols)


class TestColuna(unittest.TestCase):
    def setUp(self):
        self.col = F.Column(
            x=0.5, depth=[-0.02, 0.0, 0.1, 0.2],
            value=[-1e15, 2e19, 1e17, -1e15],
            material=["oxide", "silicon", "silicon", "silicon"])

    def test_superficie_e_o_primeiro_no_de_silicio(self):
        self.assertAlmostEqual(self.col.surface(), 0.0)

    def test_coluna_sem_silicio_nao_tem_superficie(self):
        col = F.Column(x=0, depth=[0.0], value=[0.0], material=["oxide"])
        self.assertIsNone(col.surface())

    def test_poli_nao_conta_como_superficie(self):
        """Foi o erro que inventou uma junção sob a porta: o topo do poli
        virava "superfície" e a junção aparecia 0,5 µm acima do silício."""
        self.assertNotIn("poly", F.BULK)
        col = F.Column(x=0, depth=[-0.3, 0.0], value=[1e20, -1e15],
                       material=["poly", "silicon"])
        self.assertAlmostEqual(col.surface(), 0.0)

    def test_valor_interpolado(self):
        self.assertAlmostEqual(self.col.at(0.05), (2e19 + 1e17) / 2)

    def test_valor_no_no(self):
        self.assertAlmostEqual(self.col.at(0.1), 1e17)

    def test_fora_do_corte_satura_nas_pontas(self):
        self.assertAlmostEqual(self.col.at(-1.0), -1e15)
        self.assertAlmostEqual(self.col.at(5.0), -1e15)

    def test_coluna_vazia(self):
        self.assertIsNone(F.Column(x=0).at(0.1))

    def test_nos_repetidos_na_interface(self):
        """O motor duplica o nó na interface; não pode dividir por zero."""
        col = F.Column(x=0, depth=[0.0, 0.0, 0.1], value=[1.0, 2.0, 3.0],
                       material=["oxide", "silicon", "silicon"])
        self.assertIsNotNone(col.at(0.0))


class TestVarredura(unittest.TestCase):
    def test_posicoes_cobrem_as_bordas(self):
        xs = F.scan_positions(0.0, 1.0, 5)
        self.assertEqual(len(xs), 5)
        self.assertAlmostEqual(xs[0], 0.0)
        self.assertAlmostEqual(xs[-1], 1.0)

    def test_posicoes_igualmente_espacadas(self):
        xs = F.scan_positions(0.0, 1.0, 5)
        passos = [b - a for a, b in zip(xs, xs[1:])]
        for p in passos:
            self.assertAlmostEqual(p, passos[0])

    def test_pelo_menos_duas_posicoes(self):
        self.assertEqual(len(F.scan_positions(0.0, 1.0, 1)), 2)

    def test_intervalo_degenerado(self):
        self.assertEqual(F.scan_positions(1.0, 1.0, 5), [1.0, 1.0])

    def test_deck_seleciona_a_variavel_uma_vez(self):
        d = F.build_scan_deck("t", ["mode two.dim"], ["init boron conc=1e15"],
                              [0.1, 0.2, 0.3])
        self.assertEqual(d.count("select z=doping"), 1)

    def test_deck_tem_um_corte_por_posicao(self):
        d = F.build_scan_deck("t", [], [], [0.1, 0.2, 0.3])
        cortes = [l for l in d.splitlines()
                  if l.startswith("print.1d") and "layers" not in l]
        self.assertEqual(len(cortes), 3)

    def test_a_tabela_de_camadas_pede_x_value(self):
        """Sem ``x.value`` o print.1d cai no modo de interface e zera tudo."""
        d = F.build_scan_deck("t", [], [], [0.1, 0.9])
        camadas = next(l for l in d.splitlines() if "layers" in l)
        self.assertIn("x.value=0.9", camadas)

    def test_deck_sem_posicao_nao_pede_camadas(self):
        d = F.build_scan_deck("t", [], [], [])
        self.assertNotIn("layers", d)

    def test_deck_escolhe_a_especie_quimica(self):
        d = F.build_scan_deck("t", [], [], [0.1], z_expr="arsenic")
        self.assertIn("select z=arsenic", d)

    def test_deck_termina_com_quit(self):
        d = F.build_scan_deck("t", [], [], [0.1])
        self.assertEqual(d.strip().splitlines()[-1], "quit")


class TestLeitura(unittest.TestCase):
    def setUp(self):
        self.fld = F.parse_scan(SAIDA, [0.2, 0.8])

    def test_uma_coluna_por_corte(self):
        self.assertEqual(len(self.fld.columns), 2)
        self.assertEqual(self.fld.xs, [0.2, 0.8])

    def test_le_corte_vertical_rotulado_y(self):
        """Os cortes verticais saem como "y coordinate in um"."""
        self.assertEqual(len(self.fld.columns[1].depth), 4)

    def test_pareamento_e_posicional(self):
        self.assertAlmostEqual(self.fld.columns[1].value[1], 5e19)

    def test_le_o_material_de_cada_no(self):
        self.assertEqual(self.fld.columns[0].material[0], "oxide")
        self.assertEqual(self.fld.columns[0].material[1], "silicon")

    def test_le_a_pilha_de_camadas(self):
        self.assertEqual(len(self.fld.stack), 2)

    def test_menos_blocos_que_cortes_nao_desalinha(self):
        """Um corte fora da malha não produz bloco; as sobras são descartadas."""
        fld = F.parse_scan(SAIDA, [0.2, 0.8, 1.4])
        self.assertEqual(len(fld.columns), 2)
        self.assertEqual(fld.xs, [0.2, 0.8])

    def test_saida_sem_tabela(self):
        fld = F.parse_scan("Reading Models...\n", [0.1, 0.2])
        self.assertFalse(fld.ok)

    def test_uma_coluna_so_nao_e_campo(self):
        fld = F.parse_scan(SAIDA, [0.2])
        self.assertFalse(fld.ok)

    def test_extensao_dos_dados(self):
        x0, x1, y0, y1 = self.fld.extent()
        self.assertAlmostEqual(x0, 0.2)
        self.assertAlmostEqual(x1, 0.8)
        self.assertAlmostEqual(y0, -0.02)
        self.assertAlmostEqual(y1, 0.4)

    def test_faixa_de_valores_ignora_o_zero(self):
        lo, hi = self.fld.value_range()
        self.assertGreater(lo, 0)
        self.assertAlmostEqual(hi, 5e19)

    def test_campo_vazio_tem_extensao_segura(self):
        """A tela divide pela extensão; zero quebraria o desenho."""
        x0, x1, y0, y1 = F.Field2D().extent()
        self.assertGreater(x1, x0)
        self.assertGreater(y1, y0)
        self.assertEqual(F.Field2D().value_range(), (1.0, 1.0))


class TestContorno(unittest.TestCase):
    def setUp(self):
        self.fld = degrau()

    def test_gera_linha_para_nivel_dentro_da_faixa(self):
        self.assertTrue(F.contour(self.fld, 1e18))

    def test_nivel_fora_da_faixa_nao_gera_linha(self):
        self.assertEqual(F.contour(self.fld, 1e30), [])

    def test_nivel_invalido(self):
        self.assertEqual(F.contour(self.fld, 0.0), [])
        self.assertEqual(F.contour(self.fld, -1e18), [])

    def test_campo_vazio(self):
        self.assertEqual(F.contour(F.Field2D(), 1e18), [])

    def test_os_pontos_ficam_dentro_da_extensao(self):
        x0, x1, y0, y1 = self.fld.extent()
        for linha in F.contour(self.fld, 1e18):
            for x, y in linha:
                self.assertGreaterEqual(x, x0 - 1e-9)
                self.assertLessEqual(x, x1 + 1e-9)
                self.assertGreaterEqual(y, y0 - 1e-9)
                self.assertLessEqual(y, y1 + 1e-9)

    def test_o_contorno_acompanha_o_degrau(self):
        """O lado fundo tem a mesma concentração mais fundo que o lado raso."""
        pontos = [p for linha in F.contour(self.fld, 1e18) for p in linha]
        esq = [y for x, y in pontos if x < 0.4]
        dir_ = [y for x, y in pontos if x > 0.6]
        self.assertTrue(esq and dir_)
        self.assertLess(sum(esq) / len(esq), sum(dir_) / len(dir_))

    def test_nivel_mais_alto_fica_mais_raso(self):
        media = lambda n: (lambda ps: sum(y for _, y in ps) / len(ps))(
            [p for l in F.contour(self.fld, n) for p in l])
        self.assertLess(media(1e18), media(1e16))

    def test_escala_linear_tambem_funciona(self):
        self.assertTrue(F.contour(self.fld, 1e18, logarithmic=False))


class TestJuncao(unittest.TestCase):
    def setUp(self):
        self.fld = degrau()

    def test_a_juncao_existe_onde_o_sinal_troca(self):
        self.assertTrue(F.junction(self.fld))

    def test_campo_sem_troca_de_sinal_nao_tem_juncao(self):
        col = F.Column(x=0, depth=[0.0, 0.1], value=[1e19, 1e18],
                       material=["silicon", "silicon"])
        outra = F.Column(x=1, depth=[0.0, 0.1], value=[1e19, 1e18],
                         material=["silicon", "silicon"])
        self.assertEqual(F.junction(F.Field2D(columns=[col, outra])), [])

    def test_campo_vazio(self):
        self.assertEqual(F.junction(F.Field2D()), [])

    def test_profundidade_por_posicao_segue_o_degrau(self):
        raso = F.junction_depth_at(self.fld, 0.1)
        fundo = F.junction_depth_at(self.fld, 0.9)
        self.assertIsNotNone(raso)
        self.assertIsNotNone(fundo)
        self.assertLess(raso, fundo)

    def test_medida_a_partir_da_superficie_do_silicio(self):
        """Com óxido em cima, a junção não conta a espessura do óxido."""
        col = F.Column(x=0.0, depth=[-0.1, 0.0, 0.1, 0.2],
                       value=[1e19, 1e19, 1e18, -1e15],
                       material=["oxide", "silicon", "silicon", "silicon"])
        fld = F.Field2D(columns=[col, col])
        xj = F.junction_depth_at(fld, 0.0)
        self.assertGreater(xj, 0.1)
        self.assertLess(xj, 0.2)

    def test_no_exatamente_em_zero_e_a_juncao(self):
        """Dopagem líquida nula é a junção.

        Com o teste estrito de troca de sinal, um nó em zero fazia a junção
        inteira desaparecer: o produto com o vizinho de cada lado dá zero, e
        nenhum dos dois pares era contado como cruzamento.
        """
        col = F.Column(x=0.0, depth=[0.0, 0.1, 0.2],
                       value=[1e19, 0.0, -1e15],
                       material=["silicon"] * 3)
        fld = F.Field2D(columns=[col, col])
        self.assertAlmostEqual(F.junction_depth_at(fld, 0.0), 0.1)
        self.assertTrue(F.junction(fld))

    def test_coluna_sem_silicio_nao_tem_profundidade(self):
        col = F.Column(x=0, depth=[0.0, 0.1], value=[1e19, -1e15],
                       material=["oxide", "oxide"])
        self.assertIsNone(F.junction_depth_at(F.Field2D(columns=[col, col]),
                                              0.0))

    def test_campo_vazio_nao_tem_profundidade(self):
        self.assertIsNone(F.junction_depth_at(F.Field2D(), 0.5))


class TestRecorteDeProfundidade(unittest.TestCase):
    """O desenho para logo abaixo do que interessa.

    Com os dois micra inteiros do substrato, o dispositivo — porta, extensão,
    fonte e dreno — ficaria espremido numa faixa de poucos pixels no topo.
    """

    def test_com_juncao_o_corte_fica_logo_abaixo_dela(self):
        """Junção rasa num substrato fundo: é o caso real do LDD."""
        from mos_studio.ui.widgets.cross_section import CrossSection
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        cols = []
        for i in range(8):
            c = F.Column(x=i / 7)
            for k in range(61):
                d = 2.0 * k / 60                      # dois micra de malha
                c.depth.append(d)
                c.value.append(1e20 * 10 ** (-d / 0.05) - 1e15)
                c.material.append("silicon")
            cols.append(c)
        v = CrossSection()
        v.set_field(F.Field2D(columns=cols))
        self.assertLess(v.visible_depth(), 1.0)       # não mostra os 2 µm
        self.assertGreater(v.visible_depth(), 0.25)   # mas cobre a junção

    def test_sem_juncao_usa_o_decaimento_do_perfil(self):
        """Um perfil químico não troca de sinal; o corte vem do decaimento."""
        from mos_studio.ui.widgets.cross_section import CrossSection
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        cols = []
        for i in range(6):
            c = F.Column(x=i / 5)
            for k in range(41):
                d = 2.0 * k / 40
                c.depth.append(d)
                c.value.append(1e20 * 10 ** (-d / 0.05))   # cai rápido
                c.material.append("silicon")
            cols.append(c)
        v = CrossSection()
        v.set_field(F.Field2D(columns=cols, z_expr="arsenic"))
        self.assertLess(v.visible_depth(), 2.0)

    def test_o_limite_manual_manda(self):
        from mos_studio.ui.widgets.cross_section import CrossSection
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        v = CrossSection()
        v.set_field(degrau())
        v.set_depth_limit(0.2)
        self.assertAlmostEqual(v.visible_depth(), 0.2)
        v.set_depth_limit(0.0)
        self.assertNotAlmostEqual(v.visible_depth(), 0.2)


class TestCostura(unittest.TestCase):
    def test_une_segmentos_encadeados(self):
        segs = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (2.0, 0.0))]
        linhas = F._chain(segs)
        self.assertEqual(len(linhas), 1)
        self.assertEqual(len(linhas[0]), 3)

    def test_segmentos_separados_ficam_separados(self):
        segs = [((0.0, 0.0), (1.0, 0.0)), ((5.0, 5.0), (6.0, 5.0))]
        self.assertEqual(len(F._chain(segs)), 2)

    def test_costura_pelas_duas_pontas(self):
        segs = [((1.0, 0.0), (2.0, 0.0)), ((0.0, 0.0), (1.0, 0.0))]
        self.assertEqual(len(F._chain(segs)), 1)

    def test_sem_segmento(self):
        self.assertEqual(F._chain([]), [])


class TestGeometria(unittest.TestCase):
    def setUp(self):
        self.fld = F.parse_scan(SAIDA, [0.2, 0.8])

    def test_faixas_por_material(self):
        faixas = F.material_bands(self.fld)
        self.assertIn("oxide", faixas)
        self.assertIn("silicon", faixas)

    def test_cada_faixa_tem_posicao_topo_e_base(self):
        for lista in F.material_bands(self.fld).values():
            for x, topo, base in lista:
                self.assertGreaterEqual(base, topo)

    def test_a_faixa_de_oxido_fica_acima_do_silicio(self):
        faixas = F.material_bands(self.fld)
        self.assertLess(faixas["oxide"][0][1], faixas["silicon"][0][1])

    def test_campo_vazio_nao_tem_faixa(self):
        self.assertEqual(F.material_bands(F.Field2D()), {})

    def test_perfil_da_superficie(self):
        pts = F.surface_line(self.fld)
        self.assertEqual(len(pts), 2)
        for x, y in pts:
            self.assertAlmostEqual(y, 0.0)

    def test_coluna_mais_proxima(self):
        self.assertAlmostEqual(F.column_at(self.fld, 0.7).x, 0.8)
        self.assertAlmostEqual(F.column_at(self.fld, 0.0).x, 0.2)

    def test_coluna_de_campo_vazio(self):
        self.assertIsNone(F.column_at(F.Field2D(), 0.5))


class TestContraOMotor(unittest.TestCase):
    """Uma varredura real de um transistor LDD."""

    @classmethod
    def setUpClass(cls):
        from mos_studio.core import mesh as M, suprem4

        if suprem4.find_run_dir() is None:
            raise unittest.SkipTest("SUPREM-IV não está instalado")
        from tests.test_recipe4 import ldd
        from mos_studio.core import recipe4 as R

        malha = M.to_cards(M.default_mesh())
        passos = [c for s in ldd() for c in R.step_to_cards(s)]
        cls.xs = F.scan_positions(0.0, 1.0, 16)
        deck = F.build_scan_deck("ldd", malha, passos, cls.xs)
        cls.fld = F.parse_scan(suprem4.run_sync(deck, timeout=300), cls.xs)

    def test_a_varredura_traz_todas_as_colunas(self):
        self.assertEqual(len(self.fld.columns), len(self.xs))
        self.assertTrue(self.fld.ok)

    def test_cada_coluna_atravessa_silicio(self):
        for c in self.fld.columns:
            self.assertIn("silicon", c.material, c.x)

    def test_o_motor_construiu_o_poli_so_de_um_lado(self):
        """A corrosão ``right`` deixa a porta à esquerda de x = 0,35 µm."""
        tem_poli = {c.x: ("poly" in c.material) for c in self.fld.columns}
        self.assertTrue(tem_poli[min(tem_poli)])
        self.assertFalse(tem_poli[max(tem_poli)])

    def test_nao_ha_juncao_sob_a_porta(self):
        """Foi o que denunciou o ``poly`` indevido em :data:`field2d.BULK`."""
        self.assertIsNone(F.junction_depth_at(self.fld, 0.0))

    def test_a_juncao_e_mais_profunda_na_fonte_dreno(self):
        extensao = F.junction_depth_at(self.fld, 0.4)
        fonte = F.junction_depth_at(self.fld, 0.93)
        self.assertIsNotNone(extensao)
        self.assertIsNotNone(fonte)
        self.assertLess(extensao, fonte)

    def test_a_superficie_do_silicio_e_quase_plana(self):
        ys = [y for _, y in F.surface_line(self.fld)]
        self.assertTrue(ys)
        self.assertLess(max(ys) - min(ys), 0.1)

    def test_o_contorno_sai_com_dados_reais(self):
        lo, hi = self.fld.value_range()
        nivel = (lo * hi) ** 0.5
        self.assertTrue(F.contour(self.fld, nivel))

    def test_as_faixas_trazem_os_materiais_do_processo(self):
        faixas = F.material_bands(self.fld)
        for m in ("silicon", "oxide", "poly"):
            self.assertIn(m, faixas, m)


if __name__ == "__main__":
    unittest.main()
