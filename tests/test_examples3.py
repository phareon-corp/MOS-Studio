"""Os exemplos 1-D do MOS-Studio.

:class:`TestContraOMotor` roda cada receita no SUPREM-III e confere os números
que o catálogo promete. É o que impede a descrição de envelhecer: se um
coeficiente do motor mudar, o teste avisa antes do usuário.
"""

from __future__ import annotations

import unittest

from mos_studio.core import deck, examples3 as E3, recipe, suprem


def tem_motor() -> bool:
    return suprem.find_run_dir() is not None


class TestCatalogo(unittest.TestCase):
    def test_tem_o_transistor(self):
        ids = [e.id for e in E3.CATALOG]
        self.assertIn("nmos-porta", ids)
        self.assertIn("nmos-fonte-dreno", ids)

    def test_busca_por_id(self):
        self.assertEqual(E3.get("nmos-porta").name, "Transistor NMOS")
        self.assertIsNone(E3.get("nao.existe"))

    def test_todo_exemplo_tem_nome_descricao_e_expectativa(self):
        for e in E3.CATALOG:
            self.assertTrue(e.name and e.desc and e.title, e.id)
            self.assertTrue(e.expect, e.id)

    def test_ids_nao_repetem(self):
        ids = [e.id for e in E3.CATALOG]
        self.assertEqual(len(ids), len(set(ids)))

    def test_as_etapas_sao_de_tipos_conhecidos(self):
        for e in E3.CATALOG:
            for passo in e.build():
                self.assertIn(passo.type, recipe.STEP_TYPES, e.id)

    def test_cada_build_cria_etapas_novas(self):
        """Abrir o mesmo exemplo duas vezes não pode compartilhar estado."""
        a, b = E3.NMOS_PORTA.build(), E3.NMOS_PORTA.build()
        self.assertNotEqual(a[0].uid, b[0].uid)
        a[0].params["concentration"] = "9E99"
        self.assertNotEqual(a[0].params["concentration"],
                            b[0].params["concentration"])

    def test_comeca_pela_inicializacao(self):
        for e in E3.CATALOG:
            self.assertEqual(e.build()[0].type, "INITIALIZE", e.id)

    def test_cabe_no_teto_de_malha_do_suprem3(self):
        """O motor recusa o deck inteiro acima de 500 pontos."""
        for e in E3.CATALOG:
            nos = E3.grid_points(e)
            self.assertGreater(nos, 0, e.id)
            self.assertLess(nos, E3.GRID_LIMIT, e.id)

    def test_a_receita_passa_na_verificacao(self):
        for e in E3.CATALOG:
            self.assertEqual(recipe.validate(e.build()), [], e.id)

    def test_toda_deposicao_dopada_tem_temperatura(self):
        """Sem ela o motor responde "The temperature must be specified"."""
        for e in E3.CATALOG:
            for passo in e.build():
                if passo.type != "DEPOSITION":
                    continue
                if passo.params.get("dopant"):
                    self.assertTrue(passo.params.get("temperature"), e.id)


@unittest.skipUnless(tem_motor(), "SUPREM-III não está instalado")
class TestContraOMotor(unittest.TestCase):
    """Cada receita roda, e os números do catálogo são os do motor."""

    @classmethod
    def _rodar(cls, ex: E3.Example3):
        passos = [{"type": s.type, "params": s.params} for s in ex.build()]
        texto = deck.build_in_file(ex.title, passos)
        return suprem.SupremRunner(texto).execute()

    def test_as_receitas_rodam_sem_erro(self):
        for e in E3.CATALOG:
            with self.subTest(exemplo=e.id):
                r = self._rodar(e)
                bruto = r.files.get("OUTPUT.OUT", {}).get("raw", "")
                erros = [l for l in bruto.splitlines() if "Error" in l]
                self.assertEqual(erros, [], f"{e.id}: {erros}")

    def test_a_porta_tem_a_pilha_completa(self):
        r = self._rodar(E3.NMOS_PORTA)
        materiais = [m for m, _ in r.layers()]
        self.assertEqual(materiais, ["POLYSILICON", "OXIDE", "SILICON"])

    def test_o_oxido_de_porta_tem_28_nanometros(self):
        """25 min de O₂ seco a 1000 °C. É o número da descrição."""
        r = self._rodar(E3.NMOS_PORTA)
        espessuras = dict(r.layers())
        self.assertAlmostEqual(espessuras["OXIDE"], 0.028, places=3)

    def test_o_canal_tem_perfil_retrogrado(self):
        """O implante atravessa o óxido de sacrifício: o pico fica abaixo da
        superfície, não nela."""
        r = self._rodar(E3.NMOS_PORTA)
        perfil = [(d, c) for d, c in r.profile() if abs(c) > 1e9]
        self.assertTrue(perfil)
        superficie = perfil[0]
        pico = min(perfil, key=lambda p: p[1])      # mais negativo = mais p
        self.assertGreater(pico[0], superficie[0])
        self.assertAlmostEqual(pico[0], 0.122, places=2)
        self.assertAlmostEqual(abs(pico[1]) / 1e16, 2.66, places=1)

    def test_o_canal_e_todo_tipo_p(self):
        """Sem fonte nem dreno, não há junção no corte de porta."""
        r = self._rodar(E3.NMOS_PORTA)
        perfil = [c for _, c in r.profile() if abs(c) > 1e9]
        self.assertTrue(all(c < 0 for c in perfil))

    def test_fonte_e_dreno_tem_juncao(self):
        r = self._rodar(E3.NMOS_FONTE_DRENO)
        perfil = [(d, c) for d, c in r.profile() if abs(c) > 1e9]
        trocas = [(d0, c0, d1, c1) for (d0, c0), (d1, c1)
                  in zip(perfil, perfil[1:]) if c0 * c1 < 0]
        self.assertEqual(len(trocas), 1)
        d0, c0, d1, c1 = trocas[0]
        xj = d0 + (d1 - d0) * abs(c0) / (abs(c0) + abs(c1))
        self.assertAlmostEqual(xj, 0.203, places=2)

    def test_fonte_e_dreno_e_tipo_n_na_superficie(self):
        r = self._rodar(E3.NMOS_FONTE_DRENO)
        perfil = [(d, c) for d, c in r.profile() if abs(c) > 1e9]
        self.assertGreater(perfil[0][1], 1e20)

    def test_a_porta_e_mais_rasa_que_a_fonte(self):
        """É a diferença que o exemplo pede para comparar."""
        porta = [c for _, c in self._rodar(E3.NMOS_PORTA).profile()
                 if abs(c) > 1e9]
        fonte = [c for _, c in self._rodar(E3.NMOS_FONTE_DRENO).profile()
                 if abs(c) > 1e9]
        self.assertLess(max(abs(c) for c in porta),
                        max(abs(c) for c in fonte))


if __name__ == "__main__":
    unittest.main()
