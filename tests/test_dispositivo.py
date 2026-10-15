"""A tela de Dispositivo: mapas, deck editável e arquivos trazidos de fora.

Os testes que sobem o MINIMOS estão em :class:`TestContraOMotor` e são
pulados quando ele não está instalado.
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


def tem_minimos() -> bool:
    from mos_studio.core import minimos

    mdir = minimos.find_dir()
    return mdir is not None and not minimos.check_engine(mdir)


@unittest.skipUnless(TEM_QT, "PySide6 não está instalado")
class BaseUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from mos_studio.ui import theme
        theme.apply(cls.app, "claro")

    def setUp(self):
        from mos_studio.ui.main_window import MainWindow
        self.janela = MainWindow()
        self.janela.show()
        self.app.processEvents()
        self.tela = self.janela.dispositivo

    def tearDown(self):
        self.janela.close()
        self.janela.deleteLater()
        self.app.processEvents()


class TestEscalaDoMapa(BaseUI):
    """A escala de cor dos mapas 2-D.

    A anterior ia de ``nfill`` a ``accent``, que têm o **mesmo** RGB (o
    primeiro é o segundo com alfa 77) — e a interpolação descarta o alfa. O
    mapa inteiro saía de uma cor só: um retângulo laranja chapado.
    """

    def test_os_polos_sao_cores_diferentes(self):
        from mos_studio.ui import theme

        neg = theme.qcolor("field-neg")
        pos = theme.qcolor("field-pos")
        self.assertNotEqual(neg.name(), pos.name())

    def test_a_escala_divergente_varia(self):
        from mos_studio.ui.widgets.device_plots import cor_divergente

        cores = {cor_divergente(t).name()
                 for t in (-1.0, -0.5, 0.0, 0.5, 1.0)}
        self.assertEqual(len(cores), 5)

    def test_o_meio_e_neutro(self):
        """Nunca uma matiz no meio de uma escala divergente."""
        from mos_studio.ui import theme
        from mos_studio.ui.widgets.device_plots import cor_divergente

        meio = cor_divergente(0.0)
        self.assertEqual(meio.name(), theme.qcolor("field-mid").name())

    def test_campo_com_sinal_usa_escala_simetrica(self):
        mapa = self.tela.mapa
        mapa.set_field([0.0, 1.0, 2.0], [0.0, 1.0],
                       [-10.0, 0.0, 5.0, -2.0, 1.0, 3.0], "teste")
        lo, hi = mapa._escala()
        self.assertAlmostEqual(lo, -hi)
        self.assertTrue(mapa._divergente())

    def test_campo_so_positivo_usa_escala_sequencial(self):
        mapa = self.tela.mapa
        mapa.set_field([0.0, 1.0], [0.0, 1.0], [1.0, 2.0, 3.0, 4.0], "teste")
        self.assertFalse(mapa._divergente())
        lo, hi = mapa._escala()
        self.assertGreaterEqual(lo, 0.0)

    def test_o_mapa_desenha_sem_dados(self):
        from PySide6.QtGui import QPixmap

        self.tela.mapa.clear()
        self.tela.mapa.resize(400, 300)
        pm = QPixmap(self.tela.mapa.size())
        self.tela.mapa.render(pm)
        self.assertFalse(pm.isNull())


class TestSuperficie3D(BaseUI):
    """A superfície 3-D, que o app antigo desenhava com o matplotlib.

    Perdeu-se na migração para o PySide6; aqui a grade do PIF é projetada e
    pintada com QPainter, sem matplotlib.
    """

    def _campo(self, valores=None):
        """Uma grade pequena com relevo, para os testes de projeção."""
        lat = [0.0, 0.5, 1.0, 1.5]
        vert = [0.0, 0.3, 0.6]
        if valores is None:
            valores = [0.0, 1.0, 1.0, 0.0,
                       -1.0, 2.0, 2.0, -1.0,
                       -2.0, 0.5, 0.5, -2.0]
        self.tela.superficie.set_field(lat, vert, valores, "teste")
        return lat, vert, valores

    def test_a_aba_existe(self):
        nomes = [self.tela.abas.tabText(i)
                 for i in range(self.tela.abas.count())]
        self.assertIn("Superfície 3-D", nomes)

    def test_sem_dados_nao_quebra(self):
        from PySide6.QtGui import QPixmap

        sup = self.tela.superficie
        sup.clear()
        sup.resize(500, 300)
        self.assertFalse(sup.has_data())
        pm = QPixmap(sup.size())
        sup.render(pm)
        self.assertFalse(pm.isNull())

    def test_desenha_com_dados(self):
        from PySide6.QtGui import QPixmap

        self._campo()
        sup = self.tela.superficie
        sup.resize(600, 400)
        self.app.processEvents()
        self.assertTrue(sup.has_data())
        pm = QPixmap(sup.size())
        sup.render(pm)
        self.assertFalse(pm.isNull())

    def test_a_escala_e_simetrica_com_sinal(self):
        """Senão o zero do campo não cairia no neutro da cor."""
        self._campo()
        lo, hi = self.tela.superficie._escala()
        self.assertAlmostEqual(lo, -hi)

    def test_a_vista_gira_e_respeita_os_limites(self):
        sup = self.tela.superficie
        sup.set_view(120.0, 45.0)
        self.assertEqual(sup.view(), (120.0, 45.0))
        sup.set_view(0.0, 200.0)
        self.assertLessEqual(sup.view()[1], sup.MAX_ELEV)
        sup.set_view(0.0, -50.0)
        self.assertGreaterEqual(sup.view()[1], sup.MIN_ELEV)

    def test_o_azimute_da_a_volta(self):
        sup = self.tela.superficie
        sup.set_view(370.0, 30.0)
        self.assertAlmostEqual(sup.view()[0], 10.0)

    def test_restaurar_a_vista(self):
        sup = self.tela.superficie
        sup.set_view(200.0, 70.0)
        sup.reset_view()
        self.assertEqual(sup.view(), (35.0, 28.0))

    def test_uma_grade_grande_e_amostrada(self):
        """Mais de MAX_QUADS por eixo não melhora a leitura e custa caro."""
        sup = self.tela.superficie
        n = sup.MAX_QUADS * 3
        idx = sup._indices(n)
        self.assertLessEqual(len(idx) - 1, sup.MAX_QUADS + 1)
        self.assertEqual(idx[0], 0)
        self.assertEqual(idx[-1], n - 1)

    def test_uma_grade_pequena_passa_inteira(self):
        sup = self.tela.superficie
        self.assertEqual(sup._indices(5), [0, 1, 2, 3, 4])

    def test_o_campo_escolhido_vai_para_as_duas_vistas(self):
        """O mapa e a superfície mostram o mesmo dado."""
        self.tela._campos = {"Potencial (V)": [0.0, 1.0, 2.0, 3.0]}
        self.tela._lat, self.tela._vert = [0.0, 1.0], [0.0, 1.0]
        self.tela._show_field("Potencial (V)")
        self.assertTrue(self.tela.mapa.has_data())
        self.assertTrue(self.tela.superficie.has_data())

    def test_campo_vazio_limpa_as_duas(self):
        self.tela._campos = {}
        self.tela._show_field("nao.existe")
        self.assertFalse(self.tela.mapa.has_data())
        self.assertFalse(self.tela.superficie.has_data())


class TestDeckEditavel(BaseUI):
    """Dá para mudar o que o MINIMOS simula, sem passar pelos campos."""

    def test_comeca_gerado_dos_campos(self):
        self.assertFalse(self.tela.manual_deck())
        self.assertIn("DEVICE", self.tela.deck_text())

    def test_entrar_e_sair_do_modo_manual(self):
        self.tela._start_manual_deck()
        self.assertTrue(self.tela.manual_deck())
        self.tela._discard_manual_deck()
        self.assertFalse(self.tela.manual_deck())

    def test_o_deck_manual_e_o_que_vai_ao_motor(self):
        self.tela.load_deck("* meu\nDEVICE CHANNEL=P\nEND\n", "meu.inp")
        self.assertTrue(self.tela.manual_deck())
        self.assertIn("CHANNEL=P", self.tela.deck_text())

    def test_os_campos_nao_sobrescrevem_o_deck_manual(self):
        self.tela.load_deck("* meu\nDEVICE CHANNEL=P\nEND\n", "meu.inp")
        self.tela._on_param("tox_nm", "40")
        self.assertIn("CHANNEL=P", self.tela.deck_text())
        self.assertNotIn("TOX=4", self.tela.deck_text())

    def test_abrir_um_deck_mostra_a_aba_dele(self):
        self.tela.load_deck("* meu\nEND\n", "meu.inp")
        self.assertEqual(self.tela.abas.tabText(self.tela.abas.currentIndex()),
                         "Deck .inp")

    def test_o_rodape_diz_de_onde_veio_o_deck(self):
        self.tela.load_deck("* meu\nEND\n", "exemplo.inp")
        self.assertIn("exemplo.inp", self.tela._aviso.text())

    def test_descartar_volta_aos_campos(self):
        self.tela.load_deck("* meu\nDEVICE CHANNEL=P\nEND\n", "meu.inp")
        self.tela._discard_manual_deck()
        self.assertIn("DEVICE", self.tela.deck_text())
        self.assertNotIn("CHANNEL=P", self.tela.deck_text())


class TestAbrirResultado(BaseUI):
    """Ver uma execução do MINIMOS sem rodar o motor."""

    def _escrever(self, nome: str, texto: str):
        import tempfile
        from pathlib import Path

        pasta = Path(tempfile.mkdtemp(prefix="mm_res_"))
        alvo = pasta / nome
        alvo.write_text(texto, encoding="ascii")
        return alvo

    def test_arquivo_sem_nada_util_explica(self):
        """Um arquivo que não é PIF nem curva recebe explicação, não silêncio."""
        from unittest import mock

        alvo = self._escrever("fort.99", "lixo\n")
        with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName",
                        return_value=(str(alvo), "")):
            self.tela.import_result()
        self.app.processEvents()
        self.assertFalse(self.tela.mapa.has_data())
        self.assertIn(alvo.name, self.tela.erro.raw)

    def test_abrir_um_arquivo_de_curva(self):
        from unittest import mock

        curva = ("  UG       UD       ID\n"
                 " 0.00E+00 1.00E-01 1.00E-12\n"
                 " 1.00E+00 1.00E-01 2.00E-06\n")
        alvo = self._escrever("fort.61", curva)
        with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName",
                        return_value=(str(alvo), "")):
            self.tela.import_result()
        self.app.processEvents()
        self.assertIsNotNone(self.tela.result)
        self.assertIn("fort.61", self.tela._andamento.text())

    @unittest.skipUnless(tem_minimos(), "MINIMOS não está instalado")
    def test_abre_um_pif_de_verdade(self):
        """Roda uma vez, guarda o PIF e reabre do disco."""
        import threading
        from pathlib import Path
        from mos_studio.core import minimos

        mdir = minimos.find_dir()
        deck = minimos.build_deck({"mode": "op", "ud": "0.1", "ug": "2.0"})
        pronto, ev = {}, threading.Event()
        minimos.run(deck, mdir,
                    callback_done=lambda r: (pronto.update(r), ev.set()),
                    callback_error=lambda e: (pronto.update(err=e), ev.set()))
        ev.wait(900)
        self.assertTrue(pronto.get("pif"), "o MINIMOS não gerou o PIF")

        alvo = self._escrever("fort.30", pronto["pif"])
        caixa = {"pif": alvo.read_text(encoding="latin1"), "iv": None,
                 "ref": None, "out": None, "returncode": 0,
                 "stages": [], "files": [alvo.name]}
        self.tela._on_done(caixa)
        self.app.processEvents()
        self.assertTrue(self.tela.mapa.has_data())
        self.assertEqual(
            self.tela.abas.tabText(self.tela.abas.currentIndex()),
            "Mapas 2-D")


@unittest.skipUnless(tem_minimos(), "MINIMOS não está instalado")
class TestContraOMotor(BaseUI):
    def _rodar(self, modo: str, ms: int = 900000) -> dict:
        from PySide6.QtCore import QEventLoop, QTimer

        self.tela.params["mode"] = modo
        self.tela._update_mode_visibility()
        self.tela._refresh_deck()
        laco = QEventLoop()
        self.tela.run_finished.connect(lambda _r: laco.quit())
        QTimer.singleShot(ms, laco.quit)
        self.tela.run()
        laco.exec()
        for _ in range(4):
            self.app.processEvents()
        return self.tela.result or {}

    def test_o_modo_de_mapas_pede_o_pif(self):
        """Sem ``PIF=YES`` o motor não grava o fort.30 e não há o que mostrar."""
        from mos_studio.core import minimos

        deck = minimos.build_deck({"mode": "op"})
        self.assertIn("PIF=YES", deck)

    def test_roda_e_mostra_os_mapas(self):
        caixa = self._rodar("op")
        self.assertTrue(caixa.get("pif"), "o MINIMOS não gerou o PIF")
        self.assertTrue(self.tela.mapa.has_data())

    def test_termina_na_aba_dos_mapas(self):
        """Terminar na aba da curva deixava o usuário com um gráfico de um
        ponto só, convencido de que não saiu nada."""
        self._rodar("op")
        self.assertEqual(
            self.tela.abas.tabText(self.tela.abas.currentIndex()),
            "Mapas 2-D")

    def test_o_mapa_tem_os_quatro_campos(self):
        from mos_studio.core import parsers

        caixa = self._rodar("op")
        _lat, _vert, campos = parsers.parse_minimos_pif(caixa.get("pif") or "")
        self.assertEqual(len(campos), 4)

    def test_o_potencial_tem_os_dois_sinais(self):
        """É o que justifica a escala divergente."""
        from mos_studio.core import parsers

        caixa = self._rodar("op")
        _lat, _vert, campos = parsers.parse_minimos_pif(caixa.get("pif") or "")
        pot = next(v for k, v in campos.items() if "Potencial" in k)
        self.assertLess(min(pot), 0.0)
        self.assertGreater(max(pot), 0.0)

    def test_a_faixa_assina_o_minimos(self):
        self._rodar("op")
        self.assertIn("MINIMOS", self.janela.strip._engine.text())

    def test_a_superficie_recebe_os_dados_da_corrida(self):
        self._rodar("op")
        self.assertTrue(self.tela.superficie.has_data())

    def test_a_superficie_desenha_todos_os_campos(self):
        from PySide6.QtGui import QPixmap

        self._rodar("op")
        self.tela.superficie.resize(600, 400)
        for nome in self.tela._campos:
            self.tela._show_field(nome)
            self.app.processEvents()
            pm = QPixmap(self.tela.superficie.size())
            self.tela.superficie.render(pm)
            self.assertFalse(pm.isNull(), nome)


if __name__ == "__main__":
    unittest.main()
