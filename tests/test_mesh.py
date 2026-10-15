"""A malha do SUPREM-IV.

O teste decisivo aqui é :class:`TestContraOMotor`: as posições esperadas são
as que o próprio motor imprimiu com ``initialize line.data`` para a malha
padrão, copiadas da saída. É o que separa uma pré-visualização honesta de um
desenho bonito — a interpolação linear do espaçamento, que parece a escolha
óbvia, erra a contagem de nós em cerca de 10%.
"""

from __future__ import annotations

import unittest

from mos_studio.core import mesh as M

#: Posições que o motor criou no eixo x da malha padrão, da saída de
#: ``initialize line.data``. Note que não são uniformes entre as linhas
#: pedidas (0 / 0,35 / 0,6 / 1,0): o passo cresce por razão geométrica.
X_MOTOR = [0.000000, 0.098010, 0.175046, 0.235596, 0.283189, 0.320597,
           0.350000, 0.381789, 0.416997, 0.455993, 0.499183, 0.547019,
           0.600000, 0.654906, 0.720200, 0.797848, 0.890189, 1.000000]

#: Os primeiros nós do eixo y (profundidade), da mesma saída.
Y_MOTOR_INICIO = [0.000000, 0.020262, 0.041895, 0.064990, 0.089648, 0.115974,
                  0.144080, 0.174088, 0.206125, 0.240329, 0.276847, 0.315834,
                  0.357459, 0.401899]

#: O motor imprime seis casas decimais, e é só isso que separa as duas contas.
TOLERANCIA = 1e-6


class TestValidacao(unittest.TestCase):
    def test_eixo_precisa_de_duas_linhas(self):
        self.assertTrue(M.validate_axis([]))
        self.assertTrue(M.validate_axis([M.Line(0.0, 0.1)]))
        self.assertEqual(M.validate_axis([M.Line(0.0, 0.1), M.Line(1.0, 0.1)]),
                         "")

    def test_espacamento_precisa_ser_positivo(self):
        erro = M.validate_axis([M.Line(0.0, 0.0), M.Line(1.0, 0.1)])
        self.assertIn("maior que zero", erro)

    def test_espacamento_abaixo_do_minimo(self):
        erro = M.validate_axis([M.Line(0.0, 1e-5), M.Line(1.0, 0.1)])
        self.assertIn("mínimo", erro)

    def test_posicoes_precisam_crescer(self):
        erro = M.validate_axis([M.Line(1.0, 0.1), M.Line(0.5, 0.1)])
        self.assertIn("maior que a da", erro)

    def test_posicoes_repetidas_tambem_sao_erro(self):
        self.assertTrue(M.validate_axis([M.Line(0.5, 0.1), M.Line(0.5, 0.1)]))

    def test_a_mensagem_diz_qual_linha(self):
        erro = M.validate_axis([M.Line(0.0, 0.1), M.Line(1.0, 0.1),
                                M.Line(0.5, 0.1)])
        self.assertIn("Linha 3", erro)

    def test_eixo_invalido_nao_gera_posicoes(self):
        self.assertEqual(M.positions([M.Line(0.0, 0.1)]), [])


