"""O catálogo da tela de Modelos.

Dois grupos de testes: os que só exercitam a lógica de alterações, e os que
conferem os valores e os cartões contra o motor instalado. Os cartões gerados
foram submetidos ao binário — a lista inteira, com todas as abas, escolhas,
switches e o booleano, passa sem uma mensagem de erro.
"""

from __future__ import annotations

import unittest

from mos_studio.core import models4 as MM


def tem_motor() -> bool:
    from mos_studio.core import modelrc

    return bool(modelrc.records())


class TestGrupos(unittest.TestCase):
    def test_as_seis_abas_do_mockup(self):
        self.assertEqual([g.id for g in MM.GROUPS],
                         ["imp", "method", "ox", "int", "vac", "trap"])

    def test_cada_grupo_tem_titulo_e_descricao(self):
        for g in MM.GROUPS:
            self.assertTrue(g.label and g.title and g.desc, g.id)

    def test_grupo_por_id(self):
        self.assertEqual(MM.group("ox").card, "oxide")
        self.assertIsNone(MM.group("nao.existe"))

    def test_impureza_nao_tem_cartao_fixo(self):
        """Não existe cartão ``impurity``: o cartão é o nome da espécie."""
        g = MM.group("imp")
        self.assertEqual(g.card, "")
        self.assertTrue(g.choice_is_card)
        self.assertEqual(MM.card_name(g, "arsenic"), "arsenic")

    def test_modelos_de_oxidacao_estao_no_method(self):
        """O mockup punha erfc/viscous no cartão ``oxide``."""
        nomes = [sw.name for sw in MM.group("method").switches]
        self.assertEqual(nomes, ["defectm", "oxidem"])
        self.assertEqual(MM.group("ox").switches, ())

    def test_armadilhas_usam_booleano_e_nao_escolha(self):
        """``disable`` não existe; desligar é ``enable=false``."""
        g = MM.group("trap")
        self.assertEqual(g.toggle, "enable")
        self.assertEqual(g.choices, ())


class TestQualificadores(unittest.TestCase):
    def test_especie_leva_o_material(self):
        self.assertEqual(MM.qualifiers(MM.group("imp"), "arsenic"),
                         ("silicon",))

    def test_method_nao_leva_material(self):
        g = MM.group("method")
        self.assertEqual(MM.qualifiers(g, "boron"), ("boron",))

    def test_oxido_leva_o_ambiente(self):
        self.assertEqual(MM.qualifiers(MM.group("ox"), "dry"), ("dry",))

    def test_regime_fino_leva_a_orientacao(self):
        """O motor recusa ``thinox.0`` sem wet/dry *e* orientação."""
        q = MM.qualifiers(MM.group("ox"), "dry", "thinox.0")
        self.assertEqual(q, ("dry", f"orient={MM.ORIENTATION}"))

    def test_fator_de_orientacao_ignora_o_ambiente(self):
        g = MM.group("ox")
        self.assertEqual(MM.qualifiers(g, "dry", "ori.fac"),
                         (f"orient={MM.ORIENTATION}",))
        self.assertEqual(MM.qualifiers(g, "wet", "ori.fac"),
                         MM.qualifiers(g, "dry", "ori.fac"))

    def test_defeitos_pontuais_levam_o_material(self):
        for gid in ("int", "vac", "trap"):
            self.assertEqual(MM.qualifiers(MM.group(gid), ""), ("silicon",))


