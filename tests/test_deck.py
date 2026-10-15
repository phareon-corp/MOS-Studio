"""O gerador e o leitor de deck fazem exatamente o que faziam antes."""

from __future__ import annotations

import unittest
from pathlib import Path

from mos_studio.core import deck
from mos_studio.core.recipe import STEP_TYPES, Step

from . import legacy

RAIZ = Path(__file__).resolve().parent.parent


def todos_os_passos() -> list[dict]:
    return [Step.new(t).as_dict() for t in STEP_TYPES]


class TestGeracao(unittest.TestCase):
    def test_deck_termina_em_stop_e_usa_crlf(self):
        texto = deck.build_in_file("T", todos_os_passos())
        self.assertTrue(texto.endswith("STOP\r\n"))
        self.assertNotIn("\n\n", texto.replace("\r\n", "\n\n").replace("\n\n", "\r\n"))
        for linha in texto.split("\r\n"):
            self.assertNotIn("\n", linha, "sobrou um \\n solto numa continuação")

    def test_continuacao_comeca_com_mais_na_coluna_1(self):
        texto = deck.build_in_file("T", [Step.new("INITIALIZE").as_dict()])
        continuacoes = [ln for ln in texto.split("\r\n") if ln.startswith("+")]
        self.assertTrue(continuacoes)
        for ln in continuacoes:
            self.assertFalse(ln.startswith(" "), "continuação não pode ter espaço antes do +")

    def test_ida_e_volta_preserva_os_tipos(self):
        texto = deck.build_in_file("DIODO", todos_os_passos())
        titulo, passos = deck.parse_in_file(texto)
        self.assertEqual(titulo, "DIODO")
        self.assertEqual([p["type"] for p in passos], STEP_TYPES)

    def test_linhas_anotadas_batem_com_o_gerador(self):
        passos = [dict(Step.new(t).as_dict(), uid=i) for i, t in enumerate(STEP_TYPES)]
        montado = "\r\n".join(t for t, _ in deck.annotated_lines("T", passos)) + "\r\n"
        self.assertEqual(montado, deck.build_in_file("T", passos))

    def test_cada_linha_aponta_para_a_etapa_que_a_gerou(self):
        passos = [dict(Step.new("INITIALIZE").as_dict(), uid=7)]
        linhas = deck.annotated_lines("T", passos)
        self.assertIsNone(linhas[0][1])                  # TITLE
        self.assertEqual([u for _t, u in linhas[1:3]], [7, 7])  # comando + continuação
        self.assertIsNone(linhas[-1][1])                 # STOP


class TestPlot(unittest.TestCase):
    def test_plot_fora_do_catalogo_de_etapas(self):
        self.assertNotIn("PLOT", STEP_TYPES)

    def test_strip_plot_remove_comando_e_continuacoes(self):
        entrada = ("TITLE X\nPLOT NET ACTIVE XMAX=1\n+ CMIN=1E14\n"
                   "PRINT NET ACTIVE CONCENTR\nSTOP\n")
        saida = deck.strip_plot(entrada)
        self.assertNotIn("PLOT", saida)
        self.assertNotIn("CMIN", saida)
        self.assertIn("PRINT", saida)

    def test_deck_legado_com_plot_ainda_e_lido(self):
        _t, passos = deck.parse_in_file("TITLE X\nPLOT NET ACTIVE\nSTOP\n")
        self.assertEqual([p["type"] for p in passos], ["PLOT"])


class TestPerfilGarantido(unittest.TestCase):
    def test_injeta_print_quando_falta(self):
        saida = deck.ensure_profile_print("TITLE X\nETCH OXIDE\nSTOP\n")
        self.assertIn("Print Net Chemical Concentration", saida)

    def test_preserva_print_existente(self):
        entrada = "TITLE X\nPRINT NET ACTIVE CONCENTR\nSTOP\n"
        self.assertEqual(deck.ensure_profile_print(entrada), entrada)


@unittest.skipUnless(legacy.available(), "suprem3.py não está no repositório")
class TestParidadeComOLegado(unittest.TestCase):
    """O comportamento tem de ser o mesmo da versão Tkinter."""

    @classmethod
    def setUpClass(cls):
        cls.ns = legacy.namespace()

    def test_mesmas_funcoes_nos_decks_reais(self):
        arquivos = sorted(RAIZ.glob("suprem-run/examples/**/*.in"))
        self.assertTrue(arquivos, "nenhum deck de exemplo encontrado")
        for f in arquivos:
            texto = f.read_text(encoding="latin1", errors="replace")
            with self.subTest(arquivo=f.name):
                self.assertEqual(self.ns["parse_in_file"](texto),
                                 deck.parse_in_file(texto))
                self.assertEqual(self.ns["strip_plot"](texto),
                                 deck.strip_plot(texto))
                self.assertEqual(self.ns["ensure_profile_print"](texto),
                                 deck.ensure_profile_print(texto))
                titulo, passos = deck.parse_in_file(texto)
                self.assertEqual(self.ns["build_in_file"](titulo, passos),
                                 deck.build_in_file(titulo, passos))
                self.assertEqual(self.ns["build_profile_deck"](titulo, passos),
                                 deck.build_profile_deck(titulo, passos))

    def test_mesmo_codigo_por_etapa(self):
        for passo in todos_os_passos():
            with self.subTest(tipo=passo["type"]):
                self.assertEqual(self.ns["step_to_code"](passo),
                                 deck.step_to_code(passo))


if __name__ == "__main__":
    unittest.main()
