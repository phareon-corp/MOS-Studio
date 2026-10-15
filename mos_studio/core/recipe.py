"""A receita de processo: tipos de etapa, campos, padrões e verificação.

Esta camada é o vocabulário de domínio da interface. Ela diz, para cada um dos
sete comandos montáveis do SUPREM-III, quais parâmetros existem, como se
chamam em português, em que unidade são digitados e em que faixa fazem sentido.
A tradução para o texto do deck é separada (:mod:`mos_studio.core.deck`) e
preserva os nomes de parâmetro do SUPREM.

PLOT **não** está aqui, de propósito: a biblioteca gráfica do SUPREM-III desta
compilação é um conjunto de stubs vazios e ``strip_plot`` apaga o comando de
todo deck antes de executar. Oferecê-lo no catálogo seria deixar o usuário
montar algo que nunca roda, sem aviso.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Vocabulários do SUPREM-III (valores que vão para o deck) ──────────────

AMBIENTS = ["DRYO2", "WETO2", "NITROGEN", "BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY"]
DOPANTS = ["BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY", "BF2"]
MATERIALS = ["SILICON", "OXIDE", "NITRIDE", "ALUMINUM", "POLYSILI"]
DISTRIBUTIONS = ["GAUSSIAN", "PEARSON", "BOLTZMAN", "2-GAUSSI"]

#: Ambientes de difusão que são fonte de dopante (habilitam GAS.CONC).
DOPING_AMBIENTS = {"BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY"}
#: Ambientes de difusão que crescem óxido.
OXIDIZING_AMBIENTS = {"DRYO2", "WETO2"}

#: Rótulos em português para os valores do deck.
AMBIENT_LABELS = {
    "DRYO2": "O₂ seco", "WETO2": "O₂ úmido", "NITROGEN": "N₂ (inerte)",
    "BORON": "Boro (fonte gasosa)", "PHOSPHOR": "Fósforo (fonte gasosa)",
    "ARSENIC": "Arsênio (fonte gasosa)", "ANTIMONY": "Antimônio (fonte gasosa)",
}
DOPANT_LABELS = {
    "BORON": "Boro", "PHOSPHOR": "Fósforo", "ARSENIC": "Arsênio",
    "ANTIMONY": "Antimônio", "BF2": "BF₂",
}
MATERIAL_LABELS = {
    "SILICON": "Silício", "OXIDE": "Óxido", "NITRIDE": "Nitreto",
    "ALUMINUM": "Alumínio", "POLYSILI": "Polissilício",
}
DISTRIBUTION_LABELS = {
    "GAUSSIAN": "Gaussiana", "PEARSON": "Pearson IV",
    "BOLTZMAN": "Boltzmann", "2-GAUSSI": "Dupla gaussiana",
}
ORIENTATION_LABELS = {"100": "⟨100⟩", "111": "⟨111⟩", "110": "⟨110⟩"}

STEP_LABELS = {
    "INITIALIZE": "Inicialização",
    "DIFFUSION": "Difusão",
    "DEPOSITION": "Deposição",
    "ETCH": "Corrosão",
    "IMPLANTI": "Implantação iônica",
    "EPITAXY": "Epitaxia",
    "PRINT": "Tabela de saída",
}

STEP_DESCRIPTIONS = {
    "INITIALIZE": "Define substrato, orientação e dopagem inicial. "
                  "Sempre a primeira etapa.",
    "DIFFUSION": "Tratamento térmico: oxidação, pré-deposição ou recozimento.",
    "DEPOSITION": "Deposita uma camada de material sobre a superfície.",
    "ETCH": "Remove uma camada, inteira ou por espessura.",
    "IMPLANTI": "Implanta íons com dose e energia definidas.",
    "EPITAXY": "Cresce silício dopado sobre a superfície.",
    "PRINT": "Grava uma tabela de saída. Os gráficos do MOS-Studio vêm daqui.",
}

#: Número máximo de nós de malha que o SUPREM-III aceita (erro 12 acima disso).
MAX_GRID_POINTS = 500

#: Ordem em que os tipos aparecem no catálogo "Adicionar etapa".
STEP_TYPES = ["INITIALIZE", "DIFFUSION", "IMPLANTI", "DEPOSITION", "ETCH",
              "EPITAXY", "PRINT"]


# ── Descrição de um campo de formulário ───────────────────────────────────

@dataclass(frozen=True)
class Field:
    """Um parâmetro editável de uma etapa.

    ``key`` é o nome interno do parâmetro (o mesmo que o gerador de deck
    consome); ``label`` é o rótulo em português; ``unit`` aparece ao lado do
    campo. ``kind`` é ``"number"``, ``"text"``, ``"choice"`` ou ``"bool"``.
    """

    key: str
    label: str
    kind: str = "number"
    unit: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    help: str = ""
    wide: bool = False
    required: bool = True
    #: Quando presente, o campo só aparece se a função aceitar os parâmetros.
    visible_when: Callable[[dict], bool] | None = None

    def visible(self, params: dict) -> bool:
        return self.visible_when is None or bool(self.visible_when(params))


def _choices(values: list[str], labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple((v, labels.get(v, v)) for v in values)


def _is_doping_ambient(p: dict) -> bool:
    return str(p.get("ambient", "")).upper() in DOPING_AMBIENTS


def _etch_by_thickness(p: dict) -> bool:
    return not p.get("all", True)


#: Campos de cada tipo de etapa, na ordem em que aparecem no formulário.
FIELDS: dict[str, tuple[Field, ...]] = {
    "INITIALIZE": (
        Field("orientation", "Orientação cristalina", "choice",
              choices=_choices(["100", "111", "110"], ORIENTATION_LABELS), wide=True),
        Field("dopant", "Dopante do substrato", "choice",
              choices=_choices(DOPANTS[:4], DOPANT_LABELS), wide=True),
        Field("concentration", "Concentração do substrato", "number", "cm⁻³",
              minimum=1e12, maximum=1e21),
        Field("thickness", "Profundidade simulada", "number", "µm",
              minimum=0.05, maximum=20),
        Field("dx", "Passo da malha", "number", "µm", minimum=1e-4, maximum=5e-2,
              help="menor = mais preciso e mais lento"),
    ),
    "DIFFUSION": (
        Field("ambient", "Ambiente", "choice",
              choices=_choices(AMBIENTS, AMBIENT_LABELS), wide=True),
        Field("temperature", "Temperatura", "number", "°C", minimum=700, maximum=1250),
        Field("time", "Tempo", "number", "min", minimum=0.1, maximum=6000),
        Field("gasConc", "Concentração na fonte gasosa", "number", "cm⁻³",
              minimum=1e14, maximum=1e21, visible_when=_is_doping_ambient,
              help="só para ambiente dopante"),
        Field("tRate", "Rampa de temperatura", "number", "°C/min",
              minimum=-100, maximum=100, required=False,
              help="opcional; vazio = temperatura constante"),
        Field("solidSol", "Limitar pela solubilidade sólida", "bool", wide=True,
              required=False),
    ),
    "DEPOSITION": (
        Field("material", "Material", "choice",
              choices=_choices(["OXIDE", "NITRIDE", "POLYSILI", "ALUMINUM", "SILICON"],
                               MATERIAL_LABELS), wide=True),
        Field("thickness", "Espessura", "number", "µm", minimum=1e-3, maximum=10),
        Field("dopant", "Dopante da camada", "choice",
              choices=(("", "Sem dopante"),) + _choices(DOPANTS[:4], DOPANT_LABELS),
              wide=True, required=False),
        Field("concentration", "Concentração da camada", "number", "cm⁻³",
              minimum=1e12, maximum=1e22, required=False,
              help="opcional; use com dopante"),
        Field("temperature", "Temperatura de deposição", "number", "°C",
              minimum=300, maximum=1250, required=False, help="opcional"),
    ),
    "ETCH": (
        Field("material", "Material removido", "choice",
              choices=_choices(["OXIDE", "NITRIDE", "SILICON", "POLYSILI", "ALUMINUM"],
                               MATERIAL_LABELS), wide=True),
        Field("all", "Remover toda a camada", "bool", wide=True, required=False),
        Field("thickness", "Espessura removida", "number", "µm",
              minimum=1e-3, maximum=10, visible_when=_etch_by_thickness),
    ),
    "IMPLANTI": (
        Field("dopant", "Íon implantado", "choice",
              choices=_choices(DOPANTS, DOPANT_LABELS), wide=True),
        Field("dose", "Dose", "number", "cm⁻²", minimum=1e10, maximum=1e17),
        Field("energy", "Energia", "number", "keV", minimum=1, maximum=400),
        Field("distribution", "Distribuição", "choice",
              choices=(("", "Padrão do motor"),)
                      + _choices(DISTRIBUTIONS, DISTRIBUTION_LABELS),
              wide=True, required=False),
    ),
    "EPITAXY": (
        Field("dopant", "Dopante", "choice",
              choices=_choices(DOPANTS[:4], DOPANT_LABELS), wide=True),
        Field("concentration", "Concentração", "number", "cm⁻³",
              minimum=1e12, maximum=1e21),
        Field("thickness", "Espessura crescida", "number", "µm",
              minimum=1e-2, maximum=50),
        Field("temperature", "Temperatura", "number", "°C", minimum=900, maximum=1250),
        Field("growthRate", "Taxa de crescimento", "number", "µm/min",
              minimum=1e-3, maximum=10),
    ),
    "PRINT": (
        Field("what", "Grandeza", "choice",
              choices=(("NET", "Concentração líquida"),
                       ("BORON", "Boro"), ("PHOSPHOR", "Fósforo"),
                       ("ARSENIC", "Arsênio"), ("ANTIMONY", "Antimônio"),
                       ("OXIDE", "Óxido"), ("ALL", "Tudo")), wide=True),
        Field("curve", "Forma", "choice",
              choices=(("ACTIVE", "Ativa"), ("CHEMICAL", "Química"), ("", "Não aplicável")),
              wide=True, required=False),
        Field("extra", "Tabela", "choice",
              choices=(("CONCENTR", "Concentração por profundidade"),
                       ("LAYER", "Camadas"), ("IMPURITY", "Impurezas"),
                       ("MATERIAL", "Materiais"), ("OXIDATIO", "Oxidação")),
              wide=True),
        Field("filename", "Arquivo de saída", "text",
              help="até 8 caracteres + extensão"),
        Field("linespa", "Linhas por página", "number", "linhas",
              minimum=10, maximum=10000),
    ),
}


#: Valores iniciais de cada tipo de etapa — os mesmos da versão Tkinter.
DEFAULTS: dict[str, dict[str, Any]] = {
    "INITIALIZE": {"orientation": "100", "dopant": "BORON", "concentration": "1E15",
                   "dx": "5E-3", "thickness": "0.5"},
    "DIFFUSION": {"ambient": "DRYO2", "temperature": "1000", "time": "15",
                  "gasConc": "", "solidSol": False, "tRate": ""},
    "DEPOSITION": {"material": "ALUMINUM", "thickness": "0.4", "dopant": "",
                   "concentration": "", "temperature": ""},
    "ETCH": {"material": "OXIDE", "all": True, "thickness": ""},
    "IMPLANTI": {"dopant": "BORON", "energy": "45", "dose": "1E13",
                 "distribution": ""},
    "EPITAXY": {"dopant": "PHOSPHOR", "thickness": "1.0", "concentration": "5E15",
                "temperature": "1000", "growthRate": "0.5"},
    "PRINT": {"what": "NET", "curve": "ACTIVE", "extra": "CONCENTR",
              "filename": "OUTPUT.OUT", "linespa": "1000"},
}


# ── Etapa e receita ───────────────────────────────────────────────────────

_ids = itertools.count(1)


@dataclass
class Step:
    """Uma etapa da receita. ``params`` usa as chaves do gerador de deck."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    uid: int = field(default_factory=lambda: next(_ids))

    @classmethod
    def new(cls, step_type: str) -> "Step":
        """Cria uma etapa do tipo pedido, com os valores padrão."""
        if step_type not in FIELDS:
            raise ValueError(f"tipo de etapa desconhecido: {step_type}")
        return cls(type=step_type, params=dict(DEFAULTS[step_type]))

    def copy(self) -> "Step":
        """Duplica a etapa, com identidade nova."""
        return Step(type=self.type, params=dict(self.params))

    def as_dict(self) -> dict[str, Any]:
        """Formato consumido pelos geradores de deck."""
        return {"type": self.type, "params": dict(self.params)}

    @property
    def label(self) -> str:
        return STEP_LABELS.get(self.type, self.type)

    @property
    def description(self) -> str:
        return STEP_DESCRIPTIONS.get(self.type, "")

    def fields(self) -> list[Field]:
        """Campos visíveis para os valores atuais."""
        return [f for f in FIELDS[self.type] if f.visible(self.params)]

    def summary(self) -> str:
        """Resumo de uma linha, em linguagem de domínio."""
        return summarize(self)


