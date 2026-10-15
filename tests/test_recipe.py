"""A receita: campos, unidades, padrões e verificação."""

from __future__ import annotations

import unittest

from mos_studio.core import recipe as R


class TestCatalogo(unittest.TestCase):
    def test_os_sete_tipos_montaveis(self):
        self.assertEqual(sorted(R.STEP_TYPES),
                         sorted(["INITIALIZE", "DIFFUSION", "DEPOSITION", "ETCH",
                                 "IMPLANTI", "EPITAXY", "PRINT"]))

    def test_plot_nao_e_oferecido(self):
        self.assertNotIn("PLOT", R.STEP_TYPES)
        self.assertNotIn("PLOT", R.FIELDS)
        self.assertNotIn("PLOT", R.DEFAULTS)

    def test_todo_tipo_tem_rotulo_descricao_campos_e_padroes(self):
        for tipo in R.STEP_TYPES:
            with self.subTest(tipo=tipo):
                self.assertIn(tipo, R.STEP_LABELS)
                self.assertIn(tipo, R.STEP_DESCRIPTIONS)
                self.assertTrue(R.FIELDS[tipo])
                self.assertTrue(R.DEFAULTS[tipo])

    def test_todo_padrao_corresponde_a_um_campo(self):
        for tipo in R.STEP_TYPES:
            chaves = {f.key for f in R.FIELDS[tipo]}
            with self.subTest(tipo=tipo):
                self.assertEqual(set(R.DEFAULTS[tipo]) - chaves, set())

    def test_campo_numerico_tem_unidade_e_faixa(self):
        for tipo in R.STEP_TYPES:
            for f in R.FIELDS[tipo]:
                if f.kind != "number":
                    continue
                with self.subTest(tipo=tipo, campo=f.key):
                    self.assertTrue(f.unit, "campo numérico sem unidade")
                    self.assertIsNotNone(f.minimum)
                    self.assertIsNotNone(f.maximum)
                    self.assertLess(f.minimum, f.maximum)

    def test_rotulo_e_texto_de_dominio_nao_o_nome_cru_do_parametro(self):
        """O rótulo é uma frase em português, não a chave do deck.

        Coincidir com o nome do parâmetro é aceitável quando a palavra já é a
        do domínio (“Material”); o que não vale é exibir a abreviação do
        SUPREM (``THICKNES``, ``GAS.CONC``, ``dx``) como rótulo.
        """
        for tipo in R.STEP_TYPES:
            for f in R.FIELDS[tipo]:
                with self.subTest(tipo=tipo, campo=f.key):
                    self.assertTrue(f.label)
                    self.assertTrue(f.label[0].isupper())
                    if f.label.lower() == f.key.lower():
                        self.assertTrue(
                            f.key.isalpha() and len(f.key) >= 4,
                            "rótulo repete uma abreviação do deck")

    def test_valores_padrao_passam_na_verificacao(self):
        for tipo in R.STEP_TYPES:
            passo = R.Step.new(tipo)
            for f in passo.fields():
                with self.subTest(tipo=tipo, campo=f.key):
                    self.assertIsNone(R.check_field(passo, f))


class TestCamposCondicionais(unittest.TestCase):
    def test_gas_conc_so_com_ambiente_dopante(self):
        passo = R.Step.new("DIFFUSION")
        passo.params["ambient"] = "NITROGEN"
        self.assertNotIn("gasConc", {f.key for f in passo.fields()})
        passo.params["ambient"] = "PHOSPHOR"
        self.assertIn("gasConc", {f.key for f in passo.fields()})

    def test_espessura_da_corrosao_so_quando_nao_remove_tudo(self):
        passo = R.Step.new("ETCH")
        self.assertNotIn("thickness", {f.key for f in passo.fields()})
        passo.params["all"] = False
        self.assertIn("thickness", {f.key for f in passo.fields()})


