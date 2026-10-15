"""Ponta a ponta: clicar em “Simular processo” e ver o perfil na tela.

Este é o teste que prova o escopo desta etapa da migração. Precisa dos
binários nativos do SUPREM-III; sem eles, é pulado.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    TEM_QT = True
except ImportError:                                  # pragma: no cover
    TEM_QT = False

from mos_studio.core import suprem

MOTOR = suprem.find_run_dir()
TEM_MOTOR = MOTOR is not None and not suprem.check_engine(MOTOR)
LIMITE_MS = 120_000


@unittest.skipUnless(TEM_QT and TEM_MOTOR, "precisa de PySide6 e do motor nativo")
class TestSimulacaoCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mos_studio.ui import theme
        cls.app = QApplication.instance() or QApplication([])
        theme.apply(cls.app, "claro")

    def setUp(self):
        from mos_studio.ui.main_window import MainWindow
        self.janela = MainWindow()
        # a janela abre no Início, onde simular é inerte de propósito
        self.janela.go("processo")
        self.eventos: list[str] = []

    def tearDown(self):
        self.janela.close()
        self.janela.deleteLater()
        self.app.processEvents()

    def _rodar(self) -> dict:
        """Dispara a execução e espera o desfecho."""
        laco = QEventLoop()
        desfecho: dict = {}
        ctrl = self.janela._run
        ctrl.stage_changed.connect(self.eventos.append)
        ctrl.succeeded.connect(lambda r: (desfecho.update(ok=r), laco.quit()))
        ctrl.failed.connect(lambda m: (desfecho.update(erro=m), laco.quit()))
        ctrl.was_cancelled.connect(lambda: (desfecho.update(cancelado=True),
                                            laco.quit()))
        QTimer.singleShot(LIMITE_MS, laco.quit)
        self.janela.start_run()
        laco.exec()
        return desfecho

    def test_da_receita_ao_perfil_na_tela(self):
        desfecho = self._rodar()
        self.assertNotIn("erro", desfecho, desfecho.get("erro", ""))
        self.assertIn("ok", desfecho, "a execução não terminou a tempo")
        resultado = desfecho["ok"]

        # a cadeia inteira rodou, na ordem
        self.assertEqual(self.eventos, ["setup", "genii", "sup3"])
        self.assertEqual(resultado.stages, ["setup", "genii", "sup3"])

        # o perfil chegou à tela de resultados
        self.assertEqual(self.janela.current_area(), "resultados")
        self.assertTrue(self.janela.resultados._grafico.has_data)
        self.assertGreater(len(resultado.profile()), 20)

        # a junção foi medida e aparece com unidade
        self.assertNotEqual(self.janela.resultados._xj.text(), "—")
        self.assertEqual(self.janela.resultados._xj_unidade.text(), "µm")

        # a execução ficou guardada em disco
        self.assertIsNotNone(resultado.out_dir)
        self.assertTrue((resultado.out_dir / "INPUT.IN").exists())

    def test_deck_quebrado_mostra_o_erro_do_motor(self):
        self.janela.processo._start_manual_edit()
        self.janela.processo.deck.view.setPlainText(
            "TITLE QUEBRADO\nCOMANDO QUE NAO EXISTE\nSTOP")
        desfecho = self._rodar()
        self.assertIn("erro", desfecho)
        self.assertTrue(desfecho["erro"].strip())

        # o erro aparece na própria tela, com a mensagem original do motor
        painel = self.janela.processo.erro
        self.assertTrue(painel.isVisibleTo(self.janela.processo))
        self.assertIn("COMANDO", painel.raw.upper())
        self.assertEqual(self.janela.current_area(), "processo")

    def test_cancelar_nao_deixa_resultado(self):
        ctrl = self.janela._run
        laco = QEventLoop()
        desfecho: dict = {}
        ctrl.succeeded.connect(lambda r: (desfecho.update(ok=r), laco.quit()))
        ctrl.failed.connect(lambda m: (desfecho.update(erro=m), laco.quit()))
        ctrl.was_cancelled.connect(lambda: (desfecho.update(cancelado=True),
                                            laco.quit()))
        ctrl.started.connect(ctrl.cancel)       # cancela assim que começa
        QTimer.singleShot(LIMITE_MS, laco.quit)
        self.janela.start_run()
        laco.exec()
        # o motor é rápido: pode terminar antes do cancelamento chegar.
        self.assertTrue(desfecho, "nenhum desfecho")
        if "cancelado" in desfecho:
            self.assertEqual(self.janela.runs, [])

    def test_a_faixa_de_estado_relata_o_fim(self):
        self._rodar()
        self.assertTrue(self.janela.strip.isVisibleTo(self.janela))
        self.assertIn("conclu", self.janela.strip._text.text().lower())


if __name__ == "__main__":
    unittest.main()