def summarize(step: Step) -> str:
    """Resumo curto da etapa, como aparece na lista da receita."""
    p, t = step.params, step.type
    if t == "INITIALIZE":
        ori = ORIENTATION_LABELS.get(str(p.get("orientation", "100")), p.get("orientation", ""))
        dop = DOPANT_LABELS.get(p.get("dopant", ""), p.get("dopant", ""))
        return f"Si {ori} · {dop} {fmt_number(p.get('concentration'))} cm⁻³".strip()
    if t == "DIFFUSION":
        amb = AMBIENT_LABELS.get(p.get("ambient", ""), p.get("ambient", ""))
        amb = amb.replace(" (fonte gasosa)", "").replace(" (inerte)", "")
        return f"{amb} · {p.get('temperature', '')} °C · {p.get('time', '')} min"
    if t == "DEPOSITION":
        mat = MATERIAL_LABELS.get(p.get("material", ""), p.get("material", ""))
        return f"{mat} · {fmt_number(p.get('thickness'))} µm"
    if t == "ETCH":
        mat = MATERIAL_LABELS.get(p.get("material", ""), p.get("material", ""))
        quanto = "toda a camada" if p.get("all") else f"{fmt_number(p.get('thickness'))} µm"
        return f"{mat} · {quanto}"
    if t == "IMPLANTI":
        dop = DOPANT_LABELS.get(p.get("dopant", ""), p.get("dopant", ""))
        return (f"{dop} · {fmt_number(p.get('dose'))} cm⁻² · "
                f"{p.get('energy', '')} keV")
    if t == "EPITAXY":
        dop = DOPANT_LABELS.get(p.get("dopant", ""), p.get("dopant", ""))
        return f"{dop} · {fmt_number(p.get('thickness'))} µm"
    if t == "PRINT":
        # A tabela manda no resumo: "Camadas" é mais informativo que a grandeza
        # quando o PRINT pede a pilha de materiais em vez do perfil.
        extra = str(p.get("extra", "")).upper()
        tabelas = dict(FIELDS["PRINT"][2].choices)
        if extra and extra != "CONCENTR":
            grandeza = tabelas.get(extra, extra.capitalize())
        else:
            grandeza = dict(FIELDS["PRINT"][0].choices).get(
                p.get("what", ""), p.get("what", ""))
        return f"{grandeza} → {p.get('filename', '')}"
    return ""


