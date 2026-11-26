"""Testes dos modelos do MOSIM além do 2-D: malha adaptativa, AVAL, transiente,
SOI, perfis de arquivo, pré-deposição, perfil assimétrico e a ponte direta.

As referências "MINIMOS" foram obtidas rodando o MINIMOS 6.1 nos mesmos decks
(minimos-run/examples); as tolerâncias são as medidas no ADR 0005.
"""
import math
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mos_studio.mosim import malha, perfil, simular, transiente
from mos_studio.mosim.deck import ler
from mos_studio.mosim.executar import executar

EXA2D = """* EXAMPLE FOR CLASSICAL TWO-DIMENSIONAL MODEL
DEVICE     CHANNEL=N  GATE=NPOLY  TOX=150.E-8  W=1.E-4  L=0.85E-4
BIAS       UD=4. UG=1.5
PROFILE    NB=5.2E16  ELEM=AS  DOSE=2.E15  TOX=500.E-8  AKEV=160.
+          TEMP=1050.  TIME=2700
IMPLANT    ELEM=B  DOSE=1.E12  AKEV=12  TEMP=940  TIME=1000
OPTION     MODEL={modelo}
OUTPUT     ALL=YES
END
"""

DECK_SOI = """* EXAMPLE FOR SOI TRANSISTOR
DEVICE     CHANNEL=N  GATE=NPOLY  TOX=27.5E-7  W=50.0E-4  L=1.0E-4
+          FILM=0.15E-4 BULK=500E-7 KBULK=3.9
BIAS       US=0 UD=1.8 UG=0.8
PROFILE    NB=4.0E16 ELEM=P  DOSE=5.E15 AKEV=90.
+          TEMP=945  TIME=2000 TOX=27.5E-7
PROFILE    XOFF=0.15E-4  ELEM=AS  DOSE=5.E15  AKEV=180.
IMPLANT    ELE=B  DOSE=2E11   AKEV=20.  TEMP=575.  TIME=7200.
OPTION     MODEL={modelo} TEMP=300
RECOMB     TN=0.5E-6 TP=0.5E-6
OUTPUT     NONE=YES
END        BIN=NO
"""

#: Referências do MINIMOS 6.1 (mesmos decks).
MINIMOS = {
    "exa2d_ID": 4.711e-5, "exavl_ID": 4.912e-5, "exavl_IB": -5.484e-8,
    "exsoi_ID_2D": 6.83e-5, "exsoi_ID_AVAL": 8.934e-5,
}


def corrente(r, chave="DRAIN CURRENT"):
    return float(re.findall(chave + r"\s*=\s*([-0-9.E+]+)", r["out"])[-1])


class MalhaAdaptativa(unittest.TestCase):
    def test_malha_inicial_igual_a_do_minimos_nos_contatos(self):
        m = simular.construir(ler(EXA2D.format(modelo="2-D")))
        xs, ys = m.malha0
        # extremos e passos áureos idênticos aos da malha final do MINIMOS no exa2d
        self.assertAlmostEqual(xs[0], -0.9068, places=3)
        self.assertAlmostEqual(xs[-1], 1.7568, places=3)
        self.assertTrue(np.any(np.isclose(xs, -0.2714, atol=1e-3)))
        # y no silício: a sequência fixa do MINIMOS (nm)
        si = [v * 1e3 for v in ys if v >= 0][:6]
        np.testing.assert_allclose(si, [0.0, 1.618, 2.80, 4.72, 6.63, 9.74], atol=0.02)

    def test_refinar_divide_ao_meio_e_suaviza(self):
        v = np.array([0.0, 1.0, 2.0, 10.0])
        novo = malha.refinar(v, np.array([2.0, 0.5, 0.5]), pgmi=1e-4)
        self.assertIn(0.5, novo)
        h = np.diff(novo)
        self.assertTrue(np.all(h[1:] <= malha.PHI ** 2 * 1.02 * h[:-1]))
        self.assertTrue(np.all(h[:-1] <= malha.PHI ** 2 * 1.02 * h[1:]))

    def test_canal_curto_como_o_minimos(self):
        r = executar(EXA2D.format(modelo="2-D"))
        self.assertEqual(r["returncode"], 0)
        self.assertAlmostEqual(corrente(r) / MINIMOS["exa2d_ID"], 1.0, delta=0.03)


