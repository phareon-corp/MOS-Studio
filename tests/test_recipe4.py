"""A receita do motor 2-D.

A classe :class:`TestContraOMotor` submete ao binário um cartão de cada
variante de etapa. Foi ela que pegou dois erros reais: ``deposit …
concentration=`` (o nome tem treze letras e o motor guarda onze) e ``option
/quiet`` (o shell não tem negação com barra; o oposto é ``option normal``).
"""

from __future__ import annotations

import unittest

from mos_studio.core import recipe4 as R

#: Uma variante de cada etapa, com os desvios que mudam o cartão gerado.
VARIANTES: list[tuple[str, dict]] = [
    ("INIT", {}),
    ("DEPOSIT", {}),
    ("DEPOSIT", {"impurity": "boron", "conc": "1E18"}),
    ("ETCH", {"mode": "all"}),
    ("ETCH", {"mode": "dry", "thick": "0.05"}),
    ("ETCH", {"mode": "left", "p1x": "0.35"}),
    ("ETCH", {"mode": "right", "p1x": "0.35"}),
    ("ETCH", {"mode": "coords", "coords": "0,-1; 0.3,-1; 0.3,1; 0,1"}),
    ("IMPLANT", {}),
    ("IMPLANT", {"model": "gauss", "tilt": "7"}),
    ("DIFFUSE", {"ambient": "nitrogen"}),
    ("DIFFUSE", {"ambient": "dryo2"}),
    ("DIFFUSE", {"ambient": "weto2", "pressure": "1"}),
    ("DIFFUSE", {"ambient": "phosphorus", "gas_conc": "1E20"}),
    ("DIFFUSE", {"ambient": "nitrogen", "ramp_to": "1100"}),
    ("METHOD", {}),
    ("METHOD", {"model": "full.cpl", "oxide": "viscous", "grid_ox": "0.01"}),
    ("OPTION", {"quiet": True}),
    ("OPTION", {"quiet": False}),
    ("STRUCTURE", {}),
    ("STRUCTURE", {"mirror": "left"}),
]


def passo(tipo: str, **params) -> R.Step4:
    s = R.Step4.new(tipo)
    s.params.update(params)
    return s


def ldd() -> list[R.Step4]:
    """A receita do transistor LDD, que é o projeto guiado da interface."""
    return [
        passo("INIT", impurity="boron", conc="1E15", orient="100"),
        passo("DIFFUSE", ambient="dryo2", temp="1000", time="30"),
        passo("DEPOSIT", material="poly", thick="0.3", divisions="6"),
        passo("ETCH", material="poly", mode="right", p1x="0.35"),
        passo("IMPLANT", impurity="phosphorus", dose="5E13", energy="40"),
        passo("DIFFUSE", ambient="nitrogen", temp="900", time="30"),
        passo("DEPOSIT", material="oxide", thick="0.15", divisions="4"),
        passo("ETCH", material="oxide", mode="dry", thick="0.15"),
        passo("IMPLANT", impurity="arsenic", dose="5E15", energy="60"),
        passo("DIFFUSE", ambient="nitrogen", temp="900", time="20"),
    ]


