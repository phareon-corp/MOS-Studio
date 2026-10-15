"""O catálogo dos exemplos de fábrica.

:class:`TestTodosRodam` executa **todos** os quinze exemplos que o catálogo
declara executáveis e confere que os três marcados como defeituosos falham
pelo motivo registrado. É um teste lento, e é o único jeito de o catálogo não
mentir: foi ele que mostrou que o ``exam11`` tem o mesmo defeito de GaAs do
``exam12``, e que o ``exam5pis`` não é defeituoso — só não pode rodar sozinho.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from mos_studio.core import examples4 as E


def tem_motor() -> bool:
    return E.base_dir() is not None


class TestCatalogo(unittest.TestCase):
    def test_todo_exemplo_tem_nome_e_descricao(self):
        for e in E.CATALOG:
            self.assertTrue(e.id and e.name and e.desc, e.id)

    def test_ids_nao_repetem(self):
        ids = [e.id for e in E.CATALOG]
        self.assertEqual(len(ids), len(set(ids)))

    def test_caminhos_nao_repetem(self):
        caminhos = [e.path for e in E.CATALOG]
        self.assertEqual(len(caminhos), len(set(caminhos)))

    def test_busca_por_id(self):
        self.assertEqual(E.get("exam5").name, "Transistor LDD")
        self.assertIsNone(E.get("nao.existe"))

    def test_dimensao_e_uma_das_duas(self):
        for e in E.CATALOG:
            self.assertIn(e.dim, ("1-D", "2-D"), e.id)

    def test_defeituoso_tem_o_motivo_escrito(self):
        for e in E.CATALOG:
            if not e.runnable:
                self.assertGreater(len(e.broken), 40, e.id)

    def test_continuacao_declara_o_anterior(self):
        for e in E.CATALOG:
            if e.continuation:
                self.assertTrue(e.after, e.id)

    def test_o_ldd_e_o_projeto_guiado(self):
        """A interface usa o exam5 como projeto guiado; tem de estar aqui."""
        ldd = E.get("exam5")
        self.assertEqual(ldd.dim, "2-D")
        self.assertTrue(ldd.runnable)


@unittest.skipUnless(tem_motor(), "SUPREM-IV não está instalado")
class TestContraAInstalacao(unittest.TestCase):
    def test_todos_estao_instalados(self):
        self.assertEqual(len(E.installed()), len(E.CATALOG))

    def test_le_o_texto_do_deck(self):
        self.assertIn("line", E.read(E.get("exam5")))

    def test_deck_inexistente_le_vazio(self):
        fantasma = E.Example("x", "exam99/nao.existe", "n", "1-D", "d")
        self.assertEqual(E.read(fantasma), "")
        self.assertIsNone(E.deck_path(fantasma))

    def test_a_dimensao_do_catalogo_bate_com_o_deck(self):
        """Foi este teste que corrigiu exam6 e exam11 para 2-D."""
        for e in E.CATALOG:
            self.assertEqual(E.dim_of(e), e.dim, e.id)

    def test_continuacao_nao_tem_malha_propria(self):
        """Por isso a dimensão dela não dá para deduzir do texto."""
        pis = E.get("exam5pis")
        self.assertNotIn("line x", E.read(pis))
        self.assertEqual(E.dim_of(pis), "2-D")

    def test_cartoes_resolvem_as_abreviacoes_de_fabrica(self):
        """Os decks escrevem ``bound expo``, ``meth compr``, ``stru outf=``."""
        cartoes = E.cards(E.get("exam7"))
        self.assertIn("method", cartoes)
        self.assertIn("structure", cartoes)
        self.assertNotIn("meth", cartoes)

    def test_o_resumo_cabe_numa_linha(self):
        for e in E.CATALOG:
            self.assertLessEqual(len(E.summary(e).split(" · ")), 5, e.id)

    def test_todo_exemplo_mostra_pelo_menos_um_cartao(self):
        for e in E.CATALOG:
            self.assertTrue(E.cards(e), e.id)

    def test_o_locos_e_o_exam7(self):
        """O mockup chamava o exam6 de LOCOS; ``fullrox`` é o recessado."""
        self.assertIn("LOCOS", E.get("exam7").name)
        self.assertIn("Calibração", E.get("exam6").name)

    def test_a_exportacao_pisces_e_o_segundo_deck_do_exam5(self):
        """O mockup atribuía o PISCES ao exam8, que é tensão no nitreto."""
        self.assertIn("pisc", E.read(E.get("exam5pis")).lower())
        self.assertNotIn("pisc", E.read(E.get("exam8")).lower())

    def test_prepara_copiando_os_vizinhos(self):
        work = Path(tempfile.mkdtemp(prefix="ex4t_"))
        try:
            prep = E.prepare(E.get("exam15"), work)
            self.assertEqual(prep.missing, [])
            self.assertTrue((work / prep.deck_name).is_file())
            self.assertTrue((work / "be1").is_file())   # o perfil que ele lê
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_deck_de_execucao_simples(self):
        work = Path(tempfile.mkdtemp(prefix="ex4t_"))
        try:
            e = E.get("exam1")
            self.assertEqual(E.run_deck(e, E.prepare(e, work)),
                             "source boron.in\nquit\n")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_deck_de_continuacao_encadeia(self):
        work = Path(tempfile.mkdtemp(prefix="ex4t_"))
        try:
            e = E.get("exam5pis")
            deck = E.run_deck(e, E.prepare(e, work))
            self.assertLess(deck.index("whole.s4"), deck.index("sup2pis.s4"))
        finally:
            shutil.rmtree(work, ignore_errors=True)


@unittest.skipUnless(tem_motor(), "SUPREM-IV não está instalado")
class TestTodosRodam(unittest.TestCase):
    """Executa o catálogo inteiro. Lento de propósito."""

    @classmethod
    def _rodar(cls, e: E.Example) -> tuple[int, str]:
        from mos_studio.core import suprem4

        rd = suprem4.find_run_dir()
        work = Path(tempfile.mkdtemp(prefix="ex4run_"))
        try:
            prep = E.prepare(e, work)
            entrada = work / "mosstudio.in"
            entrada.write_text(E.run_deck(e, prep), encoding="ascii",
                               errors="replace")
            p = subprocess.run(
                [str(rd / "bin" / "suprem"), entrada.name], cwd=str(work),
                env=suprem4._environment(rd, work),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=240)
            return p.returncode, p.stdout.decode("latin1", "replace")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_os_executaveis_rodam_sem_recusa(self):
        from mos_studio.core import suprem4

        for e in E.CATALOG:
            if not e.runnable:
                continue
            with self.subTest(exemplo=e.id):
                rc, saida = self._rodar(e)
                self.assertEqual(rc, 0, f"{e.id} terminou com {rc}")
                self.assertEqual(suprem4.engine_errors(saida), [],
                                 f"{e.id} teve recusa de cartão")

    def test_os_defeituosos_falham_pelo_motivo_registrado(self):
        """Se um dia pararem de falhar, o catálogo precisa ser corrigido."""
        from mos_studio.core import suprem4

        for e in E.CATALOG:
            if e.runnable:
                continue
            with self.subTest(exemplo=e.id):
                _, saida = self._rodar(e)
                self.assertTrue(suprem4.engine_errors(saida),
                                f"{e.id} parou de falhar: revise o catálogo")

    def test_o_pisces_gera_a_malha_quando_encadeado(self):
        """Sozinho ele responde "please specify a temperature"."""
        from mos_studio.core import suprem4

        rd = suprem4.find_run_dir()
        e = E.get("exam5pis")
        work = Path(tempfile.mkdtemp(prefix="ex4pis_"))
        try:
            prep = E.prepare(e, work)
            (work / "mosstudio.in").write_text(E.run_deck(e, prep))
            p = subprocess.run(
                [str(rd / "bin" / "suprem"), "mosstudio.in"], cwd=str(work),
                env=suprem4._environment(rd, work),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=240)
            saida = p.stdout.decode("latin1", "replace")
            self.assertEqual(suprem4.engine_errors(saida), [])
            self.assertTrue((work / "ldd.mesh").is_file(),
                            "a malha do PISCES não foi gravada")
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
