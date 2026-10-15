"""A biblioteca de receitas: todas precisam ser válidas e montáveis.

Estas receitas são a porta de entrada do app — são o que a tela de Início
oferece. Se uma delas não passa pela validação ou excede a malha do motor, o
usuário encontra um erro no primeiro clique.
"""

from __future__ import annotations

import unittest

from mos_studio.core import deck as deck_mod
from mos_studio.core import library
from mos_studio.core.recipe import MAX_GRID_POINTS, parse_float, validate

#: A receita em branco é um ponto de partida, não um processo: tem só o
#: substrato e nada para imprimir. As exigências de conteúdo não valem para ela.
EM_BRANCO = "em-branco"


def receitas_completas():
    return [r for r in library.RECIPES if r.key != EM_BRANCO]


class TestCatalogo(unittest.TestCase):

    def test_tem_receitas_e_chaves_unicas(self):
        self.assertGreaterEqual(len(library.RECIPES), 4)
        chaves = [r.key for r in library.RECIPES]
        self.assertEqual(len(chaves), len(set(chaves)))

    def test_get_desconhecido_cai_na_primeira(self):
        self.assertIs(library.get("nao-existe"), library.RECIPES[0])

    def test_todas_descrevem_o_que_fazem(self):
        for r in library.RECIPES:
            with self.subTest(receita=r.key):
                self.assertTrue(r.name.strip())
                self.assertTrue(r.description.strip())
                self.assertTrue(r.title.strip())
                self.assertGreaterEqual(r.step_count, 1)

    def test_as_receitas_de_processo_tem_mais_de_uma_etapa(self):
        for r in receitas_completas():
            with self.subTest(receita=r.key):
                self.assertGreaterEqual(r.step_count, 2)

    def test_a_receita_em_branco_traz_so_o_substrato(self):
        branca = library.get(EM_BRANCO)
        self.assertEqual([t for t, _ in branca.steps], ["INITIALIZE"])


class TestValidade(unittest.TestCase):

    def test_toda_receita_passa_na_validacao(self):
        for r in library.RECIPES:
            with self.subTest(receita=r.key):
                problemas = validate(r.build())
                self.assertEqual(
                    [p.message for p in problemas], [],
                    f"a receita {r.key} abriria com erro na tela")

    def test_nenhuma_estoura_a_malha_do_motor(self):
        """O SUPREM-III para em 500 nós; a receita tem de caber."""
        for r in library.RECIPES:
            init = [s for s in r.build() if s.type == "INITIALIZE"]
            if not init:
                continue
            with self.subTest(receita=r.key):
                p = init[0].params
                espessura = parse_float(p.get("thickness"))
                passo = parse_float(p.get("dx"))
                if not espessura or not passo:
                    continue
                self.assertLessEqual(espessura / passo, MAX_GRID_POINTS)

    def test_nenhuma_usa_plot(self):
        """PLOT saiu do catálogo: a biblioteca de gráficos é um esqueleto."""
        for r in library.RECIPES:
            self.assertNotIn("PLOT", [t for t, _ in r.steps])

    def test_toda_receita_comeca_inicializando_o_substrato(self):
        for r in library.RECIPES:
            with self.subTest(receita=r.key):
                self.assertEqual(r.steps[0][0], "INITIALIZE")

    def test_toda_receita_imprime_algum_resultado(self):
        """Sem PRINT a corrida termina sem nada para ler."""
        for r in receitas_completas():
            with self.subTest(receita=r.key):
                self.assertIn("PRINT", [t for t, _ in r.steps])


class TestDeckGerado(unittest.TestCase):

    def test_gera_deck_com_titulo_e_parada(self):
        for r in library.RECIPES:
            texto = deck_mod.build_in_file(r.title,
                                           [s.as_dict() for s in r.build()])
            with self.subTest(receita=r.key):
                self.assertTrue(texto.startswith("TITLE "))
                self.assertIn("STOP", texto)

    def test_continuacoes_comecam_com_mais_na_coluna_1(self):
        """Regra do formato: a continuação precisa do “+” na coluna 1."""
        for r in library.RECIPES:
            texto = deck_mod.build_in_file(r.title,
                                           [s.as_dict() for s in r.build()])
            for linha in texto.replace("\r\n", "\n").split("\n"):
                if linha.startswith(" ") and linha.strip():
                    self.fail(f"{r.key}: linha com recuo — {linha!r}")

    def test_ida_e_volta_pelo_leitor_de_deck(self):
        """O que o montador escreve, o leitor devolve igual."""
        for r in library.RECIPES:
            etapas = [s.as_dict() for s in r.build()]
            texto = deck_mod.build_in_file(r.title, etapas)
            titulo, lidas = deck_mod.parse_in_file(texto)
            with self.subTest(receita=r.key):
                self.assertEqual(titulo.strip().upper(),
                                 r.title.strip().upper())
                self.assertEqual([e["type"] for e in lidas],
                                 [e["type"] for e in etapas])


if __name__ == "__main__":
    unittest.main()
