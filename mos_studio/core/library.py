"""Receitas embutidas: conteúdo editável, não código.

São as receitas que a tela inicial oferece. Cada uma é uma lista de etapas
igual à que o usuário monta à mão — abrir uma receita da biblioteca é o mesmo
que tê-la digitado. O usuário pode salvar as suas aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .recipe import Step


@dataclass(frozen=True)
class Recipe:
    """Uma receita pronta."""

    key: str
    name: str
    emphasis: str
    tag: str
    description: str
    title: str
    steps: tuple[tuple[str, dict[str, Any]], ...] = ()

    def build(self) -> list[Step]:
        """Cria as etapas (identidades novas a cada chamada)."""
        return [Step(t, dict(p)) for t, p in self.steps]

    @property
    def step_count(self) -> int:
        return len(self.steps)


def _init(thickness: str = "0.5", dopant: str = "BORON",
          conc: str = "1E15", dx: str = "5E-3",
          orientation: str = "100") -> tuple[str, dict]:
    return ("INITIALIZE", {"orientation": orientation, "dopant": dopant,
                           "concentration": conc, "dx": dx,
                           "thickness": thickness})


def _diff(ambient: str, temp: str, time: str, gas: str = "") -> tuple[str, dict]:
    return ("DIFFUSION", {"ambient": ambient, "temperature": temp, "time": time,
                          "gasConc": gas, "solidSol": False, "tRate": ""})


def _etch(material: str = "OXIDE") -> tuple[str, dict]:
    return ("ETCH", {"material": material, "all": True, "thickness": ""})


def _dep(material: str, thickness: str) -> tuple[str, dict]:
    return ("DEPOSITION", {"material": material, "thickness": thickness,
                           "dopant": "", "concentration": "", "temperature": ""})


def _imp(dopant: str, dose: str, energy: str) -> tuple[str, dict]:
    return ("IMPLANTI", {"dopant": dopant, "dose": dose, "energy": energy,
                         "distribution": ""})


def _print(extra: str = "CONCENTR", filename: str = "PERFIL.OUT",
           what: str = "NET") -> tuple[str, dict]:
    return ("PRINT", {"what": what, "curve": "ACTIVE" if extra == "CONCENTR" else "",
                      "extra": extra, "filename": filename, "linespa": "1000"})


RECIPES: tuple[Recipe, ...] = (
    Recipe(
        key="diodo-pn",
        name="Diodo PN",
        emphasis="por difusão",
        tag="Embutida",
        description="Substrato p, pré-deposição de fósforo, recozimento em N₂ "
                    "e metalização.",
        title="DIODO PN - DIFUSAO DE FOSFORO EM SILICIO TIPO P",
        steps=(
            _init(),
            _diff("DRYO2", "1000", "15"),
            _etch(),
            _diff("PHOSPHOR", "1000", "30", "1E18"),
            _diff("NITROGEN", "900", "15"),
            _print("CONCENTR", "DIODED.OUT"),
            _dep("OXIDE", "0.2"),
            _etch(),
            _dep("ALUMINUM", "0.4"),
            _print("LAYER", "DIODEL.OUT"),
        ),
    ),
    Recipe(
        key="fonte-dreno-nmos",
        name="Fonte e dreno",
        emphasis="NMOS",
        tag="Embutida",
        description="Óxido de porta, implantação de arsênio e recozimento de "
                    "ativação.",
        title="NMOS - FONTE E DRENO POR IMPLANTACAO DE ARSENIO",
        steps=(
            _init(thickness="1.0", conc="1E16"),
            _diff("DRYO2", "1000", "30"),
            _imp("ARSENIC", "2E15", "80"),
            _diff("NITROGEN", "1000", "30"),
            _etch(),
            _print("CONCENTR", "SDPERF.OUT"),
            _print("LAYER", "SDCAM.OUT"),
        ),
    ),
    Recipe(
        key="poco-n",
        name="Poço N",
        emphasis="por implantação",
        tag="Embutida",
        description="Implantação de fósforo em alta energia seguida de "
                    "drive-in longo.",
        title="POCO N - IMPLANTACAO DE FOSFORO E DRIVE-IN",
        steps=(
            _init(thickness="8.0", dx="4E-2"),
            _diff("DRYO2", "1000", "20"),
            _imp("PHOSPHOR", "3E12", "160"),
            _diff("NITROGEN", "1150", "600"),
            _etch(),
            _print("CONCENTR", "POCO.OUT"),
            _print("LAYER", "POCOCAM.OUT"),
        ),
    ),
    Recipe(
        key="oxidacao",
        name="Oxidação",
        emphasis="seca e úmida",
        tag="Embutida",
        description="Crescimento de óxido para comparar os regimes linear e "
                    "parabólico.",
        title="OXIDACAO - COMPARACAO SECA E UMIDA",
        steps=(
            _init(),
            _diff("DRYO2", "1000", "40"),
            _print("LAYER", "OXSECO.OUT"),
            _diff("WETO2", "1000", "40"),
            _print("LAYER", "OXUMIDO.OUT"),
        ),
    ),
    Recipe(
        key="epitaxia",
        name="Epitaxia",
        emphasis="sobre n⁺",
        tag="Embutida",
        description="Camada epitaxial levemente dopada sobre substrato "
                    "degenerado.",
        title="EPITAXIA - CAMADA N SOBRE SUBSTRATO N+",
        steps=(
            _init(thickness="1.0", dopant="ANTIMONY", conc="1E19"),
            ("EPITAXY", {"dopant": "PHOSPHOR", "thickness": "1.5",
                         "concentration": "1E16", "temperature": "1100",
                         "growthRate": "0.5"}),
            _diff("NITROGEN", "1000", "30"),
            _print("CONCENTR", "EPIPERF.OUT"),
            _print("LAYER", "EPICAM.OUT"),
        ),
    ),
    Recipe(
        key="em-branco",
        name="Receita",
        emphasis="em branco",
        tag="Nova",
        description="Só a Inicialização. Monte o processo etapa por etapa.",
        title="NOVA SIMULACAO",
        steps=(_init(),),
    ),
)

BY_KEY = {r.key: r for r in RECIPES}


def get(key: str) -> Recipe:
    """Receita pela chave; a primeira da lista se a chave não existir."""
    return BY_KEY.get(key, RECIPES[0])