class TestAlteracoes(unittest.TestCase):
    """A lógica de alterações não precisa do motor."""

    def setUp(self):
        self.m = MM.Models4()
        self.g = MM.group("int")

    def test_projeto_novo_nao_emite_cartao(self):
        self.assertEqual(self.m.count(), 0)
        self.assertEqual(self.m.cards(), [])

    def test_valor_alterado_entra(self):
        self.m.overrides[MM.key_of(self.g, "", "D.0")] = "2e6"
        self.assertEqual(self.m.cards(), ["interstitial silicon D.0=2e6"])

    def test_varios_parametros_na_mesma_linha(self):
        self.m.overrides[MM.key_of(self.g, "", "D.0")] = "2e6"
        self.m.overrides[MM.key_of(self.g, "", "D.E")] = "3.0"
        self.assertEqual(self.m.cards(),
                         ["interstitial silicon D.0=2e6 D.E=3.0"])

    def test_cartoes_diferentes_em_linhas_diferentes(self):
        self.m.overrides[MM.key_of(self.g, "", "D.0")] = "2e6"
        self.m.overrides[MM.key_of(MM.group("vac"), "", "D.0")] = "1e3"
        self.assertEqual(len(self.m.cards()), 2)

    def test_escolhas_diferentes_em_linhas_diferentes(self):
        imp = MM.group("imp")
        self.m.overrides[MM.key_of(imp, "arsenic", "Dix.0")] = "0.1"
        self.m.overrides[MM.key_of(imp, "boron", "Dix.0")] = "0.2"
        self.assertEqual(self.m.cards(),
                         ["arsenic silicon Dix.0=0.1",
                          "boron silicon Dix.0=0.2"])

    def test_restaurar_limpa_so_a_aba(self):
        self.m.overrides[MM.key_of(self.g, "", "D.0")] = "2e6"
        self.m.overrides[MM.key_of(MM.group("vac"), "", "D.0")] = "1e3"
        self.m.reset(self.g, "")
        self.assertEqual(self.m.cards(), ["vacancy silicon D.0=1e3"])

    def test_restaurar_tudo(self):
        self.m.overrides[MM.key_of(self.g, "", "D.0")] = "2e6"
        self.m.switches["method|defectm"] = "full.cpl"
        self.m.toggles["trap|_"] = False
        self.m.reset_all()
        self.assertEqual(self.m.count(), 0)
        self.assertEqual(self.m.cards(), [])

    def test_alteracao_de_parametro_inexistente_e_descartada(self):
        """Uma alteração salva de uma versão anterior não quebra o deck."""
        self.m.overrides[MM.key_of(self.g, "", "nao.existe")] = "1"
        self.assertEqual(self.m.cards(), [])

    def test_alteracao_de_grupo_inexistente_e_descartada(self):
        self.m.overrides["grupo.que.foi|_|D.0"] = "1"
        self.assertEqual(self.m.cards(), [])

    def test_switch_vale_para_a_execucao_toda(self):
        """``method full.cpl``, nunca ``method boron full.cpl``."""
        g = MM.group("method")
        self.m.switches[f"{g.id}|defectm"] = "full.cpl"
        self.assertEqual(self.m.cards(), ["method full.cpl"])

    def test_os_dois_switches_na_mesma_linha(self):
        self.m.switches["method|defectm"] = "full.cpl"
        self.m.switches["method|oxidem"] = "compress"
        self.assertEqual(self.m.cards(), ["method compress full.cpl"])

    def test_desligar_booleano(self):
        self.m.toggles["trap|_"] = False
        self.assertEqual(self.m.cards(), ["trap silicon enable=false"])

    def test_ligar_booleano(self):
        self.m.toggles["trap|_"] = True
        self.assertEqual(self.m.cards(), ["trap silicon enable"])

    def test_parametro_de_escopo_comum_sai_uma_vez(self):
        """``ori.fac`` não depende do ambiente; aparece nas duas abas."""
        g = MM.group("ox")
        self.m.overrides[MM.key_of(g, "dry", "ori.fac")] = "0.6"
        self.m.overrides[MM.key_of(g, "wet", "ori.fac")] = "0.6"
        self.assertEqual(self.m.cards(),
                         [f"oxide orient={MM.ORIENTATION} ori.fac=0.6"])