class TestVocabulario(unittest.TestCase):
    def test_todo_tipo_tem_campos_e_padroes(self):
        for t in R.STEP_TYPES:
            self.assertIn(t, R.FIELDS, t)
            self.assertIn(t, R.DEFAULTS, t)
            self.assertIn(t, R.STEP_LABELS, t)
            self.assertIn(t, R.STEP_DESCRIPTIONS, t)

    def test_todo_padrao_corresponde_a_um_campo(self):
        for t, padroes in R.DEFAULTS.items():
            chaves = {f.key for f in R.FIELDS[t]}
            self.assertEqual(set(padroes) - chaves, set(), t)

    def test_ambiente_inerte_nao_e_inert(self):
        """O motor responde "parameter inert does not exist for this command"."""
        self.assertNotIn("inert", R.AMBIENTS)
        self.assertIn("nitrogen", R.AMBIENTS)
        self.assertIn("argon", R.AMBIENTS)

    def test_so_o_oxigenio_cresce_oxido(self):
        self.assertEqual(R.OXIDIZING, {"dryo2", "weto2"})

    def test_implante_aceita_mais_especies_que_a_difusao(self):
        self.assertIn("bf2", R.IMPLANT_IONS)
        self.assertNotIn("bf2", R.IMPURITIES)

    def test_tipo_desconhecido_e_recusado(self):
        with self.assertRaises(ValueError):
            R.Step4.new("NAO.EXISTE")

    def test_cada_etapa_nova_tem_uid_proprio(self):
        self.assertNotEqual(R.Step4.new("INIT").uid, R.Step4.new("INIT").uid)

    def test_copia_e_independente(self):
        a = passo("INIT")
        b = a.copy()
        b.params["conc"] = "1E17"
        self.assertNotEqual(a.params["conc"], b.params["conc"])


class TestCamposVisiveis(unittest.TestCase):
    def test_concentracao_da_camada_so_com_dopante(self):
        chaves = lambda s: [f.key for f in s.fields()]      # noqa: E731
        self.assertNotIn("conc", chaves(passo("DEPOSIT", impurity="")))
        self.assertIn("conc", chaves(passo("DEPOSIT", impurity="boron")))

    def test_espessura_da_corrosao_so_em_alguns_modos(self):
        chaves = lambda m: [f.key for f in passo("ETCH", mode=m).fields()]
        self.assertIn("thick", chaves("dry"))
        self.assertNotIn("thick", chaves("all"))
        self.assertIn("p1x", chaves("left"))
        self.assertIn("coords", chaves("coords"))

    def test_fonte_gasosa_so_com_ambiente_dopante(self):
        chaves = lambda a: [f.key for f in passo("DIFFUSE",
                                                 ambient=a).fields()]
        self.assertIn("gas_conc", chaves("phosphorus"))
        self.assertNotIn("gas_conc", chaves("dryo2"))


class TestCartoes(unittest.TestCase):
    def cartao(self, tipo: str, **params) -> str:
        return " / ".join(R.step_to_cards(passo(tipo, **params)))

    def test_init(self):
        self.assertEqual(self.cartao("INIT"),
                         "init boron conc=1e+15 orient=100")

    def test_deposito_dopado_usa_conc_abreviado(self):
        """``concentration`` tem treze letras e o motor guarda onze."""
        c = self.cartao("DEPOSIT", impurity="boron", conc="1E18")
        self.assertIn("conc=1e+18", c)
        self.assertNotIn("concentration", c)

    def test_deposito_sem_dopante_nao_menciona_concentracao(self):
        self.assertNotIn("conc", self.cartao("DEPOSIT", impurity=""))

    def test_corrosao_por_coordenadas_e_uma_sequencia(self):
        cs = R.step_to_cards(passo("ETCH", mode="coords",
                                   coords="0,-1; 0.3,-1; 0.3,1; 0,1"))
        self.assertEqual(len(cs), 4)
        self.assertIn("start", cs[0])
        self.assertIn("continue", cs[1])
        self.assertIn("done", cs[-1])

    def test_coordenadas_insuficientes_nao_geram_sequencia_quebrada(self):
        """Um ``etch done`` sem ``start`` derruba o motor com falha de
        segmentação; a verificação já aponta o problema antes de rodar."""
        cs = R.step_to_cards(passo("ETCH", mode="coords", coords="0,0"))
        self.assertEqual(cs, ["etch oxide all"])

    def test_temperatura_sai_em_celsius(self):
        """``diffuse.c`` soma 273, apesar de o suprem.key dizer Kelvin."""
        self.assertIn("temp=950", self.cartao("DIFFUSE", temp="950"))

    def test_rampa_repete_a_temperatura_inicial(self):
        c = self.cartao("DIFFUSE", temp="900", ramp_to="1100")
        self.assertIn("ramp start=900 stop=1100", c)

    def test_sem_rampa_nao_sai_cartao_de_rampa(self):
        self.assertNotIn("ramp", self.cartao("DIFFUSE", ramp_to=""))

    def test_saida_reduzida_e_o_oposto_dela(self):
        """``option /quiet`` é recusado; o oposto é ``option normal``."""
        self.assertEqual(self.cartao("OPTION", quiet=True), "option quiet")
        self.assertEqual(self.cartao("OPTION", quiet=False), "option normal")

    def test_espelho_vem_antes_de_gravar(self):
        cs = R.step_to_cards(passo("STRUCTURE", mirror="left"))
        self.assertTrue(cs[0].startswith("structure mirror"))
        self.assertIn("out=", cs[-1])

    def test_campo_vazio_cai_no_padrao(self):
        self.assertIn("thick=0.1", self.cartao("DEPOSIT", thick=""))

    def test_virgula_decimal_e_aceita(self):
        self.assertIn("thick=0.25", self.cartao("DEPOSIT", thick="0,25"))

    def test_nenhum_cartao_sai_vazio(self):
        for t, extra in VARIANTES:
            for c in R.step_to_cards(passo(t, **extra)):
                self.assertTrue(c.strip(), (t, extra))


