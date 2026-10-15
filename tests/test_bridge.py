"""A ponte SUPREM → MINIMOS: o que ela deriva e o que ela não promete."""

from __future__ import annotations

import unittest

from mos_studio.core import bridge, library, minimos


class TestNormalizacao(unittest.TestCase):
    """As três formas de passo que circulam no app viram a mesma coisa."""

    def test_aceita_tupla_dict_e_step(self):
        from mos_studio.core.recipe import Step
        tupla = ("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"})
        como_dict = {"type": "INITIALIZE",
                     "params": {"dopant": "BORON", "concentration": "1E15"}}
        como_step = Step("INITIALIZE", {"dopant": "BORON",
                                        "concentration": "1E15"})
        derivadas = [bridge.derive([forma])
                     for forma in (tupla, como_dict, como_step)]
        for d in derivadas:
            self.assertEqual(d.channel, "N")
            self.assertAlmostEqual(d.nb, 1e15)


class TestDerivacao(unittest.TestCase):

    def test_substrato_p_da_canal_n(self):
        passos = [("INITIALIZE", {"dopant": "BORON",
                                  "concentration": "2E16"})]
        b = bridge.derive(passos)
        self.assertEqual(b.channel, "N")
        self.assertEqual(b.origem["channel"], "substrato da receita")

    def test_substrato_n_da_canal_p(self):
        passos = [("INITIALIZE", {"dopant": "PHOSPHORUS",
                                  "concentration": "2E16"})]
        self.assertEqual(bridge.derive(passos).channel, "P")

    def test_perfil_manda_na_dopagem_de_substrato(self):
        """A cauda do perfil medido vence o valor escrito na receita."""
        passos = [("INITIALIZE", {"dopant": "BORON",
                                  "concentration": "1E15"})]
        perfil = [(0.0, 1e20), (0.5, 1e18), (1.0, -3e16), (1.5, -3e16),
                  (2.0, -3e16), (2.5, -3e16), (3.0, -3e16)]
        b = bridge.derive(passos, perfil)
        self.assertAlmostEqual(b.nb, 3e16, delta=1e14)
        self.assertEqual(b.origem["nb"], "cauda do perfil do SUPREM")

    def test_escolhe_o_implante_de_tipo_oposto_mais_pesado(self):
        passos = [("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
                  ("IMPLANTI", {"dopant": "ARSENIC", "dose": "2E15",
                                "energy": "80"}),
                  ("IMPLANTI", {"dopant": "PHOSPHORUS", "dose": "1E14",
                                "energy": "40"})]
        b = bridge.derive(passos)
        self.assertEqual(b.sd_elem, "AS")
        self.assertAlmostEqual(b.sd_dose, 2e15)
        self.assertAlmostEqual(b.sd_akev, 80.0)

    def test_implante_leve_do_tipo_do_substrato_vira_ajuste_de_limiar(self):
        passos = [("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
                  ("IMPLANTI", {"dopant": "BORON", "dose": "1E12",
                                "energy": "12"}),
                  ("IMPLANTI", {"dopant": "ARSENIC", "dose": "2E15",
                                "energy": "80"})]
        b = bridge.derive(passos)
        self.assertAlmostEqual(b.vt_dose, 1e12)
        self.assertEqual(b.vt_elem, "B")

    def test_recozimento_vem_em_segundos(self):
        """A receita dá minutos; o card PROFILE do MINIMOS quer segundos."""
        passos = [("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
                  ("IMPLANTI", {"dopant": "ARSENIC", "dose": "2E15",
                                "energy": "80"}),
                  ("DIFFUSION", {"ambient": "NITROGEN", "temperature": "1000",
                                 "time": "30"})]
        b = bridge.derive(passos)
        self.assertAlmostEqual(b.anneal_s, 1800.0)
        self.assertAlmostEqual(b.anneal_c, 1000.0)

    def test_difusao_antes_do_implante_nao_conta_como_recozimento(self):
        passos = [("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
                  ("DIFFUSION", {"ambient": "DRYO2", "temperature": "900",
                                 "time": "999"}),
                  ("IMPLANTI", {"dopant": "ARSENIC", "dose": "2E15",
                                "energy": "80"}),
                  ("DIFFUSION", {"ambient": "NITROGEN", "temperature": "1050",
                                 "time": "20"})]
        b = bridge.derive(passos)
        self.assertAlmostEqual(b.anneal_c, 1050.0)
        self.assertAlmostEqual(b.anneal_s, 1200.0)

    def test_junção_do_perfil_entra_na_ponte(self):
        perfil = [(i * 0.05, 1e18 if i < 6 else -1e16) for i in range(20)]
        b = bridge.derive([], perfil)
        self.assertGreater(b.xj_suprem, 0.0)

    def test_sem_receita_usa_os_padroes_do_motor(self):
        b = bridge.derive([])
        self.assertAlmostEqual(b.nb, bridge.PADRAO["nb"])
        self.assertEqual(b.origem, {})

    def test_o_aviso_nao_promete_transporte_do_perfil(self):
        b = bridge.derive(library.get("fonte-dreno-nmos").steps)
        self.assertIn("não", b.aviso.lower())
        self.assertIn("ponto a ponto", b.aviso)


class TestDeckDerivado(unittest.TestCase):
    """O deck que sai da ponte precisa evitar as armadilhas desta compilação."""

    def _deck(self, **extra):
        b = bridge.derive(library.get("fonte-dreno-nmos").steps)
        p = dict(b.as_params())
        p.update(mode="iv", tox_nm=15, w_um=1.0, l_um=0.85, auto_sign=False)
        p.update(extra)
        return minimos.build_deck(p)

    def test_sempre_emite_ug(self):
        """Sem UG o MODEL=2-D desta compilação morre com SIGSEGV."""
        for deck in (self._deck(), self._deck(ug=0), self._deck(ug=1.5)):
            linha = [ln for ln in deck.splitlines()
                     if ln.startswith("BIAS")][0]
            self.assertIn("UG=", linha)

    def test_nunca_emite_dreno_em_zero(self):
        deck = self._deck(ud=0.0)
        linha = [ln for ln in deck.splitlines() if ln.startswith("BIAS")][0]
        self.assertNotIn("UD=0 ", linha + " ")
        self.assertIn(f"UD={minimos.UD_MINIMO:g}", linha)

    def test_pmos_usa_o_card_analitico_nao_o_arquivo_2d(self):
        """``PROFILE FILE=2-D`` aborta neste motor; só sai se for pedido."""
        deck = self._deck(channel="P")
        self.assertNotIn("FILE=2-D", deck)
        self.assertIn("ELEM=", deck)

    def test_arquivo_2d_so_quando_explicitamente_pedido(self):
        self.assertIn("FILE=2-D", self._deck(dopfile=True))

    def test_varredura_de_porta_e_de_dreno_usam_as_palavras_do_motor(self):
        self.assertIn("DG=", self._deck(step_var="DG", step=0.15, nstep=20))
        self.assertIn("NG=", self._deck(step_var="DG", step=0.15, nstep=20))
        self.assertIn("DD=", self._deck(step_var="DD", step=0.5, nstep=8))
        self.assertIn("ND=", self._deck(step_var="DD", step=0.5, nstep=8))

    def test_modo_limiar_usa_thres(self):
        self.assertIn("MODEL=THRES", self._deck(mode="vth"))

    def test_modo_mapas_pede_pif(self):
        self.assertIn("PIF=YES", self._deck(mode="op", maps=True))


class TestAvisoDoQueFalta(unittest.TestCase):
    """A ponte diz quando um valor veio do padrão do motor, não da receita.

    Um corte de porta não tem fonte nem dreno. Sem o aviso, o MINIMOS
    simulava um transistor com fonte/dreno inventada e nada na tela dizia
    isso.
    """

    def _passos(self, *tipos_e_params):
        return [{"type": t, "params": p} for t, p in tipos_e_params]

    def test_avisa_quando_falta_fonte_e_dreno(self):
        passos = self._passos(
            ("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
            ("IMPLANTI", {"dopant": "BORON", "dose": "1E12", "energy": "40"}),
            ("DIFFUSION", {"temperature": "900", "time": "30"}))
        b = bridge.derive(passos, [])
        self.assertIn("fonte e dreno", b.aviso)
        self.assertNotIn("sd", b.origem)

    def test_nao_avisa_quando_a_receita_traz_tudo(self):
        passos = self._passos(
            ("INITIALIZE", {"dopant": "BORON", "concentration": "1E15"}),
            ("IMPLANTI", {"dopant": "BORON", "dose": "1E12", "energy": "40"}),
            ("IMPLANTI", {"dopant": "ARSENIC", "dose": "5E15", "energy": "80"}),
            ("DIFFUSION", {"temperature": "950", "time": "30"}))
        b = bridge.derive(passos, [])
        self.assertNotIn("padrões do motor", b.aviso)
        for chave in ("sd", "vt", "anneal"):
            self.assertIn(chave, b.origem)

    def test_o_aviso_principal_continua(self):
        b = bridge.derive([], [])
        self.assertIn("não recebe o perfil do SUPREM", b.aviso)


if __name__ == "__main__":
    unittest.main()
