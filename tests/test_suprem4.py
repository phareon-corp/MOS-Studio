"""Orquestração do SUPREM-IV.GS e regressão do motor compilado.

Dois tipos de teste aqui. Os de orquestração (ambiente, verificação,
cancelamento) rodam sempre. Os de regressão executam o binário de verdade e
são pulados se ``./build_suprem4.sh`` ainda não foi rodado.

Os de regressão existem porque o build de 64 bits não é o que o fabricante
previa (o Makefile usa ``-m32``) e porque a glibc atual expôs um bug de
portabilidade real na camada de shell — ver ADR 0002 e
``patches/suprem4/0001``. Um binário que compila e linka não é prova de que
calcula; por isso aqui se roda os exemplos de fábrica e se confere o
resultado contra o próprio arquivo de coeficientes do motor.
"""

from __future__ import annotations

import math
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mos_studio.core import deck4 as D4
from mos_studio.core import suprem4
from mos_studio.core.recipe import Step

MOTOR = suprem4.find_run_dir()
TEM_MOTOR = MOTOR is not None and not suprem4.check_engine(MOTOR)

RECEITA = [
    Step("INITIALIZE", {"orientation": "100", "dopant": "BORON",
                        "concentration": "1E15", "dx": "5E-3",
                        "thickness": "0.5"}),
    Step("DEPOSITION", {"material": "OXIDE", "thickness": "0.075",
                        "dopant": "", "concentration": "", "temperature": ""}),
    Step("IMPLANTI", {"dopant": "BORON", "dose": "3E14", "energy": "70",
                      "distribution": "PEARSON"}),
    Step("DIFFUSION", {"ambient": "DRYO2", "temperature": "1000",
                       "time": "30", "gasConc": "", "solidSol": False,
                       "tRate": ""}),
    Step("PRINT", {"what": "NET", "curve": "", "extra": "LAYER",
                   "filename": "", "linespa": ""}),
    Step("PRINT", {"what": "NET", "curve": "", "extra": "CONCENTR",
                   "filename": "", "linespa": ""}),
]


def deck_de_teste() -> str:
    return D4.build_in_file("TESTE SUPREM4", [s.as_dict() for s in RECEITA])


# ── orquestração (sem motor) ──────────────────────────────────────────────

class TestVerificacao(unittest.TestCase):
    def test_pasta_inexistente_e_relatada(self):
        problemas = suprem4.check_engine(Path("/nao/existe"))
        self.assertTrue(problemas)
        self.assertIn("build_suprem4.sh", problemas[0])

    def test_pasta_vazia_relata_binario_e_dados(self):
        with tempfile.TemporaryDirectory() as d:
            problemas = suprem4.check_engine(Path(d))
            texto = " ".join(problemas)
            self.assertIn("bin/suprem", texto)
            self.assertIn("suprem.uk", texto)

    def test_none_e_relatado_sem_levantar(self):
        self.assertTrue(suprem4.check_engine(None))


