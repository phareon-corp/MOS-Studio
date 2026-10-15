"""O relatório de diagnóstico: a única voz do programa quando ele não abre.

No Windows o MOS-Studio é uma janela sem console. Se o Qt não achar um
plugin ou o motor não estiver onde devia, não há para onde escrever o erro —
o relatório é o que resta. Por isso ele tem de funcionar justamente nas
situações ruins: sem saída padrão, com pasta somente leitura, com motor
faltando.

Roda com a plataforma ``offscreen`` do Qt, sem precisar de tela.
"""

from __future__ import annotations

import io
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    TEM_QT = True
except ImportError:                                  # pragma: no cover
    TEM_QT = False

from mos_studio import diagnostico


class TestEscrever(unittest.TestCase):
    """``_escrever`` é a guarda contra o ``sys.stdout`` ausente."""

    def test_escreve_quando_ha_saida(self):
        fluxo = io.StringIO()
        with mock.patch.object(diagnostico.sys, "stdout", fluxo):
            diagnostico._escrever("oi\n")
        self.assertEqual(fluxo.getvalue(), "oi\n")

    def test_nao_levanta_quando_a_saida_e_nula(self):
        """É o caso do executável de janela do Windows: stdout vale None."""
        with mock.patch.object(diagnostico.sys, "stdout", None):
            diagnostico._escrever("some sem reclamar\n")

    def test_nao_levanta_quando_a_saida_esta_fechada(self):
        fluxo = io.StringIO()
        fluxo.close()
        with mock.patch.object(diagnostico.sys, "stdout", fluxo):
            diagnostico._escrever("tambem some\n")


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class TestRelatorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.texto, self.problemas = diagnostico.relatorio()

    def test_traz_as_quatro_secoes(self):
        for secao in ("AMBIENTE", "INTERFACE GRÁFICA",
                      "MOTORES DE SIMULAÇÃO", "JANELA PRINCIPAL"):
            with self.subTest(secao=secao):
                self.assertIn(secao, self.texto)

    def test_diz_a_versao_do_python_e_do_qt(self):
        import sys

        from PySide6.QtCore import qVersion

        self.assertIn(sys.version.split()[0], self.texto)
        self.assertIn(qVersion(), self.texto)

    def test_monta_a_janela_de_verdade(self):
        """Importar o PySide6 prova pouco; o que falha é o primeiro widget."""
        self.assertIn("MOS-Studio —", self.texto)
        self.assertIn("encerrada", self.texto)

    def test_lista_os_tres_motores_esteja_ou_nao_instalado(self):
        for motor in ("SUPREM-III", "SUPREM-IV.GS", "MINIMOS 6.1"):
            with self.subTest(motor=motor):
                self.assertIn(motor, self.texto)

    def test_nesta_maquina_nao_ha_problema(self):
        """Se este teste falhar, a instalação de desenvolvimento quebrou."""
        self.assertEqual(self.problemas, [])
        self.assertIn("Nenhum problema encontrado", self.texto)

    def test_sem_motor_de_processo_e_um_problema_declarado(self):
        from mos_studio.core import engines

        falsos = [mock.Mock(id=m.id, label=m.label,
                            available=lambda: False,
                            check=lambda _: ["não encontrado no teste"],
                            find_run_dir=lambda: None)
                  for m in engines.all_engines()]
        with mock.patch.object(engines, "all_engines", lambda: falsos):
            _, problemas = diagnostico._motores()
        self.assertIn("nenhum motor de processo está utilizável", problemas)


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class TestExecutar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Sem isto a função abriria a janela do relatório e travaria o teste.
        self._antes = os.environ.get("MOS_DIAGNOSTICO_SILENCIOSO")
        os.environ["MOS_DIAGNOSTICO_SILENCIOSO"] = "1"

    def tearDown(self):
        if self._antes is None:
            os.environ.pop("MOS_DIAGNOSTICO_SILENCIOSO", None)
        else:
            os.environ["MOS_DIAGNOSTICO_SILENCIOSO"] = self._antes

    def test_grava_o_relatorio_e_devolve_zero(self):
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "diagnostico.txt"
            fluxo = io.StringIO()
            with mock.patch.object(diagnostico.sys, "stdout", fluxo):
                codigo = diagnostico.executar(destino)
            self.assertEqual(codigo, 0)
            self.assertIn("AMBIENTE", destino.read_text(encoding="utf-8"))
            self.assertIn(str(destino), fluxo.getvalue())

    def test_pasta_somente_leitura_cai_na_configuracao_do_usuario(self):
        """Uma instalação em Program Files não aceita escrita."""
        with TemporaryDirectory() as pasta:
            # A pasta de configuração é desviada para o temporário: o teste
            # não deve deixar arquivo no ~/.config de quem o roda.
            config = Path(pasta) / "config"
            config.mkdir()
            destino = Path(pasta) / "sem-permissao" / "diagnostico.txt"
            with mock.patch.object(diagnostico.paths, "config_dir",
                                   lambda: config), \
                 mock.patch.object(diagnostico.sys, "stdout", io.StringIO()):
                codigo = diagnostico.executar(destino)
            self.assertEqual(codigo, 0)
            self.assertFalse(destino.exists())
            self.assertIn("AMBIENTE",
                          (config / "diagnostico.txt").read_text(
                              encoding="utf-8"))

    def test_sem_saida_padrao_ainda_grava_o_arquivo(self):
        """O caminho real do MOS-Studio.exe: nenhuma saída padrão."""
        with TemporaryDirectory() as pasta:
            destino = Path(pasta) / "diagnostico.txt"
            with mock.patch.object(diagnostico.sys, "stdout", None):
                codigo = diagnostico.executar(destino)
            self.assertEqual(codigo, 0)
            self.assertTrue(destino.exists())


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class TestEntradaPelaLinhaDeComando(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_as_duas_formas_chamam_o_diagnostico(self):
        from mos_studio import app as app_mod

        for bandeira in ("--diagnostico", "--autoteste"):
            with self.subTest(bandeira=bandeira):
                with mock.patch("mos_studio.diagnostico.executar",
                                return_value=0) as chamado:
                    codigo = app_mod.main(["mos-studio", bandeira])
                self.assertEqual(codigo, 0)
                chamado.assert_called_once()


if __name__ == "__main__":
    unittest.main()