class TestCoordenadas(unittest.TestCase):
    def test_pares_separados_por_ponto_e_virgula(self):
        self.assertEqual(R._parse_coords("0,0; 1,1"), [(0.0, 0.0), (1.0, 1.0)])

    def test_aceita_espaco_como_separador_do_par(self):
        self.assertEqual(R._parse_coords("0 0; 1 1"), [(0.0, 0.0), (1.0, 1.0)])

    def test_valores_negativos(self):
        self.assertEqual(R._parse_coords("0,-1; 0.5,1"),
                         [(0.0, -1.0), (0.5, 1.0)])

    def test_par_malformado_e_ignorado(self):
        self.assertEqual(R._parse_coords("0,0; lixo; 1,1"),
                         [(0.0, 0.0), (1.0, 1.0)])

    def test_texto_vazio(self):
        self.assertEqual(R._parse_coords(""), [])
        self.assertEqual(R._parse_coords(";;"), [])


class TestVerificacao(unittest.TestCase):
    def test_receita_vazia(self):
        self.assertTrue(R.validate([]))

    def test_receita_boa_nao_tem_problema(self):
        self.assertEqual(R.validate(ldd()), [])

    def test_inicializacao_tem_de_vir_primeiro(self):
        passos = [passo("DEPOSIT"), passo("INIT")]
        self.assertIn("primeira etapa", R.validate(passos)[0].message)

    def test_inicializacao_ausente(self):
        self.assertIn("Falta a Inicialização",
                      R.validate([passo("DEPOSIT")])[0].message)

    def test_duas_inicializacoes(self):
        passos = [passo("INIT"), passo("INIT")]
        self.assertIn("Só pode haver uma", R.validate(passos)[0].message)

    def test_numero_invalido(self):
        p = R.validate([passo("INIT", conc="muito")])
        self.assertIn("não é um número", p[0].message)

    def test_valor_fora_da_faixa(self):
        p = R.validate([passo("INIT", conc="1E30")])
        self.assertIn("fora da faixa", p[0].message)

    def test_campo_obrigatorio_vazio(self):
        p = R.validate([passo("INIT", conc="")])
        self.assertIn("sem valor", p[0].message)

    def test_campo_opcional_vazio_nao_e_problema(self):
        self.assertEqual(R.validate([passo("INIT"),
                                     passo("IMPLANT", tilt="")]), [])

    def test_corroer_o_que_nao_existe(self):
        passos = [passo("INIT"), passo("ETCH", material="nitride")]
        self.assertIn("nada para corroer", R.validate(passos)[-1].message)

    def test_corroer_o_que_foi_depositado(self):
        passos = [passo("INIT"), passo("DEPOSIT", material="nitride"),
                  passo("ETCH", material="nitride")]
        self.assertEqual(R.validate(passos), [])

    def test_corroer_oxido_crescido_na_oxidacao(self):
        """A oxidação põe óxido na pilha mesmo sem deposição."""
        passos = [passo("INIT"), passo("DIFFUSE", ambient="dryo2"),
                  passo("ETCH", material="oxide")]
        self.assertEqual(R.validate(passos), [])

    def test_corroer_silicio_e_sempre_permitido(self):
        passos = [passo("INIT"), passo("ETCH", material="silicon")]
        self.assertEqual(R.validate(passos), [])

    def test_corroer_duas_vezes_a_mesma_camada(self):
        passos = [passo("INIT"), passo("DEPOSIT", material="nitride"),
                  passo("ETCH", material="nitride", mode="all"),
                  passo("ETCH", material="nitride", mode="all")]
        self.assertIn("nada para corroer", R.validate(passos)[-1].message)

    def test_coordenadas_insuficientes(self):
        passos = [passo("INIT"), passo("DEPOSIT"),
                  passo("ETCH", mode="coords", coords="0,0")]
        self.assertIn("três pares", R.validate(passos)[-1].message)

    def test_arquivo_de_estrutura_sem_nome(self):
        passos = [passo("INIT"), passo("STRUCTURE", outfile="")]
        self.assertIn("nome do arquivo", R.validate(passos)[-1].message)

    def test_problemas_por_campo(self):
        passos = [passo("INIT", conc="muito")]
        chaves = R.field_problems(passos)
        self.assertIn((passos[0].uid, "conc"), chaves)