class TestAmbiente(unittest.TestCase):
    """As quatro variáveis do motor e o HOME isolado."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.run = Path("/opt/suprem4")
        self.env = suprem4._environment(self.run, self.work)

    def test_aponta_para_os_arquivos_de_dados(self):
        self.assertEqual(self.env["SUP4KEYFILE"],
                         str(self.run / "data" / "suprem.uk"))
        self.assertEqual(self.env["SUP4MODELRC"],
                         str(self.run / "data" / "modelrc"))
        self.assertEqual(self.env["SUP4IMPDATA"],
                         str(self.run / "data" / "sup4gs.imp"))

    def test_home_aponta_para_o_diretorio_de_trabalho(self):
        """O motor lê $HOME/.supremrc antes do deck: isolar é o que torna a
        execução reproduzível, independente da máquina do usuário."""
        self.assertEqual(self.env["HOME"], str(self.work))

    def test_preserva_o_ambiente_do_sistema(self):
        import os
        if "PATH" in os.environ:
            self.assertEqual(self.env["PATH"], os.environ["PATH"])


class TestDeteccaoDeErro(unittest.TestCase):
    """O motor sai com 0 mesmo recusando cartões: é a saída que denuncia."""

    def test_reconhece_as_mensagens_do_parser(self):
        for msg in ("errors detected on command input",
                    "grammar rule violated in expression",
                    "string not allowed in expression",
                    "unable to read or open the unformatted key file /x",
                    "where is the unformatted key file???",
                    "Pisces mesh i/o error: please specify a temperature"):
            with self.subTest(mensagem=msg):
                self.assertTrue(suprem4.engine_errors(msg))

    def test_saida_normal_nao_e_erro(self):
        saida = ("SUPREM-IV.GS B.9305\nReading Models...\n"
                 "Solving 0 + 0.1 = 0.1, 100%, np 43\n"
                 "x coordinate in um\tdoping\tMaterial\n"
                 "   0.00000000\t-1.1e+19   \tsilicon\n")
        self.assertEqual(suprem4.engine_errors(saida), [])

    def test_cabecalho_do_solver_nao_e_erro(self):
        """A tabela do solver tem uma coluna chamada 'error'."""
        self.assertEqual(
            suprem4.engine_errors("           error        time    time    norm"),
            [])

    def test_nao_repete_a_mesma_mensagem(self):
        texto = "errors detected on command input\n" * 3
        self.assertEqual(len(suprem4.engine_errors(texto)), 1)

    def test_entrada_vazia(self):
        self.assertEqual(suprem4.engine_errors(""), [])
        self.assertEqual(suprem4.engine_errors(None), [])


class TestEstagios(unittest.TestCase):
    def test_rotula_os_cartoes_do_deck(self):
        etapas = suprem4._stages_from(deck_de_teste())
        self.assertIn("substrato", etapas)
        self.assertIn("implante", etapas)
        self.assertIn("difusão", etapas)
        self.assertIn("tabela", etapas)

    def test_ignora_comentarios_e_option(self):
        self.assertEqual(suprem4._stages_from("# titulo\noption quiet\nquit\n"), [])


class TestSemMotor(unittest.TestCase):
    def test_execute_sem_motor_levanta_com_recado_util(self):
        runner = suprem4.Suprem4Runner(deck_de_teste(), run_dir=Path("/nao/existe"))
        with self.assertRaises(RuntimeError) as ctx:
            runner.execute()
        self.assertIn("SUPREM-IV indisponível", str(ctx.exception))


# ── regressão do motor compilado ──────────────────────────────────────────

@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestExecucao(unittest.TestCase):
    """Uma receita montada na interface roda e volta com perfil e camadas."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        runner = suprem4.Suprem4Runner(deck_de_teste(),
                                       results_dir=Path(cls.tmp))
        cls.res = runner.execute()

    def test_produziu_perfil(self):
        self.assertGreater(len(self.res.profile()), 20)

    def test_perfil_ordenado_por_profundidade(self):
        profundidades = [d for d, _ in self.res.profile()]
        self.assertEqual(profundidades, sorted(profundidades))

    def test_perfil_comeca_na_superficie_do_silicio(self):
        """A profundidade é reancorada em zero para casar com o SUPREM-III."""
        self.assertAlmostEqual(self.res.profile()[0][0], 0.0, places=6)

    def test_perfil_todo_tipo_p(self):
        """Boro implantado em substrato de boro: nada pode virar tipo n."""
        self.assertTrue(all(c < 0 for _, c in self.res.profile()))

    def test_perfil_decai_da_superficie_para_o_fundo(self):
        """Nesta receita (0,5 µm) a cauda do implante ainda não atingiu o
        fundo, então o que se verifica é o decaimento, não o nível do
        substrato — esse é o teste do substrato profundo, abaixo."""
        perfil = self.res.profile()
        meio = len(perfil) // 2
        self.assertGreater(abs(perfil[meio][1]), abs(perfil[-1][1]))

    def test_substrato_profundo_volta_ao_nivel_de_fundo(self):
        """Com 3 µm a cauda decai e o fundo tem de bater com o 1e15 pedido."""
        passos = [
            Step("INITIALIZE", {"orientation": "100", "dopant": "BORON",
                                "concentration": "1E15", "dx": "5E-3",
                                "thickness": "3.0"}).as_dict(),
            Step("IMPLANTI", {"dopant": "BORON", "dose": "3E14",
                              "energy": "70", "distribution": "PEARSON"}).as_dict(),
            Step("DIFFUSION", {"ambient": "NITROGEN", "temperature": "1000",
                               "time": "30", "gasConc": "", "solidSol": False,
                               "tRate": ""}).as_dict(),
            Step("PRINT", {"what": "NET", "curve": "", "extra": "CONCENTR",
                           "filename": "", "linespa": ""}).as_dict(),
        ]
        deck = D4.build_in_file("Substrato profundo", passos)
        perfil = suprem4.Suprem4Runner(
            deck, results_dir=Path(tempfile.mkdtemp())).execute().profile()
        fundo = perfil[-1][1]
        self.assertLess(fundo, 0)
        self.assertAlmostEqual(abs(fundo), 1e15, delta=3e14)

    def test_implante_deixa_pico_acima_do_substrato(self):
        """3e14 cm⁻² a 70 keV: o pico tem de superar o fundo em muitas ordens."""
        pico = max(abs(c) for _, c in self.res.profile())
        self.assertGreater(pico, 1e17)

    def test_listou_as_camadas(self):
        camadas = self.res.layers()
        self.assertTrue(camadas)
        self.assertIn("silicon", [m for m, _ in camadas])
        self.assertIn("oxide", [m for m, _ in camadas])

    def test_oxido_cresceu_sobre_o_oxido_depositado(self):
        """0,075 µm depositados + crescimento em O₂ seco: tem de passar disso."""
        espessura = self.res.oxide_thickness()
        self.assertIsNotNone(espessura)
        self.assertGreater(espessura, 0.075)
        self.assertLess(espessura, 0.5)

    def test_salvou_a_saida_e_o_deck(self):
        self.assertIsNotNone(self.res.out_dir)
        nomes = {p.name for p in self.res.out_dir.iterdir()}
        self.assertIn(suprem4.OUTPUT_NAME, nomes)
        self.assertIn(suprem4.INPUT_NAME, nomes)

    def test_registrou_os_estagios(self):
        self.assertTrue(self.res.stages)

    def test_identifica_o_motor(self):
        self.assertEqual(self.res.engine, "SUPREM-IV.GS")


