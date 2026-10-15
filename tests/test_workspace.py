"""Projetos salvos, pasta de trabalho e índice de execuções.

Tudo corre dentro de um ``XDG_CONFIG_HOME`` temporário, para que o teste não
toque na configuração real nem na pasta de simulações do usuário.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from mos_studio import config
from mos_studio.core import library, workspace
from mos_studio.core.recipe import Step


class Isolado(unittest.TestCase):
    """Base que redireciona configuração e pasta de trabalho."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._antigo = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        self.base = Path(self._tmp.name) / "trabalho"
        workspace.set_working_dir(self.base)

    def tearDown(self):
        if self._antigo is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._antigo
        self._tmp.cleanup()


class TestPastaDeTrabalho(Isolado):

    def test_troca_e_persiste(self):
        nova = Path(self._tmp.name) / "outra"
        workspace.set_working_dir(nova)
        self.assertEqual(workspace.working_dir(), nova)
        self.assertEqual(Path(config.get("pasta_trabalho")), nova)

    def test_cria_a_pasta_de_execucoes(self):
        self.assertTrue(workspace.runs_dir().is_dir())
        self.assertEqual(workspace.runs_dir().parent, self.base)


class TestProjeto(Isolado):

    def test_vem_de_uma_receita_com_as_etapas(self):
        p = workspace.Project.from_recipe(library.get("diodo-pn"))
        self.assertTrue(p.steps)
        self.assertTrue(p.title)
        self.assertTrue(all(isinstance(s, Step) for s in p.steps))

    def test_ciclo_de_gravar_e_ler(self):
        p = workspace.Project.from_recipe(library.get("fonte-dreno-nmos"))
        p.notes = "uma anotação"
        p.device = {"tox_nm": "20"}
        p.oxidation = {"ambient": "DRYO2"}
        caminho = p.save()
        self.assertTrue(caminho.exists())
        lido = workspace.Project.load(caminho)
        self.assertEqual(lido.name, p.name)
        self.assertEqual(lido.title, p.title)
        self.assertEqual(lido.notes, "uma anotação")
        self.assertEqual(lido.device, {"tox_nm": "20"})
        self.assertEqual(lido.oxidation, {"ambient": "DRYO2"})
        self.assertEqual([(s.type, s.params) for s in lido.steps],
                         [(s.type, s.params) for s in p.steps])

    def test_gravar_limpa_a_marca_de_sujo(self):
        p = workspace.Project.from_recipe(library.get("diodo-pn"))
        p.dirty = True
        p.save()
        self.assertFalse(p.dirty)

    def test_listagem_traz_os_projetos_gravados(self):
        for chave in ("diodo-pn", "poco-n"):
            workspace.Project.from_recipe(library.get(chave)).save()
        self.assertEqual(len(workspace.list_projects()), 2)

    def test_importa_de_um_deck(self):
        from mos_studio.core.deck import build_in_file
        receita = library.get("diodo-pn")
        texto = build_in_file(receita.title,
                             [s.as_dict() for s in receita.build()])
        p = workspace.Project.from_deck(texto, "importado")
        self.assertTrue(p.steps)
        self.assertEqual(len(p.steps),
                         len([s for s in receita.build()]))


class TestIndiceDeExecucoes(Isolado):

    def _pasta(self, nome: str) -> Path:
        d = workspace.runs_dir() / nome
        d.mkdir(parents=True, exist_ok=True)
        (d / "SAIDA.OUT").write_text("nada", encoding="utf-8")
        return d

    def test_registra_uma_pasta_e_a_lista(self):
        d = self._pasta("corrida_1")
        registro = workspace.record_dir(d, name="Minha corrida",
                                        elapsed=1.5, engine="SUPREM-III")
        self.assertIsNotNone(registro)
        nomes = [r.name for r in workspace.list_runs()]
        self.assertIn("Minha corrida", nomes)

    def test_pasta_inexistente_nao_vira_registro(self):
        self.assertIsNone(workspace.record_dir(
            workspace.runs_dir() / "nao_existe"))
        self.assertIsNone(workspace.record_dir(None))

    def test_renomear_e_anotar_persistem(self):
        d = self._pasta("corrida_2")
        r = workspace.record_dir(d, name="Antes")
        r.rename("Depois")
        r.set_note("observação")
        de_novo = [x for x in workspace.list_runs() if x.path == d][0]
        self.assertEqual(de_novo.name, "Depois")
        self.assertEqual(de_novo.note, "observação")

    def test_apagar_tira_do_indice_e_do_disco(self):
        d = self._pasta("corrida_3")
        r = workspace.record_dir(d, name="Some")
        r.delete()
        self.assertFalse(d.exists())
        self.assertNotIn(d, [x.path for x in workspace.list_runs()])

    def test_mais_recente_primeiro(self):
        import datetime
        a = workspace.record_dir(self._pasta("a"), name="A")
        b = workspace.record_dir(self._pasta("b"), name="B")
        a.when = datetime.datetime(2020, 1, 1)
        a.write_meta()
        b.when = datetime.datetime(2024, 1, 1)
        b.write_meta()
        ordem = [r.name for r in workspace.list_runs() if r.name in ("A", "B")]
        self.assertEqual(ordem, ["B", "A"])

    def test_importar_o_legado_nao_move_arquivos(self):
        legado = workspace.legacy_results_dir()
        if not legado.exists():
            self.skipTest("não há resultados/ da versão anterior aqui")
        antes = len(list(legado.iterdir()))
        workspace.import_legacy()
        self.assertEqual(len(list(legado.iterdir())), antes)
        self.assertTrue(workspace.legacy_imported())


if __name__ == "__main__":
    unittest.main()