class Avalanche(unittest.TestCase):
    def test_corrente_de_substrato(self):
        r = executar(EXA2D.format(modelo="AVAL"))
        self.assertEqual(r["returncode"], 0)
        self.assertAlmostEqual(corrente(r) / MINIMOS["exavl_ID"], 1.0, delta=0.06)
        ib = corrente(r, "BULK CURRENT")
        self.assertLess(ib, 0.0)
        self.assertAlmostEqual(ib / MINIMOS["exavl_IB"], 1.0, delta=0.25)
        # o .iv do AVAL traz IB e IS
        linha = [l for l in r["iv"].splitlines() if not l.startswith("#")][0].split()
        self.assertAlmostEqual(float(linha[4]), ib, delta=abs(ib) * 0.01)


class Transiente(unittest.TestCase):
    DECK = """* EXAMPLE FOR TRANSIENT SIMULATION
DEVICE     CHANNEL=N  GATE=NPOLY TOX=1.5E-6  W=1.E-4  L=0.8E-4
BIAS       UG=5 UD=0.
TRANS      TG1=10.E-6  TG2=1.E-6 TG3=1.E-6 TG4=1.E-6 TG5=1.E-6
+          TG6=4.E-6 TG7={fim} WG=3
+          UG2=10.0 UG3=0 UG4=0.5 UG5=1 UG6=2
PROFILE    NB=2E16  ELEM=AS  DOSE=2.E15  TOX=500.E-8  AKEV=160.
+          TEMP=1050.  TIME=2700
IMPLANT    ELEM=B  DOSE=1.E12  AKEV=12  TEMP=940  TIME=1000
OPTION     MODEL=AVL PHYSCHK=NO
OUTPUT     NONE=YES
END        BIN=N
"""

    def test_passos_de_tempo_iguais_aos_do_minimos(self):
        d = ler(self.DECK.format(fim="10.E-6"))
        o, fim, _ = transiente.ondas(d, {"S": 0.0, "D": 0.0, "G": 5.0, "B": 0.0})
        ts = [round(t * 1e6, 4) for t in transiente.instantes(o, fim)]
        # o .tra do MINIMOS no extra.inp
        esperado = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.475, 1.8125,
                    2, 2.2, 2.4, 2.6, 2.8, 3, 3.2, 3.5, 3.95, 4.625, 5, 5.2, 5.4, 5.6, 5.8, 6,
                    6.2, 6.5, 6.95, 7.625, 8.6375, 10]
        self.assertEqual(len(ts), len(esperado))
        np.testing.assert_allclose(ts, esperado, atol=1e-3)

    def test_rampa_de_porta(self):
        r = executar(self.DECK.format(fim="0.3E-6"))
        self.assertEqual(r["returncode"], 0)
        linhas = [l.split() for l in r["tra"].splitlines()[1:]]
        # MINIMOS a 0,1-0,3 µs: IG = -1,01e-8 A e ID = IS = 5,07e-9 A
        for l in linhas[1:]:
            self.assertAlmostEqual(float(l[6]) / -1.01e-8, 1.0, delta=0.05)
            self.assertAlmostEqual(float(l[4]) / 5.06e-9, 1.0, delta=0.05)
        # carga conservada: a soma dos terminais é ~0
        for l in linhas[1:]:
            soma = sum(float(l[k]) for k in (2, 4, 6, 8))
            # o .tra tem 3 dígitos: a soma fecha dentro do arredondamento
            self.assertLess(abs(soma), 1e-2 * abs(float(l[6])))