@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestCancelamento(unittest.TestCase):
    def test_cancelar_antes_de_comecar_levanta_cancelled(self):
        runner = suprem4.Suprem4Runner(deck_de_teste())
        runner.cancel()
        with self.assertRaises(suprem4.Cancelled):
            runner.execute()

    def test_cancel_de_outra_thread_e_seguro(self):
        """O cancelamento vem da thread da interface, nunca da de trabalho."""
        runner = suprem4.Suprem4Runner(deck_de_teste(),
                                       results_dir=Path(tempfile.mkdtemp()))
        t = threading.Thread(target=runner.cancel)
        t.start()
        t.join()
        self.assertTrue(runner.cancelled)


@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestRecusaDeDeck(unittest.TestCase):
    def test_cabecalho_desconhecido_e_barrado_antes_de_rodar(self):
        """O motor NÃO recusa um cartão desconhecido: entrega ao /bin/sh.

        Verificado na mão: um deck com ``rm -rf ...`` faz o shell do motor
        executar o comando. Por isso a barreira é no runner, antes de rodar.
        """
        deck = "option quiet\nnaoexisteissocomocartao foo=1\nquit\n"
        runner = suprem4.Suprem4Runner(deck, results_dir=Path(tempfile.mkdtemp()))
        with self.assertRaises(RuntimeError) as ctx:
            runner.execute()
        self.assertIn("shell do sistema", str(ctx.exception))

    def test_parametro_inexistente_vira_runtimeerror(self):
        """Num cartão válido, o motor recusa parâmetro desconhecido."""
        deck = "option quiet\ndiffuse naoexisteparam=3\nquit\n"
        runner = suprem4.Suprem4Runner(deck, results_dir=Path(tempfile.mkdtemp()))
        with self.assertRaises(RuntimeError):
            runner.execute()

    def test_tag_de_malha_errada_vira_runtimeerror(self):
        """Uma tag inexistente NÃO emite "errors detected": o motor segue sem
        criar a região e a saída sai vazia. O detector cobre essa mensagem
        justamente porque ela é silenciosa no código de saída."""
        deck = ("option quiet\nmode one.dim\n"
                "line x loc=0 spacing=0.02 tag=topo\n"
                "line x loc=0.5 spacing=0.05 tag=fundo\n"
                "region silicon xlo=topo xhi=naoexiste\n"
                "select z=doping\nprint.1d\nquit\n")
        runner = suprem4.Suprem4Runner(deck, results_dir=Path(tempfile.mkdtemp()))
        with self.assertRaises(RuntimeError):
            runner.execute()

    def test_expressao_invalida_vira_runtimeerror(self):
        """'silicon' numa expressão é nome de material, não de impureza."""
        deck = ("option quiet\nmode one.dim\n"
                "line x loc=0 spacing=0.02 tag=t\n"
                "line x loc=0.5 spacing=0.05 tag=f\n"
                "region gaas xlo=t xhi=f\n"
                "boundary exposed xlo=t xhi=t\n"
                "init carbon conc=1e15\n"
                "select z=log10(silicon)\nprint.1d\nquit\n")
        runner = suprem4.Suprem4Runner(deck, results_dir=Path(tempfile.mkdtemp()))
        with self.assertRaises(RuntimeError):
            runner.execute()


