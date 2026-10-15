"""A receita 2-D: os cartões do SUPREM-IV como etapas editáveis.

O SUPREM-III tinha sete comandos montáveis e uma geometria implícita. O
SUPREM-IV tem geometria de verdade, e isso muda o vocabulário da receita: uma
corrosão pode remover tudo, descer uma espessura ou cortar de um lado de uma
reta; uma deposição tem divisões de malha; e o método numérico passa a ser uma
etapa, porque trocá-lo no meio do processo é prática normal (ver ``exam5``).

A separação é a mesma do lado 1-D: aqui ficam os tipos, campos, faixas e a
verificação; a tradução para texto de deck é :func:`step_to_cards`, que
preserva os nomes dos cartões do motor.

O que **não** está aqui, de propósito:

* ``plot.1d``/``plot.2d``/``contour`` — esta compilação não tem camada gráfica
  (``gpsup/gpfake.c``), então oferecê-los no catálogo seria deixar o usuário
  montar algo que não desenha nada. A tela de Resultados 2-D desenha a partir
  das tabelas do ``print.1d``, e os comandos equivalentes são mostrados lá.
* ``line``/``region``/``boundary`` — são a malha, que tem tela própria
  (:mod:`mos_studio.core.mesh`). Deixá-los no meio da receita permitiria
  redefinir a malha depois de depositar, o que o motor aceita e quase nunca é
  o que alguém quis dizer.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from .recipe import Field, fmt_number

# ── Vocabulários do SUPREM-IV ─────────────────────────────────────────────

#: Impurezas que o motor aceita em ``init``/``deposit``/``implant``.
IMPURITIES = {
    "boron": "Boro",
    "phosphorus": "Fósforo",
    "arsenic": "Arsênio",
    "antimony": "Antimônio",
}

#: ``implant`` aceita mais espécies que os outros cartões.
IMPLANT_IONS = {**IMPURITIES, "bf2": "BF₂"}

MATERIALS = {
    "silicon": "Silício",
    "oxide": "Óxido",
    "nitride": "Nitreto",
    "poly": "Polissilício",
    "photoresist": "Fotorresiste",
    "aluminum": "Alumínio",
}

AMBIENTS = {
    # "inert" NÃO existe no cartão diffuse desta compilação (o motor responde
    # "parameter inert does not exist for this command"); o ambiente inerte é
    # nitrogen ou argon.
    "nitrogen": "N₂ (inerte)",
    "argon": "Argônio (inerte)",
    "dryo2": "O₂ seco",
    "weto2": "O₂ úmido",
    "boron": "Boro (fonte gasosa)",
    "phosphorus": "Fósforo (fonte gasosa)",
    "arsenic": "Arsênio (fonte gasosa)",
    "antimony": "Antimônio (fonte gasosa)",
}

#: Ambientes que crescem óxido.
OXIDIZING = {"dryo2", "weto2"}
#: Ambientes que são fonte de dopante (habilitam ``gas.conc``).
DOPING_AMBIENTS = {"boron", "phosphorus", "arsenic", "antimony"}

#: Modelos de difusão do cartão ``method``.
METHODS = {
    "fermi": "Fermi",
    "two.dim": "Two.dim",
    "full.cpl": "Full.cpl",
}
METHOD_HELP = {
    "fermi": "Impurezas em equilíbrio com os defeitos: o mais rápido.",
    "two.dim": "Resolve defeitos pontuais em 2-D; necessário para OED.",
    "full.cpl": "Impurezas e defeitos acoplados: o mais completo e o mais lento.",
}

#: Modelos de movimento do óxido.
OXIDE_MODELS = {
    "erfc": "Erfc (analítico)",
    "vertical": "Vertical",
    "compress": "Compressível",
    "viscous": "Viscoso",
}

IMPLANT_MODELS = {"pearson": "Pearson IV", "gauss": "Gaussiana"}

#: Formas de corrosão. ``coords`` é a sequência ``start``/``continue``/``done``.
ETCH_MODES = {
    "all": "Toda a camada",
    "dry": "Descer uma espessura",
    "left": "À esquerda de uma reta",
    "right": "À direita de uma reta",
    "coords": "Região por coordenadas",
}

STEP_LABELS = {
    "INIT": "Inicialização",
    "DEPOSIT": "Deposição",
    "ETCH": "Corrosão",
    "IMPLANT": "Implantação iônica",
    "DIFFUSE": "Difusão",
    "METHOD": "Método numérico",
    "OPTION": "Saída do motor",
    "STRUCTURE": "Salvar estrutura",
}

STEP_DESCRIPTIONS = {
    "INIT": "Dopa a malha e define a orientação. Sempre a primeira etapa.",
    "DEPOSIT": "Deposita uma camada conforme sobre a superfície exposta.",
    "ETCH": "Remove material. Em 2-D a forma do corte define a geometria.",
    "IMPLANT": "Implanta íons; a máscara existente autoalinha o perfil.",
    "DIFFUSE": "Tratamento térmico: oxidação, pré-deposição ou recozimento.",
    "METHOD": "Troca o modelo de difusão e de óxido das etapas seguintes.",
    "OPTION": "Controla o que o motor imprime durante a execução.",
    "STRUCTURE": "Grava malha e soluções num arquivo para reabrir depois.",
}

#: Ordem do catálogo "Adicionar etapa".
STEP_TYPES = ["INIT", "DEPOSIT", "ETCH", "IMPLANT", "DIFFUSE", "METHOD",
              "OPTION", "STRUCTURE"]


def _choices(d: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(d.items())


def _is_doping(p: dict) -> bool:
    return str(p.get("ambient", "")).lower() in DOPING_AMBIENTS


def _etch_thick(p: dict) -> bool:
    return p.get("mode") == "dry"


def _etch_line(p: dict) -> bool:
    return p.get("mode") in ("left", "right")


def _etch_coords(p: dict) -> bool:
    return p.get("mode") == "coords"


FIELDS: dict[str, tuple[Field, ...]] = {
    "INIT": (
        Field("impurity", "Dopante do substrato", "choice",
              choices=_choices(IMPURITIES), wide=True),
        Field("conc", "Concentração", "number", "cm⁻³",
              minimum=1e12, maximum=1e21),
        Field("orient", "Orientação cristalina", "choice",
              choices=(("100", "⟨100⟩"), ("110", "⟨110⟩"), ("111", "⟨111⟩")),
              wide=True),
    ),
    "DEPOSIT": (
        Field("material", "Material", "choice",
              choices=_choices(MATERIALS), wide=True),
        Field("thick", "Espessura", "number", "µm", minimum=1e-3, maximum=10),
        Field("divisions", "Divisões na malha", "number", "linhas",
              minimum=1, maximum=50,
              help="nós ao longo da espessura da camada nova"),
        Field("impurity", "Dopante da camada", "choice",
              choices=(("", "Sem dopante"),) + _choices(IMPURITIES),
              wide=True, required=False),
        Field("conc", "Concentração da camada", "number", "cm⁻³",
              minimum=1e12, maximum=1e22, required=False,
              visible_when=lambda p: bool(p.get("impurity"))),
    ),
    "ETCH": (
        Field("material", "Material removido", "choice",
              choices=_choices(MATERIALS), wide=True),
        Field("mode", "Forma do corte", "choice",
              choices=_choices(ETCH_MODES), wide=True),
        Field("thick", "Espessura removida", "number", "µm",
              minimum=1e-3, maximum=10, visible_when=_etch_thick),
        Field("p1x", "Reta de corte · x", "number", "µm",
              minimum=-10, maximum=100, visible_when=_etch_line,
              help="corta no plano vertical nesta posição"),
        Field("coords", "Coordenadas", "text", wide=True,
              visible_when=_etch_coords, required=False,
              help="pares x,y separados por ponto e vírgula"),
    ),
    "IMPLANT": (
        Field("impurity", "Íon implantado", "choice",
              choices=_choices(IMPLANT_IONS), wide=True),
        Field("dose", "Dose", "number", "cm⁻²", minimum=1e10, maximum=1e17),
        Field("energy", "Energia", "number", "keV", minimum=1, maximum=400),
        Field("model", "Distribuição", "choice",
              choices=(("", "Padrão do motor"),) + _choices(IMPLANT_MODELS),
              wide=True, required=False),
        Field("tilt", "Inclinação do feixe", "number", "°",
              minimum=0, maximum=60, required=False,
              help="0 = perpendicular à superfície"),
    ),
    "DIFFUSE": (
        Field("ambient", "Ambiente", "choice",
              choices=_choices(AMBIENTS), wide=True),
        Field("temp", "Temperatura", "number", "°C",
              minimum=700, maximum=1250),
        Field("time", "Tempo", "number", "min", minimum=0.1, maximum=6000),
        Field("pressure", "Pressão parcial", "number", "atm",
              minimum=0.01, maximum=25, required=False),
        Field("gas_conc", "Concentração na fonte gasosa", "number", "cm⁻³",
              minimum=1e14, maximum=1e21, required=False,
              visible_when=_is_doping),
        Field("ramp_to", "Rampa até", "number", "°C",
              minimum=700, maximum=1250, required=False,
              help="opcional; vazio = temperatura constante"),
    ),
    "METHOD": (
        Field("model", "Modelo de difusão", "choice",
              choices=_choices(METHODS), wide=True),
        Field("oxide", "Movimento do óxido", "choice",
              choices=(("", "Manter o atual"),) + _choices(OXIDE_MODELS),
              wide=True, required=False),
        Field("grid_ox", "Malha dentro do óxido", "number", "µm",
              minimum=1e-3, maximum=1, required=False),
    ),
    "OPTION": (
        Field("quiet", "Reduzir a saída do motor", "bool", wide=True,
              required=False),
    ),
    "STRUCTURE": (
        Field("outfile", "Arquivo", "text", wide=True,
              help="gravado na pasta da execução"),
        Field("mirror", "Espelhar antes de salvar", "choice",
              choices=(("", "Não espelhar"), ("left", "Pela esquerda"),
                       ("right", "Pela direita")),
              wide=True, required=False,
              help="monta o dispositivo inteiro a partir da metade simulada"),
    ),
}

DEFAULTS: dict[str, dict[str, Any]] = {
    "INIT": {"impurity": "boron", "conc": "1E15", "orient": "100"},
    "DEPOSIT": {"material": "oxide", "thick": "0.1", "divisions": "4",
                "impurity": "", "conc": "1E18"},
    "ETCH": {"material": "oxide", "mode": "all", "thick": "0.1",
             "p1x": "0.35", "coords": ""},
    "IMPLANT": {"impurity": "arsenic", "dose": "5E13", "energy": "50",
                "model": "pearson", "tilt": ""},
    "DIFFUSE": {"ambient": "nitrogen", "temp": "950", "time": "30",
                "pressure": "", "gas_conc": "1E18", "ramp_to": ""},
    "METHOD": {"model": "fermi", "oxide": "compress", "grid_ox": ""},
    "OPTION": {"quiet": True},
    "STRUCTURE": {"outfile": "estrutura.str", "mirror": ""},
}

_ids = itertools.count(1)


@dataclass
class Step4:
    """Uma etapa da receita 2-D."""

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    uid: int = field(default_factory=lambda: next(_ids))

    @classmethod
    def new(cls, step_type: str) -> "Step4":
        if step_type not in FIELDS:
            raise ValueError(f"tipo de etapa desconhecido: {step_type}")
        return cls(type=step_type, params=dict(DEFAULTS[step_type]))

    def copy(self) -> "Step4":
        return Step4(type=self.type, params=dict(self.params))

    @property
    def label(self) -> str:
        return STEP_LABELS.get(self.type, self.type)

    @property
    def description(self) -> str:
        return STEP_DESCRIPTIONS.get(self.type, "")

    def fields(self) -> list[Field]:
        return [f for f in FIELDS[self.type] if f.visible(self.params)]

    def summary(self) -> str:
        return summarize(self)


def _f(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return default


def _num(value: Any, default: float = 0.0) -> str:
    v = _f(value, default)
    if v != 0 and (abs(v) >= 1e6 or abs(v) < 1e-4):
        return f"{v:g}"
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def steps_to_dicts(steps: list[Step4]) -> list[dict]:
    """Receita 2-D em JSON, para o arquivo de projeto."""
    return [{"tipo": s.type, "parametros": dict(s.params)} for s in steps]


def steps_from_dicts(dados: list) -> list[Step4]:
    """Receita 2-D lida do projeto, descartando etapas de tipo desconhecido.

    Descartar é melhor que falhar: um projeto gravado por uma versão com uma
    etapa a mais continua abrindo, só sem aquela etapa.
    """
    saida: list[Step4] = []
    for item in dados or []:
        tipo = ""
        params: dict = {}
        if isinstance(item, dict):
            tipo = str(item.get("tipo") or item.get("type") or "")
            params = dict(item.get("parametros") or item.get("params") or {})
        else:
            tipo = str(getattr(item, "type", ""))
            params = dict(getattr(item, "params", {}) or {})
        if tipo not in FIELDS:
            continue
        passo = Step4.new(tipo)
        passo.params.update(params)
        saida.append(passo)
    return saida


def summarize(step: Step4) -> str:
    """Resumo de uma linha, como aparece na lista da receita."""
    p, t = step.params, step.type
    if t == "INIT":
        ori = str(p.get("orient", "100"))
        return (f"{IMPURITIES.get(p.get('impurity', ''), '')} "
                f"{fmt_number(p.get('conc'))} cm⁻³ · ⟨{ori}⟩")
    if t == "DEPOSIT":
        s = f"{MATERIALS.get(p.get('material', ''), '')} · {fmt_number(p.get('thick'))} µm"
        if p.get("impurity"):
            s += f" · {IMPURITIES.get(p['impurity'], '')}"
        return s
    if t == "ETCH":
        mat = MATERIALS.get(p.get("material", ""), "")
        mode = p.get("mode", "all")
        if mode == "all":
            return f"{mat} · toda a camada"
        if mode == "dry":
            return f"{mat} · {fmt_number(p.get('thick'))} µm para baixo"
        if mode in ("left", "right"):
            lado = "à esquerda" if mode == "left" else "à direita"
            return f"{mat} · {lado} de x = {fmt_number(p.get('p1x'))} µm"
        return f"{mat} · região por coordenadas"
    if t == "IMPLANT":
        return (f"{IMPLANT_IONS.get(p.get('impurity', ''), '')} · "
                f"{fmt_number(p.get('dose'))} cm⁻² · {p.get('energy', '')} keV")
    if t == "DIFFUSE":
        amb = AMBIENTS.get(p.get("ambient", ""), "")
        amb = amb.replace(" (fonte gasosa)", "").replace(" (inerte)", "")
        return f"{amb} · {p.get('temp', '')} °C · {p.get('time', '')} min"
    if t == "METHOD":
        s = METHODS.get(p.get("model", ""), "")
        if p.get("oxide"):
            s += f" · óxido {OXIDE_MODELS.get(p['oxide'], '')}"
        return s
    if t == "OPTION":
        return "saída reduzida" if p.get("quiet") else "saída completa"
    if t == "STRUCTURE":
        s = str(p.get("outfile", "") or "estrutura.str")
        if p.get("mirror"):
            s += " · espelhada"
        return s
    return ""


def step_to_cards(step: Step4) -> list[str]:
    """Traduz uma etapa para os cartões do SUPREM-IV.

    Devolve uma lista porque ``ETCH`` por coordenadas vira uma sequência
    ``start``/``continue``/``done`` e ``STRUCTURE`` com espelho vira dois
    cartões.
    """
    p, t = step.params, step.type
    if t == "INIT":
        return [f"init {p.get('impurity', 'boron')} conc={_num(p.get('conc'), 1e15)}"
                f" orient={p.get('orient', '100')}"]
    if t == "DEPOSIT":
        s = (f"deposit {p.get('material', 'oxide')}"
             f" thick={_num(p.get('thick'), 0.1)}"
             f" divisions={int(_f(p.get('divisions'), 4)) or 1}")
        if p.get("impurity"):
            # ``conc``, não ``concentration``: o motor guarda os nomes de
            # parâmetro em onze caracteres (keyfile.MAX_PARAM) e recusa o nome
            # completo com "parameter concentration does not exist for this
            # command".
            s += f" {p['impurity']} conc={_num(p.get('conc'), 1e18)}"
        return [s]
    if t == "ETCH":
        mat = p.get("material", "oxide")
        mode = p.get("mode", "all")
        if mode == "all":
            return [f"etch {mat} all"]
        if mode == "dry":
            return [f"etch {mat} dry thick={_num(p.get('thick'), 0.1)}"]
        if mode in ("left", "right"):
            return [f"etch {mat} {mode} p1.x={_num(p.get('p1x'), 0.35)}"]
        pares = _parse_coords(p.get("coords", ""))
        if len(pares) < 3:
            # Sem coordenadas suficientes o motor abortaria a corrosão; um
            # cartão inválido é melhor que um silencioso, porque a verificação
            # (abaixo) já aponta o problema antes de rodar.
            return [f"etch {mat} all"]
        out = [f"etch {mat} start x={_num(pares[0][0])} y={_num(pares[0][1])}"]
        for x, y in pares[1:-1]:
            out.append(f"etch continue x={_num(x)} y={_num(y)}")
        out.append(f"etch done x={_num(pares[-1][0])} y={_num(pares[-1][1])}")
        return out
    if t == "IMPLANT":
        s = (f"implant {p.get('impurity', 'arsenic')}"
             f" dose={_num(p.get('dose'), 5e13)}"
             f" energy={_num(p.get('energy'), 50)}")
        if p.get("model"):
            s += f" {p['model']}"
        if str(p.get("tilt", "")).strip():
            s += f" angle={_num(p.get('tilt'))}"
        return [s]
    if t == "DIFFUSE":
        amb = p.get("ambient", "nitrogen")
        # 'temp' é em CELSIUS: diffuse.c soma 273 ao valor lido, apesar de o
        # suprem.key dizer "degrees Kelvin" (ver ADR 0002).
        s = (f"diffuse temp={_num(p.get('temp'), 950)}"
             f" time={_num(p.get('time'), 30)} {amb}")
        if str(p.get("pressure", "")).strip():
            s += f" pressure={_num(p.get('pressure'), 1)}"
        if amb in DOPING_AMBIENTS and str(p.get("gas_conc", "")).strip():
            s += f" gas.conc={_num(p.get('gas_conc'), 1e18)}"
        if str(p.get("ramp_to", "")).strip():
            s += (f" ramp start={_num(p.get('temp'), 950)}"
                  f" stop={_num(p.get('ramp_to'))}")
        return [s]
    if t == "METHOD":
        s = f"method {p.get('model', 'fermi')}"
        if p.get("oxide"):
            s += f" {p['oxide']}"
        if str(p.get("grid_ox", "")).strip():
            s += f" grid.ox={_num(p.get('grid_ox'))}"
        return [s]
    if t == "OPTION":
        # O oposto de ``quiet`` é ``normal``, a opção que o próprio motor liga
        # por padrão no switch ``verbose``. ``option /quiet`` é recusado — o
        # shell do SUPREM-IV não tem a negação com barra.
        return ["option quiet"] if p.get("quiet") else ["option normal"]
    if t == "STRUCTURE":
        out = []
        if p.get("mirror"):
            out.append(f"structure mirror {p['mirror']}")
        out.append(f"structure out={p.get('outfile') or 'estrutura.str'}")
        return out
    return []


def _parse_coords(text: str) -> list[tuple[float, float]]:
    """Lê ``\"0,0; 0.5,-1.1; 1,0\"`` como lista de pares."""
    pares: list[tuple[float, float]] = []
    for pedaco in str(text).split(";"):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        partes = pedaco.replace("\t", " ").split()
        if len(partes) == 1:
            partes = pedaco.split(",")
            if len(partes) > 2:          # "0,0" com vírgula decimal é ambíguo
                partes = [",".join(partes[:2]), ",".join(partes[2:])]
        if len(partes) != 2:
            continue
        try:
            pares.append((float(partes[0].replace(",", ".")),
                          float(partes[1].replace(",", "."))))
        except ValueError:
            continue
    return pares


