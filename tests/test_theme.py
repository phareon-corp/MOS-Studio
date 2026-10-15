"""A camada de tema: tokens completos e nenhuma cor literal solta na interface."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from mos_studio.ui.theme import tokens

RAIZ = Path(__file__).resolve().parent.parent
UI = RAIZ / "mos_studio" / "ui"
TEMA = UI / "theme"

#: Cor escrita à mão: #rgb, #rrggbb ou rgb(a)(...).
COR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(")
#: Família tipográfica escrita à mão.
FONTE_LITERAL = re.compile(r'QFont\(\s*["\']')


def arquivos_da_interface() -> list[Path]:
    return [p for p in UI.rglob("*.py") if TEMA not in p.parents and p.parent != TEMA]


class TestTokens(unittest.TestCase):
    def test_os_dois_temas_tem_as_mesmas_chaves(self):
        self.assertEqual(set(tokens.DARK), set(tokens.LIGHT))

    def test_tema_padrao_existe(self):
        self.assertIn(tokens.DEFAULT_THEME, tokens.PALETTES)

    def test_toda_cor_e_hex_ou_rgba(self):
        for nome, paleta in tokens.PALETTES.items():
            for chave, valor in paleta.items():
                with self.subTest(tema=nome, token=chave):
                    self.assertTrue(
                        valor.startswith("#") or valor.startswith("rgba("),
                        f"{chave} = {valor!r}")

    def test_paleta_desconhecida_cai_no_padrao(self):
        self.assertEqual(tokens.palette("inexistente"),
                         tokens.palette(tokens.DEFAULT_THEME))

    def test_escalas_nao_estao_vazias(self):
        for escala in (tokens.SPACE, tokens.RADIUS, tokens.DIMENSION,
                       tokens.FONT_SIZES, tokens.FONT_WEIGHTS,
                       tokens.LETTER_SPACING, tokens.FONT_STACKS):
            self.assertTrue(escala)

    def test_toda_cadeia_de_fontes_tem_alternativa(self):
        for papel, cadeia in tokens.FONT_STACKS.items():
            with self.subTest(papel=papel):
                self.assertGreaterEqual(len(cadeia), 2)


class TestSemLiteraisNaInterface(unittest.TestCase):
    """O design mora nos tokens: widget nenhum escreve cor ou fonte na mão."""

    def test_nenhuma_cor_literal_fora_do_tema(self):
        for arquivo in arquivos_da_interface():
            texto = arquivo.read_text(encoding="utf-8")
            achados = [ln for ln in texto.splitlines() if COR_LITERAL.search(ln)]
            with self.subTest(arquivo=arquivo.relative_to(RAIZ)):
                self.assertEqual(achados, [], "cor escrita à mão")

    def test_nenhuma_familia_tipografica_literal_fora_do_tema(self):
        for arquivo in arquivos_da_interface():
            texto = arquivo.read_text(encoding="utf-8")
            with self.subTest(arquivo=arquivo.relative_to(RAIZ)):
                self.assertIsNone(FONTE_LITERAL.search(texto),
                                  "QFont construído com família literal")

    def test_o_gerador_de_qss_nao_tem_cor_literal(self):
        texto = (TEMA / "qss.py").read_text(encoding="utf-8")
        # as cores entram por interpolação de token: {c['...']}
        sem_interpolacao = re.sub(r"\{[^{}]*\}", "", texto)
        self.assertIsNone(COR_LITERAL.search(sem_interpolacao))


class TestFolhaDeEstilo(unittest.TestCase):
    """Precisa de QApplication (as fontes são resolvidas pelo Qt)."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_gera_para_os_dois_temas(self):
        from mos_studio.ui.theme import qss
        for nome in tokens.PALETTES:
            with self.subTest(tema=nome):
                folha = qss.stylesheet(nome)
                self.assertIn("QWidget", folha)
                self.assertNotIn("{c[", folha, "sobrou interpolação por resolver")

    def test_cada_tema_usa_a_propria_cor_de_fundo(self):
        from mos_studio.ui.theme import qss
        self.assertIn(tokens.LIGHT["bg"], qss.stylesheet("claro"))
        self.assertIn(tokens.DARK["bg"], qss.stylesheet("escuro"))

    def test_nao_usa_propriedades_que_o_qt_ignora(self):
        from mos_studio.ui.theme import qss
        for ignorada in ("text-transform", "box-shadow", "transition",
                         "letter-spacing", "display:", "flex"):
            for nome in tokens.PALETTES:
                with self.subTest(tema=nome, propriedade=ignorada):
                    self.assertNotIn(ignorada, qss.stylesheet(nome))

    def test_resolve_fonte_para_todo_papel(self):
        from mos_studio.ui.theme import fonts
        for papel in tokens.FONT_STACKS:
            with self.subTest(papel=papel):
                self.assertTrue(fonts.resolve_family(papel))

    def test_espacamento_entre_letras_vem_da_fonte_nao_do_qss(self):
        from PySide6.QtGui import QFont
        from mos_studio.ui.theme import fonts
        f = fonts.font("mono", "micro", spacing="widest")
        self.assertAlmostEqual(f.letterSpacing(),
                               tokens.LETTER_SPACING["widest"], places=1)
        self.assertEqual(f.letterSpacingType(),
                         QFont.SpacingType.PercentageSpacing)


if __name__ == "__main__":
    unittest.main()