# ── Formatação numérica em português ──────────────────────────────────────

_SUPERSCRIPT = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def parse_float(value: Any) -> float | None:
    """Lê um número aceitando vírgula decimal e notação ``1E15``."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_number(value: Any) -> str:
    """Formata para leitura: ``1E15`` → ``1×10¹⁵``, ``0.5`` → ``0,5``."""
    n = parse_float(value)
    if n is None:
        return "" if value is None else str(value)
    if n != 0 and (abs(n) >= 1e5 or abs(n) < 1e-3):
        exp = 0
        mant = abs(n)
        while mant >= 10:
            mant /= 10
            exp += 1
        while mant < 1:
            mant *= 10
            exp -= 1
        mant = round(mant, 2) * (1 if n > 0 else -1)
        mant_txt = f"{mant:g}".replace(".", ",")
        return f"{mant_txt}×10{str(exp).translate(_SUPERSCRIPT)}"
    return f"{n:g}".replace(".", ",")


# ── Verificação da receita ────────────────────────────────────────────────

@dataclass(frozen=True)
class Issue:
    """Um problema que impede a simulação."""

    message: str
    #: Índice da etapa na receita, ou ``-1`` para um problema da receita inteira.
    index: int = -1
    #: Chave do campo culpado, quando há um.
    key: str = ""


def validate(steps: list[Step]) -> list[Issue]:
    """Lista os problemas que impedem rodar a receita (vazia = pode rodar).

    Verifica três coisas: a receita tem uma Inicialização, e ela vem primeiro;
    todo campo numérico obrigatório tem valor dentro da faixa aceita; e nenhuma
    corrosão tenta remover um material que não está sobre a lâmina naquele
    ponto do processo.
    """
    issues: list[Issue] = []
    if not steps:
        return [Issue("A receita está vazia.")]

    if steps[0].type != "INITIALIZE":
        pos = next((i for i, s in enumerate(steps) if s.type == "INITIALIZE"), -1)
        if pos < 0:
            issues.append(Issue("Falta a Inicialização no início da receita.", 0))
        else:
            issues.append(
                Issue("A Inicialização precisa ser a primeira etapa.", pos))

    # Malha: profundidade simulada dividida pelo passo não pode passar do
    # limite do motor, senão o deck é recusado na leitura.
    for i, step in enumerate(steps):
        if step.type != "INITIALIZE":
            continue
        espessura = parse_float(step.params.get("thickness"))
        passo = parse_float(step.params.get("dx"))
        if espessura and passo and passo > 0:
            nos = espessura / passo
            if nos > MAX_GRID_POINTS:
                sugestao = espessura / MAX_GRID_POINTS
                issues.append(Issue(
                    f"A malha teria {nos:.0f} nós e o SUPREM-III aceita no "
                    f"máximo {MAX_GRID_POINTS}. Aumente o passo para pelo "
                    f"menos {fmt_number(round(sugestao, 6))} µm ou reduza a "
                    f"profundidade simulada.", i, "dx"))

    # Camadas presentes na superfície, para a verificação da corrosão.
    present: set[str] = set()
    for i, step in enumerate(steps):
        for f in step.fields():
            issue = check_field(step, f, i)
            if issue is not None:
                issues.append(issue)

        if step.type == "DIFFUSION":
            if str(step.params.get("ambient", "")).upper() in OXIDIZING_AMBIENTS:
                present.add("OXIDE")
        elif step.type == "DEPOSITION":
            present.add(str(step.params.get("material", "")).upper())
        elif step.type == "EPITAXY":
            present.add("SILICON")
        elif step.type == "ETCH":
            mat = str(step.params.get("material", "")).upper()
            if mat != "SILICON" and mat not in present:
                nome = MATERIAL_LABELS.get(mat, mat).lower()
                issues.append(Issue(
                    f"Não há {nome} sobre a lâmina neste ponto: nada para corroer.",
                    i, "material"))
            elif step.params.get("all"):
                present.discard(mat)

    return issues


def check_field(step: Step, f: Field, index: int = -1) -> Issue | None:
    """Verifica um campo isolado. Devolve o problema, ou ``None`` se está bom."""
    raw = step.params.get(f.key, "")
    text = "" if raw is None else str(raw).strip()

    if f.kind != "number":
        if f.required and f.kind in ("choice", "text") and not text:
            return Issue(f"{f.label} sem valor.", index, f.key)
        return None

    if not text:
        if not f.required:
            return None
        return Issue(f"{f.label} sem valor numérico.", index, f.key)

    n = parse_float(text)
    if n is None:
        return Issue(f"{f.label} não é um número: “{text}”.", index, f.key)
    if f.minimum is not None and n < f.minimum or f.maximum is not None and n > f.maximum:
        return Issue(
            f"{f.label} {fmt_number(text)} {f.unit} está fora da faixa "
            f"({fmt_number(f.minimum)} – {fmt_number(f.maximum)} {f.unit}).".replace("  ", " "),
            index, f.key)
    return None


def range_hint(f: Field) -> str:
    """Texto de ajuda do campo (faixa aceita + observação)."""
    partes = []
    if f.kind == "number" and (f.minimum is not None or f.maximum is not None):
        partes.append(f"Faixa: {fmt_number(f.minimum)} – {fmt_number(f.maximum)} {f.unit}".strip())
    if f.help:
        partes.append(f.help)
    return " · ".join(partes)
