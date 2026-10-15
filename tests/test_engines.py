"""Registro de motores: a costura que deixa a interface ignorar qual simulador roda."""

from __future__ import annotations

import unittest

from mos_studio.core import engines
from mos_studio.core.recipe import Step

RECEITA = [Step.new(t).as_dict()
           for t in ("INITIALIZE", "IMPLANTI", "DIFFUSION", "PRINT")]


class TestRegistro(unittest.TestCase):
    def test_os_dois_motores_estao_registrados(self):
        ids = [m.id for m in engines.all_engines()]
        self.assertEqual(ids, [engines.SUPREM3, engines.SUPREM4])

    def test_cada_motor_tem_rotulo_e_explicacao(self):
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                self.assertTrue(motor.label)
                self.assertTrue(motor.blurb)

    def test_id_desconhecido_cai_no_suprem3_em_vez_de_levantar(self):
        """A configuração pode vir de uma versão mais nova; a tela tem de abrir."""
        self.assertEqual(engines.get("motor-do-futuro").id, engines.SUPREM3)

    def test_get_devolve_a_mesma_instancia(self):
        self.assertIs(engines.get(engines.SUPREM4), engines.get(engines.SUPREM4))

    def test_default_id_e_um_motor_valido(self):
        self.assertIn(engines.default_id(), (engines.SUPREM3, engines.SUPREM4))


class TestInterfaceUniforme(unittest.TestCase):
    """Os dois motores respondem às mesmas sete operações."""

    def test_geram_deck_a_partir_da_mesma_receita(self):
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                deck = motor.build_in_file("Receita comum", RECEITA)
                self.assertTrue(deck.strip())

    def test_decks_dos_dois_motores_sao_dialetos_diferentes(self):
        """Se saíssem iguais, um dos dois estaria gerando o dialeto errado."""
        s3 = engines.get(engines.SUPREM3).build_in_file("X", RECEITA)
        s4 = engines.get(engines.SUPREM4).build_in_file("X", RECEITA)
        self.assertNotEqual(s3, s4)
        self.assertIn("TITLE", s3)
        self.assertIn("mode one.dim", s4)

    def test_deck_de_evolucao_e_plano_coerentes(self):
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                deck, plano = motor.build_profile_deck("Evolução", RECEITA)
                self.assertTrue(deck.strip())
                self.assertTrue(plano)

    def test_tem_runner_e_excecao_de_cancelamento(self):
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                self.assertTrue(callable(motor.runner))
                self.assertTrue(issubclass(motor.cancelled, Exception))

    def test_check_relata_problemas_de_pasta_inexistente(self):
        from pathlib import Path
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                self.assertTrue(motor.check(Path("/nao/existe")))

    def test_available_responde_sem_levantar(self):
        for motor in engines.all_engines():
            with self.subTest(motor=motor.id):
                self.assertIsInstance(motor.available(), bool)


class TestAproximacoes(unittest.TestCase):
    """As diferenças de física ficam visíveis, não escondidas pela costura."""

    def test_suprem3_nao_aproxima_a_propria_receita(self):
        epitaxia = [Step.new("EPITAXY").as_dict()]
        self.assertEqual(engines.get(engines.SUPREM3).approximations(epitaxia), [])

    def test_suprem4_declara_a_epitaxia_aproximada(self):
        epitaxia = [Step.new("EPITAXY").as_dict()]
        avisos = engines.get(engines.SUPREM4).approximations(epitaxia)
        self.assertTrue(avisos)
        self.assertIn("Epitaxia", avisos[0])


class TestEscolhaDoUsuario(unittest.TestCase):
    """A escolha é guardada na configuração do usuário, não ao lado do programa."""

    def setUp(self):
        from mos_studio import config
        self.anterior = config.get(engines.CONFIG_KEY, None)

    def tearDown(self):
        from mos_studio import config
        config.set(engines.CONFIG_KEY, self.anterior or "")

    def test_set_default_guarda_e_default_id_respeita(self):
        from mos_studio import config
        engines.set_default(engines.SUPREM4)
        self.assertEqual(config.get(engines.CONFIG_KEY), engines.SUPREM4)
        if engines.get(engines.SUPREM4).available():
            self.assertEqual(engines.default_id(), engines.SUPREM4)

    def test_set_default_ignora_id_invalido(self):
        from mos_studio import config
        engines.set_default(engines.SUPREM3)
        engines.set_default("nao-existe")
        self.assertEqual(config.get(engines.CONFIG_KEY), engines.SUPREM3)

    def test_motor_salvo_mas_ausente_nao_e_escolhido(self):
        """Desinstalar um motor não pode travar a tela no motor ausente."""
        from mos_studio import config
        config.set(engines.CONFIG_KEY, engines.SUPREM4)
        escolhido = engines.default_id()
        if not engines.get(engines.SUPREM4).available():
            self.assertNotEqual(escolhido, engines.SUPREM4)


if __name__ == "__main__":
    unittest.main()
