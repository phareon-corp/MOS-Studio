"""Ajuste Deal-Grove."""

from __future__ import annotations

import unittest

from mos_studio.core import oxidation

from . import legacy

# Espessuras de uma varredura real de oxidação úmida a 1000 °C.
TEMPOS = [20, 40, 70, 80, 100, 120]
XO = [0.1654, 0.2778, 0.4093, 0.4473, 0.5175, 0.5814]


class TestAjuste(unittest.TestCase):
    def setUp(self):
        self.fit = oxidation.deal_grove_fit(TEMPOS, XO)

    def test_coeficientes(self):
        self.assertAlmostEqual(self.fit["B_h"], 0.2920, places=4)
        self.assertAlmostEqual(self.fit["A"], 0.4230, places=4)
        self.assertAlmostEqual(self.fit["BA_h"], 0.6903, places=4)

    def test_qualidade_do_ajuste(self):
        self.assertGreater(self.fit["r2"], 0.999)

    def test_reta_t_sobre_xo(self):
        self.assertAlmostEqual(self.fit["m"], 205.477, places=2)   # 1/B
        self.assertAlmostEqual(self.fit["c"], 86.923, places=2)    # A/B

    def test_modelo_reproduz_os_pontos(self):
        for t, x in zip(TEMPOS, XO):
            with self.subTest(tempo=t):
                previsto = oxidation.deal_grove_xo(t, self.fit["A"],
                                                   self.fit["B_min"])
                self.assertAlmostEqual(previsto, x, places=3)

    def test_regime_parabolico_cresce_com_raiz_do_tempo(self):
        """Para Xo ≫ A o modelo vira Xo ≈ √(B·t): quadruplicar t dobra Xo."""
        a, b = self.fit["A"], self.fit["B_min"]
        x1 = oxidation.deal_grove_xo(1e8, a, b)
        x4 = oxidation.deal_grove_xo(4e8, a, b)
        self.assertAlmostEqual(x4 / x1, 2.0, places=2)

    def test_regime_linear_cresce_com_o_tempo(self):
        """Para Xo ≪ A o modelo vira Xo ≈ (B/A)·t: dobrar t dobra Xo."""
        a, b = self.fit["A"], self.fit["B_min"]
        x1 = oxidation.deal_grove_xo(0.05, a, b)
        x2 = oxidation.deal_grove_xo(0.10, a, b)
        self.assertAlmostEqual(x2 / x1, 2.0, places=2)


@unittest.skipUnless(legacy.available(), "suprem3.py não está no repositório")
class TestParidadeComOLegado(unittest.TestCase):
    def test_mesmos_numeros_da_versao_anterior(self):
        ns = legacy.namespace()
        self.assertEqual(ns["deal_grove_fit"](TEMPOS, XO),
                         oxidation.deal_grove_fit(TEMPOS, XO))
        fit = oxidation.deal_grove_fit(TEMPOS, XO)
        self.assertEqual(ns["deal_grove_xo"](40, fit["A"], fit["B_min"]),
                         oxidation.deal_grove_xo(40, fit["A"], fit["B_min"]))


if __name__ == "__main__":
    unittest.main()
