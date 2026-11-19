"""Orquestração do SUPREM-III: ambiente, verificação, execução e cancelamento."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mos_studio import paths
from mos_studio.core import deck as D
from mos_studio.core import suprem
from mos_studio.core.recipe import Step

MOTOR = suprem.find_run_dir()
TEM_MOTOR = MOTOR is not None and not suprem.check_engine(MOTOR)

RECEITA = [
    Step("INITIALIZE", {"orientation": "100", "dopant": "BORON",
                        "concentration": "1E15", "dx": "5E-3",
                        "thickness": "0.5"}),
    Step("DIFFUSION", {"ambient": "PHOSPHOR", "temperature": "1000",
                       "time": "30", "gasConc": "1E18", "solidSol": False,
                       "tRate": ""}),
    Step("PRINT", {"what": "NET", "curve": "ACTIVE", "extra": "CONCENTR",
                   "filename": "PERFIL.OUT", "linespa": "1000"}),
]


def deck_de_teste() -> str:
    return D.build_in_file("TESTE AUTOMATICO",
                           [s.as_dict() for s in RECEITA])


class TestAmbiente(unittest.TestCase):
    """As dez variáveis dos arquivos de dados e o S3prs0 relativo."""

    def test_dez_arquivos_de_dados(self):
        self.assertEqual(len(suprem.DATA_FILES), 10)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @unittest.skipUnless(MOTOR is not None, "motor nativo ausente")
    def test_copia_os_dados_e_passa_o_nome_curto(self):
        """O fonte guarda o nome num character*80: caminho absoluto não serve."""
        env = suprem._environment(Path(MOTOR), self.work)
        for nome in suprem.DATA_FILES:
            if (Path(MOTOR) / nome).exists():
                with self.subTest(arquivo=nome):
                    self.assertEqual(env[nome], nome)
                    self.assertEqual((self.work / nome).read_bytes(),
                                     (Path(MOTOR) / nome).read_bytes())

    @unittest.skipUnless(MOTOR is not None, "motor nativo ausente")
    def test_s3prs0_e_relativo(self):
        """Caminho absoluto aqui quebra a execução — tem de ser relativo."""
        env = suprem._environment(Path(MOTOR), self.work)
        self.assertEqual(env["S3prs0"], "S3prs0")
        self.assertFalse(os.path.isabs(env["S3prs0"]))

    @unittest.skipUnless(MOTOR is not None, "motor nativo ausente")
    def test_preserva_o_ambiente_do_sistema(self):
        env = suprem._environment(Path(MOTOR), self.work)
        self.assertIn("PATH", env)

    @unittest.skipUnless(MOTOR is not None, "motor nativo ausente")
    def test_motor_numa_pasta_de_caminho_longo(self):
        """Regressão: com o caminho dos dados acima de 80 caracteres o genii
        parava em "ERROR # 33 ... formatted specification file"."""
        funda = self.work / ("pasta-com-nome-bem-comprido-" * 3) / "suprem-run"
        shutil.copytree(MOTOR, funda, symlinks=True)
        self.assertGreater(len(str(funda / "S3fky0")), 80)
        saida = suprem.run_sync("TITLE fundo\n"
                                "INITIALIZE <100> SILICON BORON CONCENTRATION=1E15 "
                                "THICKNESS=1 DX=.01\n"
                                "DIFFUSION TIME=10 TEMPERATURE=1000 DRYO2\n"
                                "PRINT LAYERS\nSTOP\n", run_dir=funda)
        self.assertNotIn("ERROR # 33", saida)
        self.assertIn("oxide", saida.lower())

    def test_ordem_dos_binarios(self):
        self.assertEqual(suprem.BINARIES, ("setup", "genii", "sup3"))


class TestVerificacao(unittest.TestCase):
    def test_pasta_inexistente(self):
        self.assertTrue(suprem.check_engine(None))
        self.assertTrue(suprem.check_engine(Path("/nao/existe")))

    def test_pasta_sem_binarios(self):
        with tempfile.TemporaryDirectory() as d:
            problemas = suprem.check_engine(Path(d))
            self.assertTrue(any("setup" in p for p in problemas))

    @unittest.skipUnless(TEM_MOTOR, "motor nativo ausente")
    def test_motor_do_repositorio_esta_pronto(self):
        self.assertEqual(suprem.check_engine(MOTOR), [])


class TestNomeDaPasta(unittest.TestCase):
    def test_sanitiza_o_titulo(self):
        self.assertEqual(suprem._safe_dirname("Diodo PN / difusão!"),
                         "Diodo_PN_difus_o")

    def test_titulo_vazio_vira_simulacao(self):
        self.assertEqual(suprem._safe_dirname("///"), "simulacao")

    def test_limita_o_tamanho(self):
        self.assertLessEqual(len(suprem._safe_dirname("A" * 200)), 40)


class TestResultado(unittest.TestCase):
    def test_perfil_vem_do_primeiro_arquivo_com_tabela(self):
        r = suprem.RunResult(deck="", files={
            "B.OUT": {"data": [], "raw": ""},
            "A.OUT": {"data": [(0.0, 1e17)], "raw": ""}})
        self.assertEqual(r.profile(), [(0.0, 1e17)])
        self.assertEqual(r.profile_source(), "A.OUT")

    def test_sem_tabela_devolve_vazio(self):
        r = suprem.RunResult(deck="", files={"A.OUT": {"data": [], "raw": ""}})
        self.assertEqual(r.profile(), [])
        self.assertEqual(r.profile_source(), "")


@unittest.skipUnless(TEM_MOTOR, "motor nativo ausente")
class TestExecucaoReal(unittest.TestCase):
    """Roda o SUPREM-III de verdade: é o teste de ponta a ponta do núcleo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.saida = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_executa_a_cadeia_completa_e_le_o_perfil(self):
        runner = suprem.SupremRunner(deck_de_teste(), results_dir=self.saida)
        etapas: list[str] = []
        r = runner.execute(on_stage=etapas.append)
        self.assertEqual(etapas, ["setup", "genii", "sup3"])
        self.assertEqual(r.stages, ["setup", "genii", "sup3"])
        perfil = r.profile()
        self.assertGreater(len(perfil), 20)
        self.assertAlmostEqual(perfil[0][0], 0.0, places=3)
        self.assertGreater(perfil[0][1], 1e16)      # superfície tipo n

    def test_grava_a_execucao_em_disco(self):
        r = suprem.SupremRunner(deck_de_teste(), results_dir=self.saida).execute()
        self.assertIsNotNone(r.out_dir)
        nomes = {p.name for p in Path(r.out_dir).iterdir()}
        self.assertIn("INPUT.IN", nomes)
        self.assertIn("PERFIL.OUT", nomes)

    def test_nao_deixa_pasta_temporaria_para_tras(self):
        antes = set(Path(tempfile.gettempdir()).glob("suprem_nat_*"))
        suprem.SupremRunner(deck_de_teste(), results_dir=self.saida).execute()
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("suprem_nat_*")),
                         antes)

    def test_deck_invalido_levanta_erro_com_a_mensagem_do_motor(self):
        runner = suprem.SupremRunner("TITLE X\nCOMANDO INVENTADO\nSTOP\n",
                                     results_dir=self.saida)
        with self.assertRaises(RuntimeError) as ctx:
            runner.execute()
        self.assertTrue(str(ctx.exception).strip())

    def test_cancelamento_interrompe(self):
        runner = suprem.SupremRunner(deck_de_teste(), results_dir=self.saida)
        runner.cancel()                      # cancela antes de começar
        with self.assertRaises(suprem.Cancelled):
            runner.execute()
        self.assertTrue(runner.cancelled)

    def test_run_sync_serve_a_analise_de_oxidacao(self):
        """É assim que a oxidação mede Xo: deck sem FILENAME, tabela de camadas.

        Com ``FILENAME=`` o PRINT escreve noutro arquivo e a saída principal
        guarda só o eco do deck — por isso o deck desta varredura imprime as
        camadas direto na saída padrão.
        """
        from mos_studio.core.parsers import parse_oxide_thickness
        oxidacao = D.build_in_file("OXIDACAO", [
            {"type": "INITIALIZE", "params": {
                "orientation": "100", "dopant": "BORON",
                "concentration": "1E15", "dx": "5E-3", "thickness": "0.5"}},
            {"type": "DIFFUSION", "params": {
                "ambient": "WETO2", "temperature": "1000", "time": "40",
                "gasConc": "", "solidSol": False, "tRate": ""}},
            {"type": "PRINT", "params": {
                "what": "", "curve": "", "extra": "LAYER",
                "filename": "", "linespa": ""}},
        ])
        texto = suprem.run_sync(oxidacao)
        espessura = parse_oxide_thickness(texto)
        self.assertIsNotNone(espessura, "não achou a camada de óxido na saída")
        self.assertTrue(0.01 < espessura < 2.0, f"Xo implausível: {espessura}")


if __name__ == "__main__":
    unittest.main()