# ── Verificação ───────────────────────────────────────────────────────────

@dataclass
class Issue:
    """Um problema que impede rodar, com a etapa a que pertence."""

    index: int
    message: str
    uid: int | None = None
    key: str = ""


def validate(steps: list[Step4]) -> list[Issue]:
    """Problemas da receita, na ordem em que aparecem.

    Verifica o que o motor *não* reclama de forma clara: corroer um material
    que não está sobre a lâmina, por exemplo, faz o SUPREM-IV seguir com a
    geometria errada em vez de parar.
    """
    issues: list[Issue] = []
    if not steps:
        return [Issue(-1, "A receita está vazia.")]
    if steps[0].type != "INIT":
        j = next((i for i, s in enumerate(steps) if s.type == "INIT"), -1)
        issues.append(Issue(
            max(j, 0),
            "A Inicialização precisa ser a primeira etapa."
            if j >= 0 else "Falta a Inicialização no início da receita."))
    if sum(1 for s in steps if s.type == "INIT") > 1:
        j = [i for i, s in enumerate(steps) if s.type == "INIT"][1]
        issues.append(Issue(j, "Só pode haver uma Inicialização na receita."))

    # Pilha de materiais sobre a lâmina, para pegar corrosão sem alvo.
    pilha: list[str] = []
    for i, s in enumerate(steps):
        for f in s.fields():
            if f.kind != "number":
                continue
            raw = str(s.params.get(f.key, "")).strip()
            if not raw:
                if f.required:
                    issues.append(Issue(i, f"{f.label} sem valor.",
                                        s.uid, f.key))
                continue
            try:
                v = float(raw.replace(",", "."))
            except ValueError:
                issues.append(Issue(i, f"{f.label}: “{raw}” não é um número.",
                                    s.uid, f.key))
                continue
            if f.minimum is not None and f.maximum is not None and not (
                    f.minimum <= v <= f.maximum):
                issues.append(Issue(
                    i,
                    f"{f.label} {fmt_number(raw)} {f.unit} está fora da faixa "
                    f"({fmt_number(f.minimum)} – {fmt_number(f.maximum)} "
                    f"{f.unit}).", s.uid, f.key))

        if s.type == "DIFFUSE" and s.params.get("ambient") in OXIDIZING:
            if "oxide" not in pilha:
                pilha.append("oxide")
        elif s.type == "DEPOSIT":
            pilha.append(s.params.get("material", ""))
        elif s.type == "ETCH":
            mat = s.params.get("material", "")
            if mat != "silicon" and mat not in pilha:
                issues.append(Issue(
                    i, f"Não há {MATERIALS.get(mat, mat).lower()} sobre a "
                       f"lâmina neste ponto: nada para corroer.", s.uid,
                    "material"))
            elif s.params.get("mode") == "all" and mat in pilha:
                pilha.remove(mat)
            if s.params.get("mode") == "coords":
                if len(_parse_coords(s.params.get("coords", ""))) < 3:
                    issues.append(Issue(
                        i, "A corrosão por coordenadas precisa de pelo menos "
                           "três pares x,y.", s.uid, "coords"))
        elif s.type == "STRUCTURE":
            if not str(s.params.get("outfile", "")).strip():
                issues.append(Issue(i, "Informe o nome do arquivo.",
                                    s.uid, "outfile"))
    return issues


