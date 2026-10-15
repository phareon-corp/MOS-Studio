"""Exemplos 1-D do MOS-Studio, para o SUPREM-III.

A aba de Exemplos mostra duas coisas: os decks de fábrica do SUPREM-IV
(:mod:`examples4`), que são texto e rodam como estão, e estes — receitas 1-D
escritas para este aplicativo, que **abrem como projeto**: viram etapas na
tela de Processo, perfil na de Resultados, e podem seguir para o MINIMOS.

A diferença importa. Um deck de fábrica se lê; uma receita destas se edita:
mude a dose do implante e rode de novo para ver a junção andar.

Todos os números aqui foram conferidos rodando o deck no binário, e os
comentários dizem o que o motor devolveu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .recipe import Step

#: Teto de pontos de malha do SUPREM-III (``recipe.MAX_GRID_POINTS``). Toda
#: receita daqui tem de caber nele contando as camadas depositadas, que
#: acrescentam nós: ``THICKNES/DX`` mais o que vier depois.
GRID_LIMIT = 500


@dataclass(frozen=True)
class Example3:
    """Um exemplo 1-D, pronto para virar projeto."""

    id: str
    name: str
    emphasis: str
    desc: str
    title: str
    steps: tuple[tuple[str, dict[str, Any]], ...]
    #: O que olhar no resultado, com os valores que o motor devolveu aqui.
    expect: str = ""

    dim: str = "1-D"
    engine: str = "SUPREM-III"

    def build(self) -> list[Step]:
        """Etapas novas (identidades próprias a cada chamada)."""
        return [Step(t, dict(p)) for t, p in self.steps]

    @property
    def step_count(self) -> int:
        return len(self.steps)


def _init(thickness: str, conc: str, dx: str = "5E-3",
          dopant: str = "BORON", orientation: str = "100") -> tuple[str, dict]:
    return ("INITIALIZE", {"orientation": orientation, "dopant": dopant,
                           "concentration": conc, "dx": dx,
                           "thickness": thickness})


def _diff(ambient: str, temp: str, time: str, gas: str = "") -> tuple[str, dict]:
    return ("DIFFUSION", {"ambient": ambient, "temperature": temp,
                          "time": time, "gasConc": gas, "solidSol": False,
                          "tRate": ""})


def _imp(dopant: str, dose: str, energy: str) -> tuple[str, dict]:
    return ("IMPLANTI", {"dopant": dopant, "dose": dose, "energy": energy,
                         "distribution": ""})


def _etch(material: str = "OXIDE") -> tuple[str, dict]:
    return ("ETCH", {"material": material, "all": True, "thickness": ""})


def _dep(material: str, thickness: str, dopant: str = "", conc: str = "",
         temp: str = "") -> tuple[str, dict]:
    # Uma deposição dopada exige temperatura: sem ela o motor responde
    # "The temperature must be specified" (erro 150).
    return ("DEPOSITION", {"material": material, "thickness": thickness,
                           "dopant": dopant, "concentration": conc,
                           "temperature": temp})


def _print(extra: str, filename: str) -> tuple[str, dict]:
    return ("PRINT", {"what": "NET",
                      "curve": "ACTIVE" if extra == "CONCENTR" else "",
                      "extra": extra, "filename": filename,
                      "linespa": "1000"})


#: O transistor NMOS visto em uma dimensão.
#:
#: Em 1-D não existe transistor inteiro — não há fonte, dreno nem comprimento
#: de canal. O que existe, e é o que esta receita simula, é o **corte vertical
#: no meio do canal**: substrato, implante de ajuste de limiar, óxido de porta
#: e porta de polissilício. É esse corte que define a tensão de limiar, e é
#: ele que o MINIMOS recebe pela tela de Dispositivo.
#:
#: Conferido no binário: óxido de porta de 28 nm, canal com 2,21×10¹⁶ cm⁻³ na
#: superfície e pico de 2,66×10¹⁶ cm⁻³ a 0,12 µm — o perfil retrógrado típico
#: de um implante de ajuste através de óxido de sacrifício.
NMOS_PORTA = Example3(
    id="nmos-porta",
    name="Transistor NMOS",
    emphasis="região de porta",
    desc="O corte vertical no meio do canal: implante de ajuste de limiar, "
         "óxido de porta e porta de polissilício. É o que define a tensão de "
         "limiar — e o que o MINIMOS recebe para simular o dispositivo.",
    title="NMOS - REGIAO DE PORTA",
    expect="Óxido de porta de 28 nm e canal com pico de 2,7×10¹⁶ cm⁻³ a "
           "0,12 µm da superfície.",
    steps=(
        # 240 nós aqui; a porta de poli acrescenta 35 e sobra folga no teto.
        _init(thickness="1.2", conc="1E15"),
        # Óxido de sacrifício: espalha o implante e protege a superfície.
        _diff("DRYO2", "900", "20"),
        # Ajuste da tensão de limiar. Atravessa o óxido de sacrifício, por
        # isso o pico fica abaixo da superfície e não nela.
        _imp("BORON", "1E12", "40"),
        _etch("OXIDE"),
        # Óxido de porta: 25 min de O₂ seco a 1000 °C dão 28 nm.
        _diff("DRYO2", "1000", "25"),
        # O perfil sai aqui, antes da porta: com o poli dopado a 10²⁰ em
        # cima, o canal — mil vezes menor — some do gráfico.
        _print("CONCENTR", "CANAL.OUT"),
        _dep("POLYSILI", "0.35", "PHOSPHOR", "1E20", "620"),
        _diff("NITROGEN", "900", "30"),
        _print("LAYER", "PORTA.OUT"),
    ),
)

#: Fonte e dreno do mesmo transistor, para comparar com a região de porta.
#:
#: Conferido no binário: junção a 0,203 µm, com arsênio a 1,77×10²⁰ cm⁻³ na
#: superfície do silício, sob os mesmos 28 nm de óxido.
NMOS_FONTE_DRENO = Example3(
    id="nmos-fonte-dreno",
    name="Transistor NMOS",
    emphasis="fonte e dreno",
    desc="O corte onde a porta não cobre: implante de arsênio de dose alta e "
         "recozimento de ativação. Compare a junção daqui com a do corte de "
         "porta — é a diferença entre o canal e o contato.",
    title="NMOS - FONTE E DRENO",
    expect="Junção a 0,203 µm, com arsênio a 1,77×10²⁰ cm⁻³ na superfície "
           "do silício.",
    steps=(
        _init(thickness="1.2", conc="1E15"),
        _diff("DRYO2", "900", "20"),
        _imp("BORON", "1E12", "40"),
        _etch("OXIDE"),
        _diff("DRYO2", "1000", "25"),
        # A porta mascararia esta região; aqui ela está aberta.
        _imp("ARSENIC", "5E15", "80"),
        _diff("NITROGEN", "950", "30"),
        _print("CONCENTR", "FONTE.OUT"),
        _print("LAYER", "CAMADAS.OUT"),
    ),
)

CATALOG: tuple[Example3, ...] = (NMOS_PORTA, NMOS_FONTE_DRENO)


def get(example_id: str) -> Example3 | None:
    return next((e for e in CATALOG if e.id == example_id), None)


def grid_points(ex: Example3) -> int:
    """Nós que o ``initialize`` da receita pede.

    Serve de guarda contra o teto de :data:`GRID_LIMIT`: o SUPREM-III recusa
    o deck inteiro com "Maximum number of grid points exceeded", e o erro
    aponta a linha do ``initialize``, não a do excesso.
    """
    for tipo, params in ex.steps:
        if tipo != "INITIALIZE":
            continue
        try:
            return int(float(params["thickness"]) / float(params["dx"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return 0
    return 0
