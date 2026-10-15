"""Leitura do arquivo de coeficientes (``modelrc``).

As amostras são recortes literais do arquivo da instalação, com as tabulações
preservadas — o arquivo mistura tabulação e espaço, e às vezes põe espaço
antes do ``=``.
"""

from __future__ import annotations

import unittest

from mos_studio.core import modelrc as M

AMOSTRA = (
    "# Oxidation parameters\n"
    "\n"
    "#---------- the dry parabolic coeff (singly activated)\n"
    "oxide  dry orient=111 par.h.0  =12.8667    par.h.e =1.23    p.break=0.\n"
    "oxide  dry orient=111 thinox.0 =5.87e6     thinox.e =2.32\n"
    "oxide  dry orient=100 thinox.0 =6.57e6     thinox.e =2.37\n"
    "oxide ori.dep = t\n"
    "oxide orient=100 ori.fac = 0.595\n"
    "arsenic\tsilicon\t\tDix.0=0.0666\tDix.E=3.44\n"
    "arsenic\toxide\t\tDix.0=1.75\tDix.E=4.89\n"
    "interst\tsilicon\tD.0=1.03e6 D.E=3.22;\n"
    "method vacan rel.err=0.01 abs.err=1.0e5\n"
    "method arsen rel.err=0.01 abs.err=1.0e9\n"
    "trap\tsilicon total=2.0e18 frac.0=2.386e5 enable\n"
    "unset interactive\n"
)


class TestFormato(unittest.TestCase):
    def test_le_todas_as_linhas_de_atribuicao(self):
        """Cinco de oxide, duas de arsenic, interst, duas de method, trap
        e o ``unset`` da primeira linha do arquivo."""
        linhas = M.parse(AMOSTRA)
        self.assertEqual(len(linhas), 12)

    def test_linha_de_comando_do_shell_fica_como_registro_inocuo(self):
        """``unset interactive`` não é cartão de modelo, mas não estorva:
        consulta por cartão nenhum vai cair nele."""
        r = next(x for x in M.parse(AMOSTRA) if x.card == "unset")
        self.assertEqual(r.qualifiers, ["interactive"])
        self.assertEqual(r.values, {})

    def test_separa_cartao_qualificadores_e_valores(self):
        r = M.parse(AMOSTRA)[0]
        self.assertEqual(r.card, "oxide")
        self.assertEqual(r.qualifiers, ["dry"])
        self.assertEqual(r.values["par.h.0"], "12.8667")

    def test_aceita_espaco_antes_e_depois_do_igual(self):
        r = M.parse(AMOSTRA)[0]
        self.assertEqual(r.values["par.h.e"], "1.23")
        self.assertEqual(r.values["p.break"], "0.")

    def test_seletor_entra_como_valor_tambem(self):
        """``orient=111`` é atribuição na forma, seletor no uso."""
        self.assertEqual(M.parse(AMOSTRA)[0].values["orient"], "111")

    def test_tabulacao_separa_como_espaco(self):
        r = next(x for x in M.parse(AMOSTRA) if x.card == "arsenic")
        self.assertEqual(r.qualifiers, ["silicon"])
        self.assertEqual(r.values["Dix.0"], "0.0666")

    def test_ignora_comentario_e_linha_vazia(self):
        for r in M.parse(AMOSTRA):
            self.assertFalse(r.card.startswith("#"))

    def test_descarta_ponto_e_virgula_final(self):
        r = next(x for x in M.parse(AMOSTRA) if x.card == "interst")
        self.assertEqual(r.values["D.E"], "3.22")

    def test_booleano_com_valor(self):
        r = next(x for x in M.parse(AMOSTRA)
                 if x.card == "oxide" and "ori.dep" in x.values)
        self.assertEqual(r.values["ori.dep"], "t")

    def test_booleano_como_palavra_solta(self):
        r = next(x for x in M.parse(AMOSTRA) if x.card == "trap")
        self.assertIn("enable", r.qualifiers)

    def test_arquivo_vazio(self):
        self.assertEqual(M.parse(""), [])
        self.assertEqual(M.parse("# nada\n\n"), [])


class TestCasamento(unittest.TestCase):
    def test_qualificador_pedido_precisa_estar_na_linha(self):
        r = next(x for x in M.parse(AMOSTRA) if x.card == "arsenic")
        self.assertTrue(r.matches("silicon"))
        self.assertFalse(r.matches("oxide"))

    def test_sem_qualificador_casa_qualquer_linha(self):
        self.assertTrue(M.parse(AMOSTRA)[0].matches())

    def test_seletor_compara_o_valor(self):
        linhas = [x for x in M.parse(AMOSTRA) if "thinox.0" in x.values]
        self.assertTrue(linhas[0].matches("dry", "orient=111"))
        self.assertFalse(linhas[0].matches("dry", "orient=100"))
        self.assertTrue(linhas[1].matches("dry", "orient=100"))

    def test_seletor_ausente_na_linha_nao_casa(self):
        r = next(x for x in M.parse(AMOSTRA) if x.card == "trap")
        self.assertFalse(r.matches("orient=100"))

    def test_canonizador_resolve_abreviacao(self):
        """É assim que o ``vacan`` do arquivo responde a ``vacancies``."""
        r = next(x for x in M.parse(AMOSTRA) if "abs.err" in x.values)
        canon = lambda q: {"vacan": "vacancies"}.get(q, q)      # noqa: E731
        self.assertTrue(r.matches("vacancies", canon=canon))
        self.assertFalse(r.matches("vacancies"))