class TestVerificacao(unittest.TestCase):
    def receita_valida(self) -> list[R.Step]:
        return [R.Step.new("INITIALIZE"), R.Step.new("DIFFUSION"),
                R.Step.new("ETCH"), R.Step.new("PRINT")]

    def test_receita_valida_nao_tem_problema(self):
        self.assertEqual(R.validate(self.receita_valida()), [])

    def test_receita_vazia(self):
        self.assertEqual(len(R.validate([])), 1)

    def test_inicializacao_tem_de_vir_primeiro(self):
        passos = [R.Step.new("DIFFUSION"), R.Step.new("INITIALIZE")]
        problemas = R.validate(passos)
        self.assertTrue(any("primeira etapa" in p.message for p in problemas))

    def test_falta_de_inicializacao(self):
        problemas = R.validate([R.Step.new("DIFFUSION")])
        self.assertTrue(any("Falta a Inicialização" in p.message for p in problemas))

    def test_valor_fora_da_faixa(self):
        passos = self.receita_valida()
        passos[1].params["temperature"] = "1400"
        problemas = R.validate(passos)
        self.assertEqual(len(problemas), 1)
        self.assertEqual(problemas[0].index, 1)
        self.assertEqual(problemas[0].key, "temperature")
        self.assertIn("fora da faixa", problemas[0].message)

    def test_valor_nao_numerico(self):
        passos = self.receita_valida()
        passos[1].params["time"] = "quinze"
        self.assertTrue(any("não é um número" in p.message
                            for p in R.validate(passos)))

    def test_campo_opcional_vazio_e_aceito(self):
        passos = self.receita_valida()
        passos[1].params["tRate"] = ""
        self.assertEqual(R.validate(passos), [])

    def test_corroer_o_que_nao_existe(self):
        passos = [R.Step.new("INITIALIZE"), R.Step.new("ETCH")]
        problemas = R.validate(passos)
        self.assertTrue(any("nada para corroer" in p.message for p in problemas))

    def test_deposicao_habilita_a_corrosao(self):
        deposicao = R.Step.new("DEPOSITION")
        deposicao.params["material"] = "OXIDE"
        passos = [R.Step.new("INITIALIZE"), deposicao, R.Step.new("ETCH")]
        self.assertEqual(R.validate(passos), [])

    def test_corroer_duas_vezes_a_mesma_camada(self):
        deposicao = R.Step.new("DEPOSITION")
        deposicao.params["material"] = "OXIDE"
        passos = [R.Step.new("INITIALIZE"), deposicao,
                  R.Step.new("ETCH"), R.Step.new("ETCH")]
        self.assertTrue(any("nada para corroer" in p.message
                            for p in R.validate(passos)))

    def test_virgula_decimal_e_aceita(self):
        passos = self.receita_valida()
        passos[1].params["time"] = "15,5"
        self.assertEqual(R.validate(passos), [])


class TestFormatacao(unittest.TestCase):
    def test_notacao_cientifica_vira_potencia(self):
        self.assertEqual(R.fmt_number("1E15"), "1×10¹⁵")
        self.assertEqual(R.fmt_number("5E-3"), "0,005")
        self.assertEqual(R.fmt_number("1E-4"), "1×10⁻⁴")

    def test_decimal_com_virgula(self):
        self.assertEqual(R.fmt_number("0.5"), "0,5")
        self.assertEqual(R.fmt_number(1000), "1000")

    def test_texto_invalido_passa_adiante(self):
        self.assertEqual(R.fmt_number("abc"), "abc")

    def test_le_virgula_decimal(self):
        self.assertAlmostEqual(R.parse_float("1,5"), 1.5)
        self.assertIsNone(R.parse_float(""))
        self.assertIsNone(R.parse_float("x"))


class TestResumos(unittest.TestCase):
    def test_resumo_em_linguagem_de_dominio(self):
        passo = R.Step.new("DIFFUSION")
        self.assertEqual(passo.summary(), "O₂ seco · 1000 °C · 15 min")

    def test_resumo_do_print_mostra_a_tabela(self):
        passo = R.Step("PRINT", {"what": "NET", "extra": "LAYER",
                                 "filename": "L.OUT"})
        self.assertIn("Camadas", passo.summary())

    def test_todo_tipo_tem_resumo(self):
        for tipo in R.STEP_TYPES:
            with self.subTest(tipo=tipo):
                self.assertTrue(R.Step.new(tipo).summary())


class TestEtapa(unittest.TestCase):
    def test_identidade_unica(self):
        a, b = R.Step.new("ETCH"), R.Step.new("ETCH")
        self.assertNotEqual(a.uid, b.uid)

    def test_duplicar_nao_compartilha_parametros(self):
        a = R.Step.new("DIFFUSION")
        b = a.copy()
        b.params["time"] = "99"
        self.assertNotEqual(a.params["time"], b.params["time"])
        self.assertNotEqual(a.uid, b.uid)

    def test_tipo_desconhecido(self):
        with self.assertRaises(ValueError):
            R.Step.new("PLOT")


if __name__ == "__main__":
    unittest.main()