class TestDivisao(unittest.TestCase):
    """:func:`mesh.divide` é a transcrição de ``dvpram()``."""

    def test_espacamento_igual_divide_uniforme(self):
        n, razao, primeiro = M.divide(0.1, 0.1, 1.0)
        self.assertEqual(razao, 1.0)
        self.assertAlmostEqual(primeiro * (n + 1), 1.0)

    def test_espacamento_igual_arredonda_para_baixo_no_empate(self):
        """O ``-0.49999`` do original: 1,0/0,1 dá 9 nós interiores, não 10."""
        n, _, _ = M.divide(0.1, 0.1, 1.0)
        self.assertEqual(n, 9)

    def test_passo_cresce_por_razao_geometrica(self):
        n, razao, _ = M.divide(0.02, 0.4, 2.0)
        self.assertGreater(razao, 1.0)
        self.assertGreater(n, 0)

    def test_razao_nunca_passa_do_limite(self):
        """``interval.r`` = 1,5 é o teto entre passos vizinhos."""
        for hl, hr, el in [(0.001, 0.5, 1.0), (0.5, 0.001, 1.0),
                           (0.002, 0.4, 2.0), (0.01, 0.3, 0.5)]:
            _, razao, _ = M.divide(hl, hr, el)
            self.assertLessEqual(razao, M.MAX_RATIO + 1e-9, (hl, hr, el))
            self.assertGreaterEqual(razao, 1 / M.MAX_RATIO - 1e-9)

    def test_trecho_menor_que_o_passo_nao_subdivide(self):
        self.assertEqual(M.divide(1.0, 1.0, 1.0), (0, 1.0, 1.0))

    def test_entrada_degenerada(self):
        for args in [(0.0, 0.1, 1.0), (0.1, 0.0, 1.0), (0.1, 0.1, 0.0),
                     (-0.1, 0.1, 1.0)]:
            self.assertEqual(M.divide(*args), (0, 1.0, 1.0), args)

    def test_a_soma_dos_passos_fecha_o_trecho(self):
        """A progressão tem de chegar exatamente na linha seguinte."""
        for hl, hr, el in [(0.02, 0.4, 2.0), (0.1, 0.03, 0.35),
                           (0.05, 0.15, 0.5)]:
            n, razao, primeiro = M.divide(hl, hr, el)
            soma = sum(primeiro * el * razao ** i for i in range(n + 1))
            self.assertAlmostEqual(soma, el, places=9, msg=(hl, hr, el))


class TestPosicoes(unittest.TestCase):
    def test_comeca_e_termina_nas_linhas_pedidas(self):
        p = M.positions([M.Line(0.0, 0.02), M.Line(2.0, 0.4)])
        self.assertAlmostEqual(p[0], 0.0)
        self.assertAlmostEqual(p[-1], 2.0)

    def test_passa_por_toda_linha_pedida(self):
        m = M.default_mesh()
        p = M.positions(m.x)
        for ln in m.x:
            self.assertTrue(any(abs(v - ln.loc) < 1e-9 for v in p), ln.loc)

    def test_ordenado_e_sem_repeticao(self):
        p = M.positions(M.default_mesh().y)
        self.assertEqual(p, sorted(p))
        for a, b in zip(p, p[1:]):
            self.assertGreater(b - a, 0)

    def test_refina_onde_o_espacamento_e_menor(self):
        """Na superfície o passo é 0,02 µm; no fundo, 0,4."""
        p = M.positions(M.default_mesh().y)
        self.assertLess(p[1] - p[0], p[-1] - p[-2])


class TestContraOMotor(unittest.TestCase):
    """As posições são as que o motor imprimiu, não as que eu calculei."""

    def setUp(self):
        self.m = M.default_mesh()

    def test_mesmo_numero_de_linhas_em_x(self):
        self.assertEqual(len(M.positions(self.m.x)), len(X_MOTOR))

    def test_mesmas_posicoes_em_x(self):
        for esperado, obtido in zip(X_MOTOR, M.positions(self.m.x)):
            self.assertAlmostEqual(obtido, esperado, delta=TOLERANCIA)

    def test_mesmas_posicoes_no_inicio_de_y(self):
        for esperado, obtido in zip(Y_MOTOR_INICIO, M.positions(self.m.y)):
            self.assertAlmostEqual(obtido, esperado, delta=TOLERANCIA)

    def test_contagem_de_nos_do_motor(self):
        """O motor relata "Points = 450" para esta malha."""
        self.assertEqual(M.stats(self.m).nodes, 450)

    def test_interpolacao_linear_erraria(self):
        """Guarda contra a tentação de simplificar :func:`mesh.divide`.

        Com o espaçamento interpolado linearmente, o eixo y daria 22 linhas
        em vez das 25 que o motor cria — e a pré-visualização mostraria uma
        malha que o motor não gera.
        """
        linear = [self.m.y[0].loc]
        for a, b in zip(self.m.y, self.m.y[1:]):
            pos = a.loc
            while True:
                frac = (pos - a.loc) / (b.loc - a.loc)
                passo = a.spacing + frac * (b.spacing - a.spacing)
                if pos + passo >= b.loc - 1e-12:
                    break
                pos += passo
                linear.append(pos)
            linear.append(b.loc)
        self.assertNotEqual(len(linear), len(M.positions(self.m.y)))