class TestInstalacao(unittest.TestCase):
    """Contra o ``modelrc`` instalado — os números que o motor realmente usa."""

    @classmethod
    def setUpClass(cls):
        if not M.records():
            raise unittest.SkipTest("SUPREM-IV não está instalado")

    def test_coeficientes_do_arsenio(self):
        """O mockup dava ``Dix.0=8.0``; o motor usa 0,0666."""
        self.assertEqual(M.lookup("arsenic", "Dix.0", "silicon"), "0.0666")
        self.assertEqual(M.lookup("arsenic", "Dix.E", "silicon"), "3.44")
        self.assertEqual(M.lookup("arsenic", "Dim.0", "silicon"), "12.8")

    def test_coeficientes_dos_intersticios(self):
        """O mockup dava ``D.0=3650`` e ``Cstar.0=1.25e29``."""
        self.assertEqual(M.lookup("interstitial", "D.0", "silicon"), "1.03e6")
        self.assertEqual(M.lookup("interstitial", "Cstar.0", "silicon"),
                         "3.11e19")
        self.assertEqual(M.lookup("interstitial", "Kr.0", "silicon"), "1.40474")

    def test_coeficientes_das_vacancias(self):
        self.assertEqual(M.lookup("vacancy", "Cstar.0", "silicon"),
                         "4.77333e18")
        self.assertEqual(M.lookup("vacancy", "Cstar.E", "silicon"), "0.7134")

    def test_armadilhas(self):
        self.assertEqual(M.lookup("trap", "total", "silicon"), "2.0e18")
        self.assertEqual(M.lookup("trap", "frac.0", "silicon"), "2.386e5")

    def test_abreviacao_de_cartao(self):
        """O arquivo escreve ``interst``; a consulta usa o nome canônico."""
        self.assertEqual(M.lookup("interst", "D.0", "silicon"),
                         M.lookup("interstitial", "D.0", "silicon"))

    def test_abreviacao_de_parametro(self):
        """O arquivo escreve ``rel.err`` por ``rel.error``."""
        self.assertEqual(M.lookup("method", "rel.error", "psi"), "0.001")

    def test_abreviacao_de_qualificador(self):
        """O arquivo escreve ``vacan`` e ``arsen``."""
        self.assertEqual(M.lookup("method", "abs.error", "vacancies"), "1.0e5")
        self.assertEqual(M.lookup("method", "abs.error", "arsenic"), "1.0e9")

    def test_tolerancia_e_por_equacao(self):
        """O mockup usava um valor só para a aba toda."""
        self.assertNotEqual(M.lookup("method", "abs.error", "vacancies"),
                            M.lookup("method", "abs.error", "boron"))

    def test_regime_fino_do_oxido_e_por_orientacao(self):
        self.assertEqual(M.lookup("oxide", "thinox.0", "dry", "orient=100"),
                         "6.57e6")
        self.assertEqual(M.lookup("oxide", "thinox.0", "dry", "orient=111"),
                         "5.87e6")

    def test_fator_de_orientacao(self):
        """O B/A guardado é o de ⟨111⟩; as outras saem deste fator."""
        self.assertEqual(M.lookup("oxide", "ori.fac", "orient=111"), "1.0")
        self.assertEqual(M.lookup("oxide", "ori.fac", "orient=100"), "0.595")

    def test_o_seco_nao_tem_ramo_de_baixa_temperatura(self):
        """O joelho está em 0 °C, então ``lin.l.0`` não existe para o seco."""
        self.assertIsNone(M.lookup("oxide", "lin.l.0", "dry"))
        self.assertIsNotNone(M.lookup("oxide", "lin.l.0", "wet"))

    def test_parametro_inexistente_devolve_none(self):
        self.assertIsNone(M.lookup("arsenic", "nao.existe", "silicon"))
        self.assertIsNone(M.lookup("nao.existe", "D.0", "silicon"))

    def test_sobrescreve_a_gramatica(self):
        """O ``suprem.key`` diz 1e-9; o que vale é o 1.03e6 do modelrc."""
        from mos_studio.core import keyfile

        self.assertEqual(keyfile.card("interstitial").get("D.0").default,
                         "1e-9")
        self.assertEqual(M.lookup("interstitial", "D.0", "silicon"), "1.03e6")


if __name__ == "__main__":
    unittest.main()