@unittest.skipUnless(tem_motor(), "SUPREM-IV não está instalado")
class TestContraOMotor(unittest.TestCase):
    """Os valores e os nomes vêm dos arquivos do motor."""

    def test_valor_vem_do_modelrc(self):
        v, origem = MM.effective("interstitial", "D.0", "silicon")
        self.assertEqual(v, "1.03e6")
        self.assertEqual(origem, "modelrc")

    def test_valor_cai_na_gramatica_quando_o_modelrc_nao_diz(self):
        v, origem = MM.effective("arsenic", "Ctn.E", "oxide")
        self.assertEqual(origem, "suprem.key")

    def test_arsenio_mostra_os_coeficientes_reais(self):
        """O mockup mostrava ``Dix.0=8.0``."""
        linhas = {r.name: r.value for r in MM.rows(MM.group("imp"), "arsenic")}
        self.assertEqual(linhas["Dix.0"], "0.0666")
        self.assertEqual(linhas["Dim.0"], "12.8")

    def test_intersticios_mostram_os_coeficientes_reais(self):
        linhas = {r.name: r.value for r in MM.rows(MM.group("int"), "")}
        self.assertEqual(linhas["D.0"], "1.03e6")
        self.assertEqual(linhas["Cstar.0"], "3.11e19")

    def test_a_lista_de_parametros_muda_com_a_especie(self):
        imp = MM.group("imp")
        nomes = lambda e: [r.name for r in MM.rows(imp, e)]   # noqa: E731
        self.assertIn("Fi", nomes("arsenic"))
        self.assertNotIn("Fi", nomes("phosphorus"))
        self.assertIn("Dvx.0", nomes("phosphorus"))
        self.assertIn("Dip.0", nomes("boron"))

    def test_campo_sem_valor_no_motor_nao_aparece(self):
        """No O₂ seco o joelho está em 0 °C: o ramo baixo não tem coeficiente."""
        secos = [r.name for r in MM.rows(MM.group("ox"), "dry")]
        umidos = [r.name for r in MM.rows(MM.group("ox"), "wet")]
        self.assertNotIn("lin.l.0", secos)
        self.assertIn("lin.l.0", umidos)

    def test_tolerancia_muda_com_a_equacao(self):
        g = MM.group("method")
        val = lambda e: {r.name: r.value for r in MM.rows(g, e)}  # noqa: E731
        self.assertEqual(val("interstitial")["abs.error"], "1.0e5")
        self.assertEqual(val("arsenic")["abs.error"], "1.0e9")

    def test_toda_linha_tem_unidade_e_significado(self):
        for g in MM.GROUPS:
            for esc in [c.id for c in g.choices] or [""]:
                for r in MM.rows(g, esc):
                    self.assertTrue(r.unit, f"{g.id}/{esc}/{r.name}")
                    self.assertTrue(r.meaning, f"{g.id}/{esc}/{r.name}")

    def test_nenhuma_linha_vem_sem_valor(self):
        for g in MM.GROUPS:
            for esc in [c.id for c in g.choices] or [""]:
                for r in MM.rows(g, esc):
                    self.assertTrue(r.value.strip(), f"{g.id}/{esc}/{r.name}")

    def test_padrao_dos_switches(self):
        """O ``suprem.key`` diz erfc, o modelrc troca por vertical."""
        g = MM.group("method")
        defectm, oxidem = g.switches
        self.assertEqual(MM.engine_switch(g, defectm), "fermi")
        self.assertEqual(MM.engine_switch(g, oxidem), "vertical")

    def test_armadilhas_vem_ligadas_no_silicio(self):
        self.assertTrue(MM.engine_toggle(MM.group("trap"), ""))

    def test_valor_igual_ao_padrao_nao_e_alteracao(self):
        m = MM.Models4()
        g = MM.group("int")
        m.set(g, "", "D.0", "1.03e6")
        self.assertEqual(m.count(), 0)
        m.set(g, "", "D.0", "2e6")
        self.assertEqual(m.count(), 1)

    def test_campo_apagado_volta_ao_padrao(self):
        m = MM.Models4()
        g = MM.group("int")
        m.set(g, "", "D.0", "2e6")
        m.set(g, "", "D.0", "")
        self.assertEqual(m.count(), 0)

    def test_switch_igual_ao_do_motor_nao_e_alteracao(self):
        m = MM.Models4()
        g = MM.group("method")
        m.set_switch(g, g.switches[1], "vertical")
        self.assertEqual(m.count(), 0)
        m.set_switch(g, g.switches[1], "compress")
        self.assertEqual(m.cards(), ["method compress"])

    def test_booleano_igual_ao_do_motor_nao_e_alteracao(self):
        m = MM.Models4()
        g = MM.group("trap")
        m.set_toggle(g, True)
        self.assertEqual(m.count(), 0)
        m.set_toggle(g, False)
        self.assertEqual(m.cards(), ["trap silicon enable=false"])

    def test_opcao_do_method_sai_truncada(self):
        """``method interstitial`` é recusado pelo motor; ``interstitia`` não."""
        m = MM.Models4()
        g = MM.group("method")
        m.overrides[MM.key_of(g, "interstitial", "rel.error")] = "0.02"
        self.assertEqual(m.cards(), ["method interstitia rel.error=0.02"])

    def test_todo_cartao_gerado_usa_nome_que_o_motor_conhece(self):
        from mos_studio.core import keyfile, suprem4

        m = MM.Models4()
        for g in MM.GROUPS:
            for esc in [c.id for c in g.choices] or [""]:
                for r in MM.rows(g, esc):
                    m.overrides[MM.key_of(g, esc, r.name)] = r.default
            for sw in g.switches:
                m.switches[f"{g.id}|{sw.name}"] = sw.options[-1].id
            if g.toggle:
                m.toggles[f"{g.id}|_"] = False
        cartoes = m.cards()
        self.assertEqual(suprem4.unknown_cards("\n".join(cartoes)), [])
        for linha in cartoes:
            nome, *resto = linha.split()
            c = keyfile.card(nome)
            self.assertIsNotNone(c, linha)
            for tok in resto:
                chave = tok.split("=", 1)[0]
                self.assertIsNotNone(c.get(chave), f"{chave} em {linha}")


if __name__ == "__main__":
    unittest.main()