@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestExemplosDeFabrica(unittest.TestCase):
    """Os decks que acompanham o fonte, rodados como regressão do binário.

    Cobrem caminhos que a interface não monta — malha 2D, corrosão por
    coordenadas, GaAs, estrutura em arquivo — e foram escritos pelos autores
    do motor, o que os torna a melhor referência disponível de que o build
    está íntegro.
    """

    #: Exemplos escolhidos por cobrirem partes diferentes do motor. Ficam de
    #: fora os que não rodam sozinhos (``exam5/sup2pis.s4`` é um fragmento
    #: que pressupõe a estrutura de ``whole.s4``) e os que a documentação
    #: GaAs do próprio fonte escreve com ``select z=log10(silicon)``, que
    #: este arquivo de chaves recusa — use ``isilicon`` (ver ADR 0002).
    EXEMPLOS = ("exam1/boron.in", "exam2/oed.in", "exam3/oed.in",
                "exam8/nit-stress.s4", "exam10/example10.in",
                "exam13/example13.in", "exam17/example17.in")

    #: Exemplos que o motor recusa por defeito do **próprio deck**, não do
    #: build. Ficam registrados aqui para que a diferença entre "o deck está
    #: errado" e "o motor quebrou" não se perca na próxima vez.
    #:   exam6  - o echo decorativo tem "< O >", que o avaliador de expressão
    #:            recusa; a oxidação em si roda e sai nas três orientações.
    #:   exam12 - "select z=log10(silicon)": em GaAs o implante é 'isilicon' e
    #:            'silicon' é nome de material. A nota de GaAs do fonte
    #:            contradiz este arquivo de chaves (ver ADR 0002).
    RECUSADOS = {"exam6/oxcalib.s4": "grammar rule violated",
                 "exam12/example12.in": "string not allowed"}

    def test_exemplos_existem_na_instalacao(self):
        """O build copia examples/ para a instalação; sem isso não há regressão."""
        base = Path(MOTOR) / "examples"
        self.assertTrue(base.is_dir(), "suprem4-run/examples não foi instalado")

    def test_exemplos_rodam_sem_erro(self):
        import shutil
        import subprocess
        base = Path(MOTOR) / "examples"
        binario = Path(MOTOR) / "bin" / "suprem"
        for rel in self.EXEMPLOS:
            deck = base / rel
            if not deck.exists():
                continue
            with self.subTest(exemplo=rel):
                work = Path(tempfile.mkdtemp(prefix="s4ex_"))
                try:
                    # Alguns decks leem arquivos auxiliares do próprio diretório.
                    for vizinho in deck.parent.iterdir():
                        if vizinho.is_file():
                            shutil.copy2(vizinho, work / vizinho.name)
                    p = subprocess.run(
                        [str(binario), deck.name], cwd=str(work),
                        env=suprem4._environment(Path(MOTOR), work),
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=300)
                    saida = p.stdout.decode("latin1", "replace")
                    self.assertEqual(p.returncode, 0,
                                     f"{rel} terminou com {p.returncode}")
                    self.assertEqual(suprem4.engine_errors(saida), [],
                                     f"{rel} teve recusa de cartão")
                finally:
                    shutil.rmtree(work, ignore_errors=True)

    def test_exemplos_recusados_falham_pelo_motivo_conhecido(self):
        """Trava o diagnóstico dos dois decks defeituosos de fábrica.

        Se um dia pararem de falhar (fonte corrigido a montante) ou passarem a
        falhar por outro motivo, este teste avisa — é a diferença entre um
        defeito de deck conhecido e uma regressão do motor.
        """
        import shutil
        import subprocess
        base = Path(MOTOR) / "examples"
        for rel, esperado in self.RECUSADOS.items():
            deck = base / rel
            if not deck.exists():
                continue
            with self.subTest(exemplo=rel):
                work = Path(tempfile.mkdtemp(prefix="s4bad_"))
                try:
                    for vizinho in deck.parent.iterdir():
                        if vizinho.is_file():
                            shutil.copy2(vizinho, work / vizinho.name)
                    p = subprocess.run(
                        [str(Path(MOTOR) / "bin" / "suprem"), deck.name],
                        cwd=str(work),
                        env=suprem4._environment(Path(MOTOR), work),
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, timeout=300)
                    saida = p.stdout.decode("latin1", "replace")
                    self.assertIn(esperado, saida)
                    # Apesar da recusa, o motor termina e produz tabela: a
                    # falha é do cartão, não da simulação.
                    self.assertEqual(p.returncode, 0)
                finally:
                    shutil.rmtree(work, ignore_errors=True)

    def test_foreach_expande_os_valores_certos(self):
        """Regressão do patch 0001.

        Sem ele, o build de 64 bits corrompe a expansão de
        ``foreach v (a to b step c)`` — a glibc atual vetoriza ``strcpy`` e as
        cópias sobrepostas de ``shell/list.c`` embaralham a string. O motor
        engolia valores truncados sem reclamar, o que é a pior falha possível
        num simulador. Ver ADR 0002.
        """
        import subprocess
        # Sem 'set echo': ele imprimiria cada cartão além da saída do echo,
        # duplicando cada valor. O 'echo' ainda reclama que o argumento não é
        # expressão, o que é ruído esperado e não afeta o valor impresso.
        deck = ("option quiet\n"
                "foreach v (15. to 18.5 step 0.5)\n"
                "echo val=v\n"
                "end\nquit\n")
        work = Path(tempfile.mkdtemp(prefix="s4fe_"))
        try:
            (work / "d.in").write_text(deck, encoding="ascii")
            p = subprocess.run(
                [str(Path(MOTOR) / "bin" / "suprem"), "d.in"], cwd=str(work),
                env=suprem4._environment(Path(MOTOR), work),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=60)
            saida = p.stdout.decode("latin1", "replace")
            valores = [l.split("val=", 1)[1].strip()
                       for l in saida.splitlines() if "val=" in l]
            self.assertEqual(valores,
                             ["15", "15.5", "16", "16.5", "17", "17.5",
                              "18", "18.5"])
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)