class TestAvisos(unittest.TestCase):
    """Avisos não impedem rodar, mas explicam um resultado surpreendente."""

    def test_implante_sem_recozimento(self):
        passos = [passo("INIT"), passo("IMPLANT")]
        self.assertIn("dopagem ativa", R.warnings(passos)[0].message)

    def test_implante_com_recozimento_depois(self):
        passos = [passo("INIT"), passo("IMPLANT"), passo("DIFFUSE")]
        self.assertEqual(R.warnings(passos), [])

    def test_so_o_implante_sem_recozimento_avisa(self):
        passos = [passo("INIT"), passo("IMPLANT"), passo("DIFFUSE"),
                  passo("IMPLANT")]
        avisos = R.warnings(passos)
        self.assertEqual(len(avisos), 1)
        self.assertEqual(avisos[0].index, 3)

    def test_poli_sem_oxido_de_porta(self):
        passos = [passo("INIT"), passo("DEPOSIT", material="poly")]
        self.assertTrue(any("óxido de porta" in a.message
                            for a in R.warnings(passos)))

    def test_poli_sobre_oxido_crescido_nao_avisa(self):
        passos = [passo("INIT"), passo("DIFFUSE", ambient="dryo2"),
                  passo("DEPOSIT", material="poly")]
        self.assertFalse(any("óxido de porta" in a.message
                             for a in R.warnings(passos)))

    def test_receita_do_ldd_nao_tem_aviso(self):
        self.assertEqual(R.warnings(ldd()), [])


