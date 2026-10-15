"""A sessão interativa do SUPREM-IV.

Os testes de formatação não precisam do motor. Os de :class:`TestSessao`
sobem o binário de verdade — é o único jeito de verificar que o estado
persiste entre comandos, que é a razão de a sessão existir.
"""

from __future__ import annotations

import unittest

from mos_studio.core import shell4 as S


def tem_motor() -> bool:
    from mos_studio.core import suprem4

    return suprem4.find_run_dir() is not None


class TestLimpeza(unittest.TestCase):
    def test_remove_o_banner(self):
        bruto = ("SUPREM-IV.GS B.9305\n"
                 "\t(c) 1991-1993 Stanford University\n"
                 "\t(c) 1991 University of Florida\n"
                 "Reading Models...\n"
                 "1000\n")
        self.assertEqual(S.clean(bruto), "1000")

    def test_remove_o_ruido_do_echo(self):
        """O ``echo`` imprime certo e só depois reclama."""
        self.assertEqual(S.clean("ola mundo\nstring not allowed in expression\n"),
                         "ola mundo")
        self.assertEqual(
            S.clean("900 graus\ngrammar rule violated in expression\n"),
            "900 graus")

    def test_mantem_erro_de_verdade(self):
        self.assertIn("No mesh defined!", S.clean("No mesh defined!\n"))

    def test_mantem_a_tabela_com_as_tabulacoes(self):
        tabela = "y coordinate in um\t doping\tMaterial\n   0.0000\t-1e+15\tsilicon"
        self.assertEqual(S.clean(tabela), tabela)

    def test_colapsa_linhas_vazias_seguidas(self):
        self.assertEqual(S.clean("a\n\n\n\nb\n"), "a\n\nb")

    def test_tira_as_linhas_vazias_do_fim(self):
        self.assertEqual(S.clean("a\n\n\n"), "a")

    def test_entrada_vazia(self):
        self.assertEqual(S.clean(""), "")
        self.assertEqual(S.clean("\n\n"), "")


class TestSaida(unittest.TestCase):
    def test_reconhece_os_comandos_de_encerrar(self):
        for c in ("quit", "exit", "stop", "qui", "QUIT", "  quit  "):
            self.assertTrue(S.is_quit(c), c)

    def test_abreviacao_curta_demais_nao_conta(self):
        """``q`` sozinho é ambíguo; não vale arriscar matar a sessão."""
        self.assertFalse(S.is_quit("q"))

    def test_cartao_normal_nao_e_saida(self):
        for c in ("diffuse time=30 temp=1000 nitrogen", "echo quit",
                  "select z=doping", ""):
            self.assertFalse(S.is_quit(c), c)

    def test_sentinela_e_texto_nao_numero(self):
        """``echo 987654321`` imprime ``9.87654e+08``: o echo avalia número."""
        self.assertFalse(S.SENTINEL.isdigit())
        self.assertTrue(S.SENTINEL[0].isalpha())


