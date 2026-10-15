"""As telas que fecham a migração: Início, Dispositivo e Oxidação.

Aqui não se roda motor: o que se verifica é que as telas montam, que os
controles mexem no estado certo e que os números chegam formatados aos
lugares onde o usuário os lê.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    TEM_QT = True
except ImportError:                                  # pragma: no cover
    TEM_QT = False

from mos_studio.core import library, oxidation


@unittest.skipUnless(TEM_QT, "precisa de PySide6")
class BaseTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from mos_studio.ui import theme
        cls.app = QApplication.instance() or QApplication([])
        theme.apply(cls.app, "claro")


class TestInicio(BaseTela):
    def setUp(self):
        from mos_studio.ui.screens.inicio import HomeScreen
        self.tela = HomeScreen()

    def tearDown(self):
        self.tela.shutdown()
        self.tela.deleteLater()
        self.app.processEvents()

    def test_monta_e_mostra_a_biblioteca_inteira(self):
        self.assertEqual(set(self.tela._cards), {r.key for r in library.RECIPES})

    def test_cada_cartao_leva_a_uma_receita_existente(self):
        for chave in self.tela._cards:
            self.assertIs(library.get(chave), library.BY_KEY[chave])

    def test_emite_a_chave_da_receita_escolhida(self):
        recebidos: list[str] = []
        self.tela.new_project.connect(recebidos.append)
        self.tela.new_project.emit("poco-n")
        self.assertEqual(recebidos, ["poco-n"])

    def test_refresh_nao_explode_sem_execucoes(self):
        self.tela.refresh()


class TestDispositivo(BaseTela):
    def setUp(self):
        from mos_studio.ui.screens.dispositivo import DeviceScreen
        self.tela = DeviceScreen()

    def tearDown(self):
        self.tela.deleteLater()
        self.app.processEvents()

    def test_sem_processo_avisa_que_usa_os_padroes(self):
        self.assertIn("padrão", self.tela._ponte_corpo.findChildren(
            type(self.tela._aviso))[0].text().lower())

    def test_a_receita_define_o_canal(self):
        self.tela.set_process(library.get("fonte-dreno-nmos").steps, [])
        self.assertEqual(self.tela.params["channel"], "N")
        self.assertEqual(self.tela.params["gate"], "NPOLY")

    def test_o_deck_carrega_o_que_a_ponte_derivou(self):
        self.tela.set_process(library.get("fonte-dreno-nmos").steps, [])
        deck = self.tela.deck_text()
        self.assertIn("NB=1.00E+16", deck)
        self.assertIn("ELEM=AS", deck)
        self.assertIn("UG=", deck)

    def test_trocar_de_modo_esconde_a_varredura(self):
        self.tela._on_param("mode", "vth")
        self.assertFalse(self.tela._seg_var.isVisible())
        self.assertIn("MODEL=THRES", self.tela.deck_text())
        self.tela._on_param("mode", "iv")
        self.assertIn("MODEL=2-D", self.tela.deck_text())

    def test_modo_de_mapas_pede_o_pif(self):
        self.tela._on_param("mode", "op")
        self.assertIn("PIF=YES", self.tela.deck_text())

    def test_a_juncao_do_suprem_aparece_na_metrica(self):
        perfil = [(i * 0.05, 1e18 if i < 6 else -1e16) for i in range(20)]
        self.tela.set_process(library.get("fonte-dreno-nmos").steps, perfil)
        self.assertNotEqual(self.tela._metricas["xj"].text(), "—")

    def test_traducao_das_falhas_conhecidas_do_motor(self):
        self.assertIn("memória", self.tela._diagnose(
            "Program received signal SIGSEGV").lower())
        self.assertIn("contatos", self.tela._diagnose(
            "SOURCE REGION NOT FOUND").lower())
        self.assertTrue(self.tela._diagnose("qualquer outra coisa").strip())

    def test_mapas_vazios_nao_derrubam_a_tela(self):
        self.tela._fill_maps("")
        self.assertFalse(self.tela.mapa.has_data())

    def test_curva_sai_das_colunas_do_arquivo_iv(self):
        headers = ["UB", "UD", "UG", "US", "IB", "ID", "IG", "IS"]
        rows = [(0, 0.1, g * 0.15, 0, 0, g * 1e-6, 0, -g * 1e-6)
                for g in range(5)]
        self.tela.params["step_var"] = "DG"
        self.tela._fill_iv(headers, rows)
        self.assertTrue(self.tela.iv.has_data())
        self.assertNotEqual(self.tela._metricas["id"].text(), "—")


class TestOxidacao(BaseTela):
    def setUp(self):
        from mos_studio.ui.screens.oxidacao import OxidationScreen
        self.tela = OxidationScreen()
        self.tela.show()           # painéis só ficam visíveis dentro de uma tela

    def tearDown(self):
        self.tela.deleteLater()
        self.app.processEvents()

    def test_le_os_tempos_escritos(self):
        self.tela.params["times"] = "10, 30; 60,  120"
        self.assertEqual(self.tela.times(), [10.0, 30.0, 60.0, 120.0])

    def test_aceita_virgula_decimal_e_ignora_lixo(self):
        """Vírgula entre dígitos é decimal; vírgula com espaço separa."""
        self.tela.params["times"] = "0,5, 2, abc, -3, 0"
        self.assertEqual(self.tela.times(), [0.5, 2.0])

    def test_separadores_misturados(self):
        self.tela.params["times"] = "10; 30  60, 120"
        self.assertEqual(self.tela.times(), [10.0, 30.0, 60.0, 120.0])

    def test_virgula_sem_espaco_entre_digitos_e_decimal(self):
        """``60,120`` é um tempo (60,12 min), não dois — é a regra do campo."""
        self.tela.params["times"] = "10, 60,120"
        self.assertEqual(self.tela.times(), [10.0, 60.12])

    def test_literatura_acompanha_o_ambiente(self):
        self.tela._on_param("ambient", "DRYO2")
        self.tela._on_param("temperature", "1100")
        self.assertIn("DRYO2", self.tela._lit.text())
        self.assertIn("1100", self.tela._lit.text())

    def test_poucos_tempos_viram_recado_nao_corrida(self):
        self.tela.params["times"] = "10"
        self.tela._start()
        self.assertIsNone(self.tela._worker)
        self.assertTrue(self.tela.erro.isVisible())

    def test_metricas_saem_do_ajuste(self):
        """O ajuste de um Deal-Grove sintético precisa fechar em R² = 1."""
        A, B = 0.4, 0.3 / 60.0
        tempos = [10.0, 30.0, 60.0, 120.0]
        pontos = [oxidation.OxidationPoint(
            time_min=t, thickness_um=oxidation.deal_grove_xo(t, A, B))
            for t in tempos]
        s = oxidation.OxidationSweep(points=pontos)
        s.fit = oxidation.deal_grove_fit([p.time_min for p in pontos],
                                         [p.thickness_um for p in pontos])
        self.tela._on_done(s)
        self.assertAlmostEqual(s.fit["A"], A, places=5)
        self.assertAlmostEqual(s.fit["r2"], 1.0, places=6)
        self.assertNotEqual(self.tela._metricas["A"][0].text(), "—")
        self.assertTrue(self.tela.chart._pontos)

    def test_csv_tras_cabecalho_e_uma_linha_por_tempo(self):
        pontos = [oxidation.OxidationPoint(time_min=10.0, thickness_um=0.1),
                  oxidation.OxidationPoint(time_min=20.0, error="falhou")]
        self.tela.sweep = oxidation.OxidationSweep(points=pontos)
        linhas = self.tela.report_text().strip().split("\n")
        self.assertTrue(linhas[0].startswith("tempo_min"))
        self.assertEqual(len(linhas), 3)
        self.assertIn("falhou", linhas[2])


if __name__ == "__main__":
    unittest.main()