@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestFisicaDaOxidacao(unittest.TestCase):
    """O motor calcula oxidação segundo os próprios coeficientes?

    Verificação forte: em vez de comparar com um número de livro (que o
    ``modelrc`` desta compilação não promete reproduzir — ver ADR 0002), a
    varredura é ajustada por Deal-Grove e os coeficientes resultantes são
    confrontados com os que ``suprem4-run/data/modelrc`` prescreve. Um build
    quebrado erraria isso em ordens de grandeza, não em porcento.
    """

    #: Coeficientes do modelrc para O₂ úmido acima de ``p.break``/``l.break``.
    PAR_H_0, PAR_H_E = 7.00, 0.78          # parabólico (µm²/min)
    LIN_H_0, LIN_H_E = 2.95e6, 2.05        # linear <111> (µm/min)
    ORI_FAC_100 = 0.595                    # fator de orientação <100>
    TEMPERATURA = 1000.0

    @classmethod
    def setUpClass(cls):
        from mos_studio.core import engines, oxidation
        cls.sweep = oxidation.sweep([15, 30, 60, 90, 120, 180, 240],
                                    ambient="WETO2",
                                    temperature=cls.TEMPERATURA,
                                    engine_id=engines.SUPREM4)

    def _modelo(self):
        k = 8.617333262e-5
        T = self.TEMPERATURA + 273.15
        B = self.PAR_H_0 * math.exp(-self.PAR_H_E / (k * T)) * 60
        BA = self.LIN_H_0 * math.exp(-self.LIN_H_E / (k * T)) * 60 * self.ORI_FAC_100
        return B, BA

    def test_a_varredura_toda_rodou(self):
        self.assertEqual(self.sweep.error, "")
        self.assertEqual(len(self.sweep.valid()), 7)

    def test_espessura_cresce_com_o_tempo(self):
        espessuras = [p.thickness_um for p in self.sweep.valid()]
        self.assertEqual(espessuras, sorted(espessuras))

    def test_ajuste_deal_grove_e_praticamente_perfeito(self):
        """Se o motor segue Deal-Grove, t/Xo contra Xo é uma reta."""
        self.assertGreater(self.sweep.fit["r2"], 0.999)

    def test_coeficiente_parabolico_bate_com_o_modelrc(self):
        B, _ = self._modelo()
        self.assertAlmostEqual(self.sweep.fit["B_h"] / B, 1.0, delta=0.05)

    def test_coeficiente_linear_bate_com_o_modelrc(self):
        _, BA = self._modelo()
        self.assertAlmostEqual(self.sweep.fit["BA_h"] / BA, 1.0, delta=0.05)

    def test_difere_do_suprem3_como_se_espera_de_outro_modelo(self):
        """Os dois motores não são intercambiáveis: o modelrc é outro.

        O teste trava essa diferença: se um dia os dois passarem a dar o
        mesmo número, algo está apontando para o motor errado.
        """
        from mos_studio.core import engines, oxidation
        if not engines.get(engines.SUPREM3).available():
            self.skipTest("SUPREM-III ausente")
        s3 = oxidation.sweep([15, 30, 60, 120], ambient="WETO2",
                             temperature=self.TEMPERATURA,
                             engine_id=engines.SUPREM3)
        if not s3.ok:
            self.skipTest("varredura do SUPREM-III não completou")
        self.assertGreater(self.sweep.fit["B_h"], s3.fit["B_h"])