@unittest.skipUnless(tem_motor(), "SUPREM-IV não está instalado")
class TestSessao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sh = S.Shell4()
        cls.sh.start()

    @classmethod
    def tearDownClass(cls):
        cls.sh.close()

    def test_o_motor_sobe(self):
        self.assertTrue(self.sh.alive)

    def test_o_estado_persiste_entre_comandos(self):
        """É a razão de existir da sessão: um processo por comando perderia
        a variável, a malha e as soluções."""
        self.sh.send("define TMP 1234")
        r = self.sh.send("echo ${TMP}")
        self.assertEqual(r.text.strip(), "1234")

    def test_comando_vazio_nao_fala_com_o_motor(self):
        r = self.sh.send("   ")
        self.assertEqual(r.text, "")
        self.assertTrue(r.ok)

    def test_echo_sai_limpo(self):
        r = self.sh.send("echo ola mundo")
        self.assertEqual(r.text.strip(), "ola mundo")
        self.assertTrue(r.ok)

    def test_quit_nao_mata_a_sessao(self):
        r = self.sh.send("quit")
        self.assertTrue(self.sh.alive)
        self.assertIn("continua aberto", r.text)

    def test_cabecalho_desconhecido_e_barrado(self):
        """Sem a guarda, o shell do motor entrega a linha ao /bin/sh."""
        r = self.sh.send("cartao.que.nao.existe")
        self.assertFalse(r.ok)
        self.assertTrue(r.errors)

    def test_comando_do_sistema_e_barrado(self):
        r = self.sh.send("rm -rf /tmp/alvo.que.nao.existe")
        self.assertFalse(r.ok)
        self.assertIn("rm", r.errors[0])

    def test_o_motor_segue_vivo_depois_de_barrar(self):
        self.sh.send("rm -rf /tmp/alvo.que.nao.existe")
        self.assertTrue(self.sh.alive)
        self.assertEqual(self.sh.send("echo vivo").text.strip(), "vivo")

    def test_abreviacao_de_cartao_passa(self):
        r = self.sh.send("diff temp=1000 time=10 nitrogen")
        self.assertFalse(any("diff" in e for e in r.errors))

    def test_erro_do_motor_aparece_nos_erros(self):
        r = self.sh.send("initialize boron conc=1e15")
        self.assertTrue(r.errors or "mesh" in r.text.lower())

    def test_help_traz_a_gramatica_do_cartao(self):
        r = self.sh.help("trap")
        self.assertIn("total", r.text)
        self.assertIn("frac.0", r.text)

    def test_help_aceita_abreviacao(self):
        self.assertIn("Dix.0", self.sh.help("arsen").text)

    def test_so_o_que_passou_entra_no_historico(self):
        antes = len(self.sh.history)
        self.sh.send("rm -rf /tmp/alvo.que.nao.existe")
        self.assertEqual(len(self.sh.history), antes)
        self.sh.send("echo entrou")
        self.assertEqual(len(self.sh.history), antes + 1)


@unittest.skipUnless(tem_motor(), "SUPREM-IV não está instalado")
class TestSessaoCompleta(unittest.TestCase):
    """Uma sessão própria, para não sujar o estado das outras."""

    def test_monta_malha_e_le_perfil_comando_por_comando(self):
        from mos_studio.core import mesh as M, parsers

        malha = M.Mesh(x=[M.Line(0.0, 0.2), M.Line(0.4, 0.2)],
                       y=[M.Line(0.0, 0.05), M.Line(0.5, 0.2)])
        with S.Shell4() as sh:
            for c in M.to_cards(malha):
                r = sh.send(c, timeout=60)
                self.assertTrue(r.ok, (c, r.errors, r.text))
            self.assertTrue(sh.send("initialize boron conc=1e15 orient=100",
                                    timeout=120).ok)
            sh.send("select z=doping")
            r = sh.send("print.1d x.value=0.2", timeout=60)
            perfil = parsers.parse_print_1d(r.text)
            self.assertTrue(perfil)
            self.assertTrue(all(v < 0 for _, v, _ in perfil[0]))   # tipo p

    def test_source_roda_um_deck_inteiro(self):
        from mos_studio.core import mesh as M

        deck = "\n".join(M.to_cards(M.default_mesh())
                         + ["initialize boron conc=1e15 orient=100"]) + "\n"
        with S.Shell4() as sh:
            r = sh.source(deck, timeout=180)
            self.assertTrue(r.ok, (r.errors, r.text[-400:]))
            self.assertTrue(sh.alive)

    def test_reiniciar_zera_o_estado(self):
        with S.Shell4() as sh:
            sh.send("define ALVO 42")
            self.assertEqual(sh.send("echo ${ALVO}").text.strip(), "42")
            sh.restart()
            self.assertEqual(sh.history, [])
            self.assertNotEqual(sh.send("echo ${ALVO}").text.strip(), "42")

    def test_reiniciar_repetindo_mantem_o_estado(self):
        with S.Shell4() as sh:
            sh.send("define ALVO 42")
            sh.restart(replay=True)
            self.assertEqual(sh.send("echo ${ALVO}").text.strip(), "42")

    def test_fechar_encerra_o_processo(self):
        sh = S.Shell4()
        sh.start()
        self.assertTrue(sh.alive)
        sh.close()
        self.assertFalse(sh.alive)

    def test_mandar_depois_de_fechar_sobe_de_novo(self):
        sh = S.Shell4()
        sh.start()
        sh.close()
        try:
            self.assertEqual(sh.send("echo voltou").text.strip(), "voltou")
        finally:
            sh.close()


if __name__ == "__main__":
    unittest.main()