class SOI(unittest.TestCase):
    def test_corpo_flutuante(self):
        r2 = executar(DECK_SOI.format(modelo="2-D"))
        ra = executar(DECK_SOI.format(modelo="AVAL"))
        i2, ia = corrente(r2), corrente(ra)
        self.assertAlmostEqual(i2 / MINIMOS["exsoi_ID_2D"], 1.0, delta=0.08)
        self.assertAlmostEqual(ia / MINIMOS["exsoi_ID_AVAL"], 1.0, delta=0.12)
        # o efeito de corpo flutuante: as lacunas da avalanche aumentam a corrente
        self.assertGreater(ia, 1.15 * i2)


class PerfisExternos(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="mosim_teste_"))

    def test_arquivo_2d_reproduz_o_perfil_analitico(self):
        txt = EXA2D.format(modelo="2-D")
        m = simular.construir(ler(txt))
        pl = np.concatenate([np.linspace(-2.0, -0.4, 9), np.linspace(-0.38, 0.425, 60)])
        pv = np.concatenate([np.linspace(0, 0.05, 26), np.linspace(0.05, 0.6, 56),
                             np.linspace(0.6, 3.0, 13)])
        arq = self.dir / "p.bin"
        perfil.exportar_2d(arq, m.perfil.liquida, m.perfil.total, m.L * 1e4, pl, pv)
        tab = perfil.ler_arquivo_2d(arq, m.L * 1e4)
        for x, y in ((-0.5, 0.1), (0.1, 0.01), (0.4, 0.5), (0.8, 0.2)):
            a, b = float(m.perfil.liquida(x, y)), float(tab.liquida(x, y))
            self.assertAlmostEqual(b / a, 1.0, delta=0.05, msg=f"({x}, {y})")

    def test_ponte_direta_com_o_suprem(self):
        from mos_studio.core import bridge
        txt = EXA2D.format(modelo="2-D")
        m = simular.construir(ler(txt))
        y = np.concatenate([np.linspace(0, 0.1, 51), np.linspace(0.1, 2.0, 96)])
        prof = list(zip(y, m.perfil.liquida(np.full_like(y, m.L * 1e4 / 2), y)))
        arq = self.dir / "ponte.bin"
        d2 = bridge.deck_com_perfil(txt, prof, arq)
        self.assertIn("FILE=2-D", d2)
        self.assertNotIn("IMPLANT", d2)
        r1, r2 = executar(txt), executar(d2, dopfile=arq)
        self.assertEqual(r2["returncode"], 0)
        self.assertAlmostEqual(corrente(r2) / corrente(r1), 1.0, delta=0.02)

    def test_predeposicao(self):
        txt = ("T\nDEVICE CHANNEL=N GATE=NPOLY TINS=20E-7 L=2E-4 W=10E-4\nBIAS UD=0.1 UG=2\n"
               "PROFILE NB=1E16 NS=1E20 TEMP=1000 TIME=1800\nOPTION MODEL=2-D\nEND\n")
        m = simular.construir(ler(txt))
        self.assertAlmostEqual(float(m.perfil.liquida(-2.0, 0.0)) / 1e20, 1.0, delta=0.01)
        self.assertGreater(m.xj, 0.05)

    def test_perfil_assimetrico(self):
        txt = ("T\nDEVICE CHANNEL=N GATE=NPOLY TINS=20E-7 L=2E-4 W=10E-4\nBIAS UD=0.1 UG=2\n"
               "PROFILE NB=1E16 ELEM=AS DOSE=1E15 AKEV=50 TEMP=1000 TIME=900 ASYM=YES\n"
               "PROFILE ELEM=P DOSE=1E14 AKEV=50\nOPTION MODEL=2-D\nEND\n")
        m = simular.construir(ler(txt))
        fonte, dreno = float(m.perfil.liquida(-1.0, 0.02)), float(m.perfil.liquida(3.0, 0.02))
        self.assertGreater(fonte, 5 * dreno)     # dose de fonte 10× a do dreno


if __name__ == "__main__":
    unittest.main()
