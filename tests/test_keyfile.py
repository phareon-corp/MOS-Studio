"""Leitura da gramática do motor (``suprem.key``).

As amostras são recortes literais do arquivo da instalação, com as tabulações
preservadas. Os testes que precisam do motor instalado estão separados e são
pulados quando ele não está.
"""

from __future__ import annotations

import unittest

from mos_studio.core import keyfile as K

#: Um cartão com switch, padrão de switch, unidades e mensagens de erro.
ARSENIC = """
card arsenic;
{
    # select type.
    switch model = 1
    units="active dopant type"
    message = "only one of donor or acceptor may be specified";
    {
\tboolean donor;
\tboolean acceptor;
    }

    boolean implanted;

    #neutral vacancies numbers
    float Dix.0 = 0.214 units = "Pre-exponential constant for Vo cm2/sec"
    message = "Negative values for Dix.0 will screw up the program"
    error = Dix.0 < 0.0;

    float Dix.E = 3.65 units = "Activation energy for Vo diffusivity - eV";

    switch material = 2
    message = "only one material may be specified";
    {
\tboolean silicon;
\tboolean oxide;
    }
}
"""

#: O cartão que tem um parâmetro de doze caracteres — o caso que o motor
#: trunca. Ver :data:`keyfile.MAX_PARAM`.
METHOD = """
card method;
{
    switch impurity = 0
    message = "pick one";
    {
\tboolean vacancies;
\tboolean interstitial;
    }
    float rel.error = 0.01 units = "relative error";
    int    line.com  = 3;
    string formula units="a formula giving dt as f(t)";
}
"""


