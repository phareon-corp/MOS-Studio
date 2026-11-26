"""Testes do MOSIM, o motor de dispositivo aberto compatível com o MINIMOS.

Os valores de referência marcados "MINIMOS" foram obtidos rodando o MINIMOS
6.1 nos mesmos decks; servem de régua de compatibilidade. A comparação ao
vivo (``CompatibilidadeAoVivo``) só roda se o MINIMOS estiver instalado.
"""
import math
import unittest

import numpy as np

from mos_studio.mosim import deck as dk
from mos_studio.mosim import fisica, perfil
from mos_studio.mosim.executar import executar, pontos_polarizacao

LIMIAR = """TESTE DISPOSITIVO
DEVICE CHANNEL=N GATE=NPOLY TIN=20E-7 L=10E-4 W=10E-4
BIAS UD=.1 US=0 UB=0
PROFILE NB=1E16 EL=P DOSE=5E15 AKEV=50 TOX=20E-7 TEMP=950 TIME=1800
IMPLANT EL=B DOSE=1E12 AKEV=20 TEMP=950 TIME=1800
INTERFACE NSS=1E11
OUTPUT NONE=YES
OPTION MODEL=THRES
END
"""


class Leitor(unittest.TestCase):
    def test_abreviacoes_continuacao_comentario(self):
        d = dk.ler("T\nDEV CH=N GA=AL TOX=5E-6 L=1E-4 * comentário\n+ W=1E-4\n"
                   "BIA UD=1 UG=2\nPRO NB=1E15 EL=P DO=1E15 AK=40 TE=1000 TI=900\nEND\n")
        dev = d.uma("DEVICE")
        self.assertEqual(dev.txt("CHANNEL"), "N")
        self.assertEqual(dev.num("TINS"), 5e-6)
        self.assertEqual(dev.num("W"), 1e-4)
        self.assertEqual(d.uma("PROFILE").txt("ELEM"), "P")

    def test_falta_end(self):
        with self.assertRaises(dk.ErroDeck):
            dk.ler("T\nDEVICE CHANNEL=N\n")


class Fisica(unittest.TestCase):
    def test_constantes_impressas_pelo_minimos(self):
        # INTRINSIC NUMBER e THERMAL VOLTAGE que o MINIMOS imprime
        self.assertAlmostEqual(fisica.intrinseca(300) / 8.78e9, 1, delta=1e-3)
        self.assertAlmostEqual(fisica.intrinseca(250) / 6.14e7, 1, delta=2e-3)
        self.assertAlmostEqual(fisica.intrinseca(350) / 3.25e11, 1, delta=2e-3)
        self.assertAlmostEqual(fisica.tensao_termica(300), 0.02585, places=5)
        self.assertAlmostEqual(fisica.Mobilidade(300).vsat / 9.99e6, 1, delta=1e-3)
        self.assertAlmostEqual(fisica.Mobilidade(250).vsat / 1.08e7, 1, delta=5e-3)  # impresso com 3 dígitos


class Perfil(unittest.TestCase):
    def test_gaussiana_sem_difusao(self):
        # As 100 keV: Rp = 0,0710 µm, ΔRp = 0,0243 µm (medidos no MINIMOS)
        rp, drp, _ = perfil.momentos("AS", 100)
        self.assertAlmostEqual(rp, 0.07102, places=4)
        self.assertAlmostEqual(drp, 0.02430, places=4)

    def test_dose_conservada_com_difusao(self):
        y = np.linspace(0, 3, 30001)
        c = perfil.vertical(y, 1e15, 0.05, 0.02, 0.1)
        # a cauda da gaussiana inicial acima da superfície (y < 0) se perde
        from scipy.special import erfc
        dentro = 1 - 0.5 * erfc(0.05 / (0.02 * math.sqrt(2)))
        self.assertAlmostEqual(np.trapezoid(c, y * 1e-4) / 1e15, dentro, delta=1e-4)

    def test_boro_acima_de_160_kev_recusado(self):
        with self.assertRaises(dk.ErroDeck):
            perfil.momentos("B", 200)


class Polarizacao(unittest.TestCase):
    def test_step_dreno_interno_porta_externa(self):
        d = dk.ler("T\nDEVICE CHANNEL=N GATE=AL TIN=5E-6 L=1E-3 W=1E-3\n"
                   "BIAS UD=0.1 UG=0\nSTEP DG=1 NG=1 DD=0.5 ND=1\nPROFILE NB=1E15\nEND\n")
        pts = [(p["G"], p["D"]) for p in pontos_polarizacao(d, "2")]
        self.assertEqual(pts, [(0, 0.1), (0, 0.6), (1, 0.1), (1, 0.6)])

    def test_step_de_porta_com_limiar_e_recusado(self):
        r = executar(LIMIAR.replace("OUTPUT", "STEP DG=0.1 NG=2\nOUTPUT"))
        self.assertEqual(r["returncode"], 1)
        self.assertIn("NUG-STEPS", r["out"])


class Limiar(unittest.TestCase):
    def test_limiar_de_canal_longo(self):
        r = executar(LIMIAR)
        self.assertEqual(r["returncode"], 0, r["out"][-500:])
        vth = r["pontos"][0]["VTH"]
        # MINIMOS 6.1 neste deck: 0,734 V (a tolerância do laço dele é 0,01 V)
        self.assertAlmostEqual(vth, 0.734, delta=0.02)
        self.assertIn("THRESHOLD VOLTAGE", r["out"])
        self.assertIn("THRESHOLD VOLTAGE", r["ref"])
        alvo = 1e-7  # W/L = 1
        self.assertAlmostEqual(r["pontos"][0]["ID"] / alvo, 1, delta=0.01)


def _minimos():
    try:
        from mos_studio.core import minimos
        d = minimos.find_dir()
        return d if d is not None and not minimos.check_engine(d) else None
    except Exception:  # noqa: BLE001
        return None


@unittest.skipUnless(_minimos(), "MINIMOS não instalado: comparação ao vivo pulada")
class CompatibilidadeAoVivo(unittest.TestCase):
    def test_limiar_igual_ao_minimos(self):
        import threading
        from mos_studio.core import minimos, parsers
        caixa, pronto = {}, threading.Event()
        minimos.run(LIMIAR, _minimos(), callback_done=lambda r: (caixa.update(r), pronto.set()),
                    callback_error=lambda e: (caixa.update(erro=e), pronto.set()))
        pronto.wait(120)
        v_mm = parsers.parse_minimos_vt(caixa.get("ref") or "")
        v_ab = executar(LIMIAR)["pontos"][0]["VTH"]
        self.assertIsNotNone(v_mm)
        self.assertLess(abs(v_ab - v_mm), 0.02)


if __name__ == "__main__":
    unittest.main()
