"""A configuração vive no diretório do usuário, não ao lado do executável."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from mos_studio import config, paths


class TestLocal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._antigo = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name

    def tearDown(self):
        if self._antigo is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._antigo
        self._tmp.cleanup()

    @unittest.skipIf(paths.IS_WIN, "caminho XDG é do Linux")
    def test_fica_no_diretorio_de_configuracao_do_usuario(self):
        destino = paths.config_file()
        self.assertEqual(destino.parent, Path(self._tmp.name) / "mos-studio")
        self.assertTrue(destino.parent.is_dir())

    def test_nunca_ao_lado_do_executavel(self):
        self.assertNotEqual(paths.config_file().parent.resolve(),
                            paths.APP_ROOT.resolve())

    def test_grava_e_le(self):
        config.set("tema", "escuro")
        self.assertEqual(config.get("tema"), "escuro")

    def test_preserva_as_outras_chaves(self):
        config.set("tema", "escuro")
        config.set("minimos_dir", "/x")
        self.assertEqual(config.get("tema"), "escuro")
        self.assertEqual(config.get("minimos_dir"), "/x")

    def test_ausente_devolve_padrao(self):
        self.assertEqual(config.get("inexistente", "padrão"), "padrão")

    def test_arquivo_corrompido_nao_derruba(self):
        paths.config_file().write_text("{isto não é json", encoding="utf-8")
        self.assertEqual(config.load(), {})
        self.assertEqual(config.get("tema", "claro"), "claro")

    def test_importa_config_antigo_da_pasta_do_programa(self):
        legado = Path(self._tmp.name) / "config-antigo.json"
        legado.write_text(json.dumps({"minimos_dir": "/antigo"}),
                          encoding="utf-8")
        self.assertTrue(config.migrate_legacy(legado))
        self.assertEqual(config.get("minimos_dir"), "/antigo")
        self.assertTrue(legado.exists(), "o arquivo antigo não deve ser apagado")

    def test_importacao_nao_sobrescreve_o_que_ja_existe(self):
        config.set("minimos_dir", "/novo")
        legado = Path(self._tmp.name) / "config-antigo.json"
        legado.write_text(json.dumps({"minimos_dir": "/antigo"}),
                          encoding="utf-8")
        config.migrate_legacy(legado)
        self.assertEqual(config.get("minimos_dir"), "/novo")

    def test_importacao_sem_arquivo_antigo(self):
        self.assertFalse(config.migrate_legacy(Path(self._tmp.name) / "nada.json"))


if __name__ == "__main__":
    unittest.main()