class TestEstrutura(unittest.TestCase):
    def test_le_o_cartao_e_os_parametros(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertEqual(c.name, "arsenic")
        self.assertIn("Dix.0", [p.name for p in c.params])

    def test_le_o_valor_padrao(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertEqual(c.get("Dix.0").default, "0.214")
        self.assertAlmostEqual(c.get("Dix.E").as_float(), 3.65)

    def test_separa_unidade_da_mensagem(self):
        p = K.parse(ARSENIC)["arsenic"].get("Dix.0")
        self.assertIn("Pre-exponential", p.units)
        self.assertIn("screw up", p.message)

    def test_ignora_a_expressao_de_erro(self):
        """``error = Dix.0 < 0.0`` faz parte da declaração, não é parâmetro."""
        nomes = [p.name for p in K.parse(ARSENIC)["arsenic"].params]
        self.assertNotIn("error", nomes)
        self.assertNotIn("units", nomes)

    def test_distingue_numero_de_opcao(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertTrue(c.get("Dix.0").numeric)
        self.assertTrue(c.get("donor").flag)
        self.assertFalse(c.get("donor").numeric)

    def test_le_os_tres_tipos_restantes(self):
        c = K.parse(METHOD)["method"]
        self.assertEqual(c.get("line.com").type, "int")
        self.assertEqual(c.get("formula").type, "string")
        self.assertTrue(c.get("line.com").numeric)

    def test_comentario_nao_vira_parametro(self):
        nomes = [p.name for p in K.parse(ARSENIC)["arsenic"].params]
        self.assertNotIn("neutral", nomes)

    def test_arquivo_vazio(self):
        self.assertEqual(K.parse(""), {})
        self.assertEqual(K.parse("# só um comentário\n"), {})


class TestSwitches(unittest.TestCase):
    def test_agrupa_as_opcoes_pelo_switch(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertEqual([p.name for p in c.flags("model")],
                         ["donor", "acceptor"])
        self.assertEqual([p.name for p in c.flags("material")],
                         ["silicon", "oxide"])

    def test_opcao_fora_de_switch_nao_tem_grupo(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertEqual(c.get("implanted").switch, "")

    def test_lista_os_switches_na_ordem(self):
        self.assertEqual(K.parse(ARSENIC)["arsenic"].switches(),
                         ["model", "material"])

    def test_padrao_do_switch_e_base_um(self):
        """``switch material = 2`` liga a segunda opção, como em check.c."""
        c = K.parse(ARSENIC)["arsenic"]
        self.assertEqual(c.switch_default("model"), "donor")
        self.assertEqual(c.switch_default("material"), "oxide")

    def test_switch_sem_padrao(self):
        """``= 0`` significa que o motor não liga nenhuma sozinho."""
        self.assertEqual(K.parse(METHOD)["method"].switch_default("impurity"),
                         "")

    def test_parametros_nao_entram_na_lista_de_opcoes(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertNotIn("Dix.0", [p.name for p in c.flags()])


class TestNomesTruncados(unittest.TestCase):
    """O motor guarda nomes de parâmetro em ``char name[12]``.

    O ``keyread`` trunca ao compilar o ``suprem.uk`` e o motor depois recusa o
    nome completo: conferido contra o binário, ``method interstitial`` dá
    "parameter interstitial does not exist for this command", enquanto
    ``method interstitia`` é aceito. O nome do *cartão* não sofre disso —
    ``interstitial silicon D.0=1e6`` passa inteiro.
    """

    def test_guarda_o_nome_truncado(self):
        c = K.parse(METHOD)["method"]
        self.assertIn("interstitia", [p.name for p in c.params])
        self.assertNotIn("interstitial", [p.name for p in c.params])

    def test_o_nome_completo_ainda_resolve(self):
        c = K.parse(METHOD)["method"]
        self.assertEqual(c.canon("interstitial"), "interstitia")

    def test_abreviacao_resolve(self):
        c = K.parse(METHOD)["method"]
        self.assertEqual(c.canon("inter"), "interstitia")
        self.assertEqual(c.canon("rel.err"), "rel.error")

    def test_prefixo_ambiguo_nao_resolve(self):
        c = K.parse(ARSENIC)["arsenic"]
        self.assertIsNone(c.get("Dix."))          # Dix.0 e Dix.E

    def test_nome_desconhecido_volta_inteiro(self):
        c = K.parse(METHOD)["method"]
        self.assertEqual(c.canon("nao.existe"), "nao.existe")

    def test_nenhum_nome_passa_do_limite(self):
        for c in K.parse(METHOD + ARSENIC).values():
            for p in c.params:
                self.assertLessEqual(len(p.name), K.MAX_PARAM)


class TestInstalacao(unittest.TestCase):
    """Contra o ``suprem.key`` instalado."""

    @classmethod
    def setUpClass(cls):
        cls.cards = K.cards()
        if not cls.cards:
            raise unittest.SkipTest("SUPREM-IV não está instalado")

    def test_tem_os_cartoes_do_fluxo(self):
        for nome in ("initialize", "line", "region", "boundary", "deposit",
                     "etch", "implant", "diffuse", "method", "select",
                     "print.1d", "structure"):
            self.assertIn(nome, self.cards, nome)

    def test_nao_existe_cartao_impurity(self):
        """O mockup inventou um ``impurity``; o cartão é o nome da espécie."""
        self.assertNotIn("impurity", self.cards)
        self.assertIn("arsenic", self.cards)

    def test_resolve_abreviacao_de_cartao(self):
        self.assertEqual(K.resolve("interst"), "interstitial")
        self.assertEqual(K.resolve("diff"), "diffuse")

    def test_prefixo_ambiguo_de_cartao_nao_resolve(self):
        """``p`` serve a plot.1d, plot.2d, print.1d, printf, profile…"""
        self.assertEqual(K.resolve("p"), "")

    def test_fosforo_nao_tem_fi(self):
        """O mockup dava ``Fi`` ao fósforo; ele difunde por vacância."""
        p = self.cards["phosphorus"]
        self.assertIsNone(p.get("Fi"))
        self.assertIsNotNone(p.get("Dvx.0"))
        self.assertIsNotNone(self.cards["arsenic"].get("Fi"))

    def test_boro_difunde_por_defeito_positivo(self):
        b = self.cards["boron"]
        self.assertIsNotNone(b.get("Dip.0"))
        self.assertIsNone(b.get("Dim.0"))

    def test_trap_tem_total_sem_sufixo(self):
        """O mockup usava ``total.0``/``total.E``, que não existem."""
        t = self.cards["trap"]
        self.assertIsNotNone(t.get("total"))
        self.assertIsNotNone(t.get("frac.0"))
        self.assertEqual([p.name for p in t.numbers()],
                         ["total", "frac.0", "frac.E"])

    def test_modelos_de_oxidacao_estao_no_method(self):
        """O mockup punha erfc/viscous no cartão ``oxide``."""
        m = self.cards["method"]
        self.assertEqual(m.switch_default("oxidem"), "erfc")
        self.assertIn("viscous", [p.name for p in m.flags("oxidem")])
        self.assertIsNone(self.cards["oxide"].get("viscous"))

    def test_acoplamento_de_defeitos_no_method(self):
        m = self.cards["method"]
        self.assertEqual(m.switch_default("defectm"), "fermi")
        self.assertEqual([p.name for p in m.flags("defectm")],
                         ["fermi", "two.dim", "steady", "full.cpl"])

    def test_o_unico_parametro_truncado_que_a_interface_usa(self):
        self.assertEqual(self.cards["method"].canon("interstitial"),
                         "interstitia")


if __name__ == "__main__":
    unittest.main()