def warnings(steps: list[Step4]) -> list[Issue]:
    """Avisos que **não** impedem rodar, mas mudam o que se vê no resultado.

    O caso que motivou esta função: logo depois de um ``implant``, a dopagem
    *ativa* (``select z=doping``) ainda é só a do substrato — medido nesta
    compilação, um implante de 5×10¹⁵ cm⁻² de arsênio aparece como
    1,9×10²⁰ cm⁻³ em ``z=arsenic`` e **zero** em ``z=doping`` até um
    tratamento térmico ativá-lo. Sem este aviso, a tela de Resultados parece
    vazia e o usuário conclui que o implante não funcionou.
    """
    avisos: list[Issue] = []
    implantes: list[int] = []
    for i, s in enumerate(steps):
        if s.type == "IMPLANT":
            implantes.append(i)
        elif s.type == "DIFFUSE":
            implantes.clear()
    for i in implantes:
        ion = IMPLANT_IONS.get(steps[i].params.get("impurity", ""), "O íon")
        avisos.append(Issue(
            i, f"{ion} implantado sem tratamento térmico depois: a dopagem "
               f"ativa não vai mostrar este implante. Acrescente uma Difusão "
               f"para ativá-lo, ou veja o perfil químico por espécie nos "
               f"Resultados.", steps[i].uid))
    if not any(s.type == "DIFFUSE" and s.params.get("ambient") in OXIDIZING
               for s in steps) and any(s.type == "DEPOSIT" and
                                       s.params.get("material") == "poly"
                                       for s in steps):
        j = next(i for i, s in enumerate(steps)
                 if s.type == "DEPOSIT" and s.params.get("material") == "poly")
        avisos.append(Issue(
            j, "Polissilício depositado direto sobre o silício, sem óxido de "
               "porta. O motor aceita; o dispositivo não funcionaria."))
    return avisos