class TestEstatisticas(unittest.TestCase):
    def test_triangulos_sao_dois_por_celula(self):
        m = M.Mesh(x=[M.Line(0.0, 0.5), M.Line(1.0, 0.5)],
                   y=[M.Line(0.0, 0.5), M.Line(1.0, 0.5)])
        s = M.stats(m)
        self.assertEqual(s.triangles, 2 * (len(s.x_positions) - 1)
                         * (len(s.y_positions) - 1))

    def test_menor_passo_e_o_menor_dos_dois_eixos(self):
        s = M.stats(M.default_mesh())
        passos = ([b - a for a, b in zip(s.x_positions, s.x_positions[1:])]
                  + [b - a for a, b in zip(s.y_positions, s.y_positions[1:])])
        self.assertAlmostEqual(s.min_spacing, min(passos))

    def test_malha_invalida_traz_o_erro_e_nao_os_numeros(self):
        s = M.stats(M.Mesh(x=[M.Line(0.0, 0.1)], y=[M.Line(0.0, 0.1)]))
        self.assertFalse(s.ok)
        self.assertTrue(s.error)
        self.assertEqual(s.nodes, 0)

    def test_malha_padrao_nao_e_lenta(self):
        s = M.stats(M.default_mesh())
        self.assertFalse(s.slow)
        self.assertFalse(s.risky)

    def test_malha_grande_avisa(self):
        m = M.Mesh(x=[M.Line(0.0, 0.002), M.Line(1.0, 0.002)],
                   y=[M.Line(0.0, 0.002), M.Line(1.0, 0.002)])
        s = M.stats(m)
        self.assertTrue(s.slow)
        self.assertGreater(s.estimated_seconds, 0)

    def test_as_tres_faixas_de_tamanho(self):
        """Convergida, lenta e arriscada, nesta ordem."""
        self.assertLess(M.CONVERGED_NODE_COUNT, M.SLOW_NODE_COUNT)
        self.assertLess(M.SLOW_NODE_COUNT, M.MAX_SAFE_NODES)

    def test_malha_acima_do_teto_e_arriscada(self):
        s = M.MeshStats(nodes=M.MAX_SAFE_NODES + 1)
        self.assertTrue(s.risky)
        self.assertTrue(s.slow)

    def test_malha_do_tamanho_do_ldd_nao_e_arriscada(self):
        """O LDD do manual roda até 8.540 nós; o teto fica acima disso."""
        self.assertFalse(M.MeshStats(nodes=8540).risky)

    def test_extensao_da_area(self):
        self.assertEqual(M.extent(M.default_mesh()), (0.0, 1.0, 0.0, 2.0))

    def test_extensao_de_malha_vazia(self):
        self.assertEqual(M.extent(M.Mesh()), (0.0, 1.0, 0.0, 1.0))


