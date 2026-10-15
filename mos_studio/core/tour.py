"""Os dois roteiros guiados: o passeio pela interface e o projeto LDD.

São dados, não interface: cada passo diz em que widget o destaque cai, o que
explicar, que ação pedir e como saber que ela foi feita. Quem desenha é
:mod:`mos_studio.ui.widgets.tour_overlay`.

O projeto guiado monta o ``exam5`` do manual — o transistor LDD — etapa por
etapa, e cada etapa é um cartão que o motor aceita. Dois cartões do roteiro
original foram corrigidos depois de o binário os recusar:

* ``initialize silicon boron conc=1e15`` → o ``initialize`` não tem parâmetro
  ``silicon``; o material da lâmina vem do cartão ``region``;
* ``diffuse time=30 temp=950 inert`` → não existe ``inert``; o ambiente
  inerte é ``nitrogen`` ou ``argon``.

Com essas duas correções o roteiro inteiro roda sem recusa e grava a
estrutura (conferido: junção a 0,257 µm em x = 0,8 µm).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Step:
    """Um passo de um roteiro."""

    title: str
    text: str
    #: Nome do widget que recebe o destaque (ver ``tour_overlay``). Vazio
    #: centraliza o cartão, para abertura e encerramento.
    target: str = ""
    #: O que pedir ao usuário. Vazio = passo só de leitura.
    action: str = ""
    #: Cartão do deck que este passo ilustra.
    card: str = ""
    #: ``(janela) -> bool``: a ação foi feita?
    done: Callable[[object], bool] | None = None
    #: ``(janela) -> None``: faz a ação em lugar do usuário, quando ele
    #: escolhe pular. Sem isto, pular um passo avançava o texto mas deixava o
    #: aplicativo onde estava — quem pulasse tudo terminava o passeio sem
    #: nunca sair da tela de Início.
    perform: Callable[[object], None] | None = None


def _area(nome: str) -> Callable[[object], bool]:
    return lambda w: getattr(w, "current_area", lambda: "")() == nome


def _go(nome: str) -> Callable[[object], None]:
    """Leva a janela àquela tela, para quem pula o passo."""
    return lambda w: w.go(nome)


def _set_dim(dim: str) -> Callable[[object], None]:
    return lambda w: w.set_dimension(dim)


#: O passeio pelas telas do motor 2-D, como no arquivo de design.
UI_TOUR: tuple[Step, ...] = (
    Step("Bem-vindo ao MOS-Studio",
         "Este passeio percorre as telas do motor 2-D. Os destaques ficam "
         "sobre a interface de verdade. Quando o cartão pedir uma ação, "
         "faça você mesmo."),
    Step("Escolha o motor",
         "Cada projeto roda em 1-D (SUPREM-III) ou em 2-D (SUPREM-IV). O "
         "2-D resolve a seção transversal inteira do dispositivo, com "
         "difusão lateral e geometria.",
         target="dim", action="Clique em 2-D",
         done=lambda w: getattr(w, "dimension", "") == "2d",
         perform=_set_dim("2d")),
    Step("Malha",
         "No SUPREM-IV tudo começa pela malha: cada cartão line fixa uma "
         "posição e o espaçamento naquele ponto. No SUPREM-III isso era "
         "implícito.",
         target="nav-malha", action="Abra Malha", done=_area("malha"),
         perform=_go("malha")),
    Step("Linhas e espaçamento",
         "Diminua um spacing perto da superfície e veja a malha refinar. "
         "Entre duas linhas o motor subdivide por progressão geométrica, "
         "com razão limitada a 1,5 — por isso a contagem de nós nem sempre "
         "é a que a divisão simples sugeriria.",
         target="mesh-lines", card="line y loc=0 spacing=0.02 tag=topo"),
    Step("Pré-visualização",
         "Cada mudança recalcula a malha que o motor vai gerar, não a que "
         "você digitou. A linha laranja no topo é a superfície exposta, por "
         "onde a oxidação e a deposição entram.",
         target="mesh-preview"),
    Step("Receita 2-D",
         "As etapas seguem a ordem física do processo, e o deck à direita é "
         "o arquivo que vai para o motor.",
         target="nav-processo2d", action="Abra Processo",
         done=_area("processo2d"), perform=_go("processo2d")),
    Step("Etapas e deck",
         "Clique numa etapa para editá-la; clique numa linha do deck para "
         "voltar à etapa que a gerou. A corrosão em 2-D tem forma: à "
         "esquerda de uma reta, por coordenadas, ou descendo uma espessura.",
         target="recipe2d"),
    Step("Resultados 2-D",
         "Contornos de concentração sobre a estrutura que o motor "
         "construiu. O desenho sai dos números: esta compilação não tem "
         "camada gráfica, então a seção é varrida com cortes print.1d.",
         target="nav-resultados2d", action="Abra Resultados",
         done=_area("resultados2d"), perform=_go("resultados2d")),
    Step("Corte 1-D",
         "Mova o controle para deslocar o corte vertical. A profundidade de "
         "junção é remedida no ponto, a partir da superfície do silício.",
         target="cut", action="Mova o corte",
         done=lambda w: getattr(w, "_tour_cut_moved", False),
         perform=lambda w: w.resultados2d._slider.setValue(
             int(w.resultados2d._slider.value() * 0.6) or 30)),
    Step("Modelos físicos",
         "Coeficientes de impurezas, óxido, interstícios, vacâncias e "
         "armadilhas, lidos do modelrc da instalação. Só o que você alterar "
         "entra no deck.",
         target="nav-modelos", action="Abra Modelos", done=_area("modelos"),
         perform=_go("modelos")),
    Step("Console",
         "O motor é um shell: aceita define, foreach, source e help, e "
         "guarda o estado entre os comandos.",
         target="tool-console", action="Abra o Console",
         done=_area("console"), perform=_go("console")),
    Step("Pergunte ao motor",
         "Digite help diffuse e tecle Enter: sai a gramática do cartão, com "
         "o tipo e a unidade de cada parâmetro.",
         target="console-input", card="help diffuse",
         action="Digite um comando",
         done=lambda w: getattr(w, "console", None) is not None
         and w.console.used(),
         perform=lambda w: w.console.run("help diffuse")),
    Step("Simular",
         "Com a receita pronta, Simular manda o deck ao motor e já pede a "
         "varredura que desenha o resultado. Ctrl+R faz o mesmo de qualquer "
         "tela. Fim do passeio.",
         target="run"),
)


@dataclass(frozen=True)
class RecipeStep:
    """Uma etapa do projeto guiado, com a etapa da receita que ela cria."""

    label: str
    text: str
    card: str
    type: str
    params: dict = field(default_factory=dict)


#: As doze etapas do transistor LDD (``exam5`` do manual), cada uma com os
#: parâmetros que a tela de Processo 2-D vai receber.
LDD_STEPS: tuple[RecipeStep, ...] = (
    RecipeStep("Inicialização",
               "Substrato tipo p ⟨100⟩ com 10¹⁵ cm⁻³ de boro. A malha já vem "
               "da tela de Malha; o material da lâmina vem do cartão region, "
               "não do initialize.",
               "initialize boron conc=1e15 orient=100",
               "INIT", {"impurity": "boron", "conc": "1E15",
                        "orient": "100"}),
    RecipeStep("Óxido de porta",
               "Trinta minutos de O₂ seco a 1000 °C crescem cerca de 25 nm "
               "de óxido sobre toda a superfície exposta.",
               "diffuse temp=1000 time=30 dryo2",
               "DIFFUSE", {"ambient": "dryo2", "temp": "1000", "time": "30"}),
    RecipeStep("Polissilício",
               "A camada de porta, com 0,5 µm e seis divisões verticais na "
               "malha da camada nova.",
               "deposit poly thick=0.5 divisions=6",
               "DEPOSIT", {"material": "poly", "thick": "0.5",
                           "divisions": "6"}),
    RecipeStep("Definição da porta",
               "Remove o poli à direita de x = 0,35 µm. Só metade do "
               "dispositivo é simulada: a borda esquerda é plano de simetria.",
               "etch poly right p1.x=0.35",
               "ETCH", {"material": "poly", "mode": "right", "p1x": "0.35"}),
    RecipeStep("Método numérico",
               "Difusão pelo modelo de Fermi e óxido compressível nas etapas "
               "seguintes. Fermi ignora os defeitos pontuais e é o mais "
               "rápido.",
               "method fermi compress",
               "METHOD", {"model": "fermi", "oxide": "compress"}),
    RecipeStep("Implantação da extensão",
               "Dose baixa de arsênio, autoalinhada à borda da porta: é a "
               "extensão que dá o nome ao LDD.",
               "implant arsenic dose=5e13 energy=50",
               "IMPLANT", {"impurity": "arsenic", "dose": "5E13",
                           "energy": "50", "model": "pearson"}),
    RecipeStep("Óxido do espaçador",
               "Óxido conforme sobre tudo, que a corrosão seguinte vai "
               "transformar em espaçador lateral.",
               "deposit oxide thick=0.4 divisions=4",
               "DEPOSIT", {"material": "oxide", "thick": "0.4",
                           "divisions": "4"}),
    RecipeStep("Corrosão do espaçador",
               "Corrosão anisotrópica, descendo uma espessura: o óxido só "
               "sobra encostado na parede da porta.",
               "etch oxide dry thick=0.42",
               "ETCH", {"material": "oxide", "mode": "dry", "thick": "0.42"}),
    RecipeStep("Implantação de fonte e dreno",
               "Dose alta de arsênio, afastada da porta pela largura do "
               "espaçador. É o que faz a junção funda das duas pontas.",
               "implant arsenic dose=5e15 energy=80",
               "IMPLANT", {"impurity": "arsenic", "dose": "5E15",
                           "energy": "80", "model": "pearson"}),
    RecipeStep("Saída do motor",
               "Reduz o texto que o motor imprime durante o recozimento, que "
               "é a etapa mais demorada.",
               "option quiet",
               "OPTION", {"quiet": True}),
    RecipeStep("Recozimento",
               "Ativa e redistribui o arsênio: sem isto a dopagem líquida "
               "nem enxerga o implante. A junção avança por baixo do "
               "espaçador. O ambiente inerte é nitrogen — não existe inert.",
               "diffuse temp=950 time=30 nitrogen",
               "DIFFUSE", {"ambient": "nitrogen", "temp": "950",
                           "time": "30"}),
    RecipeStep("Salvar a estrutura",
               "Grava malha e soluções, para reabrir depois sem refazer o "
               "processo ou exportar para o simulador de dispositivo.",
               "structure out=ldd.str",
               "STRUCTURE", {"outfile": "ldd.str"}),
)


def ldd_tour() -> tuple[Step, ...]:
    """O roteiro do projeto guiado, montado das doze etapas."""
    passos: list[Step] = [
        Step("Transistor LDD, etapa por etapa",
             "Você vai montar o exam5 do manual do SUPREM-IV. A malha já "
             "está pronta; cada passo acrescenta uma etapa à receita e "
             "explica o que ela faz na lâmina.")]
    for i, s in enumerate(LDD_STEPS):
        passos.append(Step(
            f"{i + 1:02d} · {s.label}", s.text, target="addstep",
            action="Acrescente esta etapa", card=s.card,
            done=(lambda n: (lambda w: _built(w) > n))(i),
            perform=lambda w: w.add_guided_step()))
    passos.append(Step(
        "Estrutura completa",
        "As doze etapas estão na receita. Abra Resultados para ver os "
        "contornos e a junção.",
        target="nav-resultados2d", action="Abra Resultados",
        done=_area("resultados2d"), perform=_go("resultados2d")))
    passos.append(Step(
        "Pronto",
        "Mova o corte para comparar a junção sob o espaçador (x ≈ 0,45 µm) "
        "com a de fonte e dreno (x ≈ 0,9 µm). A primeira é a extensão de "
        "dose baixa; a segunda, o contato."
        , target="cut"))
    return tuple(passos)


def _built(window) -> int:
    """Quantas etapas do roteiro já estão na receita 2-D."""
    tela = getattr(window, "processo2d", None)
    return len(getattr(tela, "steps", [])) if tela is not None else 0