@unittest.skipUnless(TEM_MOTOR, "SUPREM-IV ausente (rode ./build_suprem4.sh)")
class TestConservacaoDaDose(unittest.TestCase):
    """O que entra tem de aparecer: integral do perfil ≈ dose implantada."""

    def test_dose_implantada_aparece_no_perfil(self):
        passos = [
            Step("INITIALIZE", {"orientation": "100", "dopant": "PHOSPHOR",
                                "concentration": "1E14", "dx": "2E-3",
                                "thickness": "1.0"}).as_dict(),
            Step("IMPLANTI", {"dopant": "BORON", "dose": "1E14",
                              "energy": "50", "distribution": "PEARSON"}).as_dict(),
            Step("PRINT", {"what": "BORON", "curve": "", "extra": "CONCENTR",
                           "filename": "", "linespa": ""}).as_dict(),
        ]
        deck = D4.build_in_file("Conservacao de dose", passos)
        runner = suprem4.Suprem4Runner(deck, results_dir=Path(tempfile.mkdtemp()))
        perfil = runner.execute().profile()
        self.assertTrue(perfil)
        # Trapézios, com profundidade em µm → cm (1 µm = 1e-4 cm).
        integral = 0.0
        for (d0, c0), (d1, c1) in zip(perfil, perfil[1:]):
            integral += (c0 + c1) / 2.0 * (d1 - d0) * 1e-4
        # 20% de folga: a malha é discreta e o perfil é truncado no fundo.
        self.assertAlmostEqual(integral / 1e14, 1.0, delta=0.2)


if __name__ == "__main__":
    unittest.main()