class TestCartoes(unittest.TestCase):
    def setUp(self):
        self.cards = M.to_cards(M.default_mesh())
        self.texto = "\n".join(self.cards)

    def test_entra_em_modo_bidimensional(self):
        self.assertEqual(self.cards[0], "mode two.dim")

    def test_uma_linha_por_cartao(self):
        linhas = [c for c in self.cards if c.startswith("line ")]
        m = M.default_mesh()
        self.assertEqual(len(linhas), len(m.x) + len(m.y))

    def test_as_bordas_sao_marcadas(self):
        for tag in ("esq", "dir", "topo", "fundo"):
            self.assertIn(f"tag={tag}", self.texto)

    def test_so_as_bordas_tem_tag(self):
        """Uma tag no meio do eixo não serviria a region nem a boundary."""
        self.assertEqual(self.texto.count("tag="), 4)

    def test_a_regiao_usa_as_quatro_tags(self):
        regiao = next(c for c in self.cards if c.startswith("region"))
        for t in ("xlo=esq", "xhi=dir", "ylo=topo", "yhi=fundo"):
            self.assertIn(t, regiao)

    def test_a_superficie_fica_exposta(self):
        """Sem ``exposed`` no topo, a difusão em O₂ não cresce óxido."""
        self.assertIn("boundary exposed xlo=esq xhi=dir ylo=topo yhi=topo",
                      self.cards)

    def test_as_laterais_refletem(self):
        """Só metade do dispositivo é simulada, como nos exemplos."""
        self.assertEqual(len([c for c in self.cards
                              if c.startswith("boundary reflecting")]), 2)

    def test_malha_incompleta_nao_gera_cartao(self):
        self.assertEqual(M.to_cards(M.Mesh()), [])
        self.assertEqual(M.to_cards(M.Mesh(x=[M.Line(0.0, 0.1)])), [])

    def test_numero_sem_zeros_sobrando(self):
        """1.0 sai como ``1``, não ``1.000000``."""
        self.assertIn("line x loc=0.6 spacing=0.05", self.cards)
        self.assertIn("line y loc=2 spacing=0.4 tag=fundo", self.cards)

    def test_todo_cartao_e_conhecido_pelo_motor(self):
        from mos_studio.core import suprem4

        self.assertEqual(suprem4.unknown_cards(self.texto), [])


class TestConferenciaComOMotor(unittest.TestCase):
    """O motor gera a malha e devolve a contagem, para comparar."""

    @classmethod
    def setUpClass(cls):
        from mos_studio.core import suprem4

        if suprem4.find_run_dir() is None:
            raise unittest.SkipTest("SUPREM-IV não está instalado")

    def test_o_motor_concorda_com_a_previsao(self):
        m = M.default_mesh()
        nos, erro = M.engine_check(m)
        self.assertEqual(erro, "")
        self.assertEqual(nos, M.stats(m).nodes)

    def test_concorda_tambem_com_a_malha_refinada(self):
        m = M.default_mesh()
        m.y[0].spacing = 0.005
        nos, erro = M.engine_check(m)
        self.assertEqual(erro, "")
        self.assertEqual(nos, M.stats(m).nodes)

    def test_malha_incompleta_nao_vai_ao_motor(self):
        nos, erro = M.engine_check(M.Mesh(x=[M.Line(0.0, 0.1)]))
        self.assertEqual(nos, 0)
        self.assertIn("linhas", erro)


class TestMalhaPadrao(unittest.TestCase):
    """Os valores são os do ``exam5``, o transistor LDD do manual."""

    def test_refina_na_borda_da_porta(self):
        m = M.default_mesh()
        porta = next(ln for ln in m.x if abs(ln.loc - 0.35) < 1e-9)
        self.assertLess(porta.spacing, m.x[0].spacing)

    def test_refina_na_superficie(self):
        m = M.default_mesh()
        self.assertLess(m.y[0].spacing, m.y[-1].spacing)

    def test_meio_micron_de_lateral_e_dois_de_profundidade(self):
        x0, x1, y0, y1 = M.extent(M.default_mesh())
        self.assertAlmostEqual(x1 - x0, 1.0)
        self.assertAlmostEqual(y1 - y0, 2.0)

    def test_e_valida(self):
        m = M.default_mesh()
        self.assertEqual(M.validate_axis(m.x), "")
        self.assertEqual(M.validate_axis(m.y), "")


if __name__ == "__main__":
    unittest.main()