def field_problems(steps: list[Step4]) -> dict[tuple[int, str], str]:
    """Problemas indexados por ``(uid da etapa, chave do campo)``."""
    return {(i.uid, i.key): i.message
            for i in validate(steps) if i.uid is not None and i.key}


# ── Deck ──────────────────────────────────────────────────────────────────

def build_deck(title: str, mesh_cards: list[str], steps: list[Step4],
               *, print_cut: float | None = None) -> str:
    """Deck completo: comentário, malha, etapas e a tabela de saída.

    ``print_cut`` acrescenta um corte vertical em ``x`` no fim, que é como a
    tela de Resultados 2-D consegue um perfil 1-D para desenhar. Sem ele a
    execução não produz tabela nenhuma e a tela ficaria vazia.
    """
    linhas = [f"# {title}"]
    linhas += mesh_cards
    for s in steps:
        linhas += step_to_cards(s)
    if print_cut is not None:
        # O x.value é obrigatório nos DOIS prints: sem ele o print.1d cai no
        # modo de interface (BND, ver print_1d.c) e a tabela de camadas sai
        # com espessuras zeradas em vez da pilha vertical.
        linhas += ["select z=doping", f"print.1d x.value={print_cut:g}",
                   f"print.1d x.value={print_cut:g} layers"]
    linhas.append("quit")
    return "\n".join(linhas) + "\n"


def cards_with_origin(mesh_cards: list[str],
                      steps: list[Step4]) -> list[tuple[str, int | None]]:
    """Cada linha do deck com o ``uid`` da etapa que a gerou (``None`` = malha).

    É o que permite clicar numa linha do deck e cair na etapa certa.
    """
    out: list[tuple[str, int | None]] = [(c, None) for c in mesh_cards]
    for s in steps:
        for c in step_to_cards(s):
            out.append((c, s.uid))
    return out