class TestDeck(unittest.TestCase):
    def setUp(self):
        from mos_studio.core import mesh as M

        self.malha = M.to_cards(M.default_mesh())

    def test_comeca_com_o_titulo_em_comentario(self):
        d = R.build_deck("meu projeto", self.malha, ldd())
        self.assertTrue(d.startswith("# meu projeto\n"))

    def test_malha_antes_das_etapas(self):
        d = R.build_deck("t", self.malha, ldd())
        self.assertLess(d.index("line x"), d.index("init boron"))

    def test_termina_com_quit(self):
        d = R.build_deck("t", self.malha, ldd())
        self.assertEqual(d.strip().splitlines()[-1], "quit")

    def test_sem_corte_nao_sai_tabela(self):
        d = R.build_deck("t", self.malha, ldd())
        self.assertNotIn("print.1d", d)

    def test_o_corte_pede_x_value_nos_dois_prints(self):
        """Sem ``x.value`` o print.1d cai no modo de interface e zera tudo."""
        d = R.build_deck("t", self.malha, ldd(), print_cut=0.8)
        prints = [l for l in d.splitlines() if l.startswith("print.1d")]
        self.assertEqual(len(prints), 2)
        for l in prints:
            self.assertIn("x.value=0.8", l)

    def test_o_corte_seleciona_a_variavel_antes(self):
        """Sem ``select`` o motor responde "Z variable is out of date"."""
        d = R.build_deck("t", self.malha, ldd(), print_cut=0.8)
        self.assertLess(d.index("select z=doping"), d.index("print.1d"))

    def test_origem_de_cada_linha(self):
        pares = R.cards_with_origin(self.malha, ldd())
        malha = [u for c, u in pares if u is None]
        self.assertEqual(len(malha), len(self.malha))
        for c, u in pares[len(self.malha):]:
            self.assertIsNotNone(u)

    def test_toda_linha_do_deck_tem_origem(self):
        passos = ldd()
        pares = R.cards_with_origin(self.malha, passos)
        uids = {s.uid for s in passos} | {None}
        for _, u in pares:
            self.assertIn(u, uids)


class TestContraOMotor(unittest.TestCase):
    """Todo cartão gerado é submetido ao binário."""

    @classmethod
    def setUpClass(cls):
        from mos_studio.core import suprem4

        if suprem4.find_run_dir() is None:
            raise unittest.SkipTest("SUPREM-IV não está instalado")

    def test_todo_cabecalho_e_um_cartao_conhecido(self):
        """Um cabeçalho desconhecido é entregue ao ``/bin/sh`` pelo shell."""
        from mos_studio.core import suprem4

        for t, extra in VARIANTES:
            deck = "\n".join(R.step_to_cards(passo(t, **extra)))
            self.assertEqual(suprem4.unknown_cards(deck), [], (t, extra))

    def test_todo_parametro_existe_no_cartao(self):
        from mos_studio.core import keyfile

        for t, extra in VARIANTES:
            for linha in R.step_to_cards(passo(t, **extra)):
                nome, *resto = linha.split()
                c = keyfile.card(nome)
                self.assertIsNotNone(c, linha)
                for tok in resto:
                    chave = tok.split("=", 1)[0]
                    if "=" not in tok and c.get(chave) is None:
                        continue          # palavra solta: material, ambiente…
                    self.assertIsNotNone(c.get(chave), f"{chave} em {linha}")

    def test_o_motor_aceita_a_receita_do_ldd(self):
        from mos_studio.core import mesh as M, suprem4

        deck = R.build_deck("ldd", M.to_cards(M.default_mesh()), ldd(),
                            print_cut=0.8)
        saida = suprem4.run_sync(deck, timeout=300)
        self.assertEqual(suprem4.engine_errors(saida), [])

    def test_a_receita_do_ldd_produz_a_juncao_esperada(self):
        """Em x = 0,8 µm o corte cai na fonte/dreno, fora da porta."""
        from mos_studio.core import mesh as M, parsers, suprem4

        deck = R.build_deck("ldd", M.to_cards(M.default_mesh()), ldd(),
                            print_cut=0.8)
        xj = parsers.parse_print_1d_junction(suprem4.run_sync(deck,
                                                              timeout=300))
        self.assertIsNotNone(xj)
        self.assertGreater(xj, 0.05)
        self.assertLess(xj, 1.0)


if __name__ == "__main__":
    unittest.main()
