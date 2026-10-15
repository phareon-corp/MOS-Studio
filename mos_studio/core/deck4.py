"""Geração do deck de entrada do SUPREM-IV.GS a partir da mesma receita.

A receita (:mod:`mos_studio.core.recipe`) fala o vocabulário do SUPREM-III,
que é o que a interface mostra. Este módulo traduz essa receita para os
cartões do SUPREM-IV — um dialeto diferente, não uma variação de grafia:

====================  ==========================================  ============
Etapa da receita      SUPREM-IV                                   observação
====================  ==========================================  ============
INITIALIZE            ``mode``/``line``/``region``/``boundary``/   um cartão
                      ``init``                                    virou cinco
DIFFUSION             ``diffuse``                                 direto
IMPLANTI              ``implant``                                 direto
DEPOSITION            ``deposit``                                 direto
ETCH                  ``etch ... all`` / ``etch ... dry thick=``   direto
EPITAXY               ``deposit silicon`` dopado                   *aproximação*
PRINT                 ``select`` + ``print.1d``                     um para dois
====================  ==========================================  ============

Três decisões que valem explicação:

**A malha é explícita.** O SUPREM-III recebia ``DX`` e ``THICKNES`` e montava
a malha sozinho. No SUPREM-IV a malha é do usuário: ``line x`` repetido, com
``tag`` nomeando as extremidades, e ``region``/``boundary`` amarrando as tags.
:func:`mesh_lines` reproduz o par ``dx``/``thickness`` da receita em linhas
de malha, refinando perto da superfície — que é onde o perfil interessa.

**Não existe cartão ``epitaxy``.** Uma epitaxia é emitida como deposição de
silício dopado, o que acerta a geometria e a dopagem da camada mas ignora a
taxa de crescimento e a difusão durante o crescimento. :func:`approximations`
relata isso para a interface avisar em vez de mentir por omissão.

**O ``print.1d`` substitui o ``PRINT``.** O SUPREM-IV não tem tabela de saída
em arquivo: ``print.1d`` escreve na saída padrão a grandeza escolhida pelo
``select`` anterior. Daí o par de cartões por etapa PRINT, e daí os parsers
em :func:`mos_studio.core.parsers.parse_print_1d`.

Armadilhas desta compilação (medidas, não supostas — ver ADR 0002):

* ``diffuse temp`` é em **graus Celsius**, embora ``data/suprem.key`` diga
  "degrees Kelvin": ``diffuse/diffuse.c`` soma 273 ao valor lido.
* ``diffuse time`` é em **minutos** (ao contrário do ``PROFILE TIME`` do
  MINIMOS, que é em segundos).
* Em material GaAs, o silício implantado é ``isilicon``; ``silicon`` numa
  expressão de ``select`` é o nome do *material* e o avaliador recusa com
  "string not allowed in expression".
"""

from __future__ import annotations

from typing import Any

StepDict = dict[str, Any]

#: Dopantes da receita → impurezas do SUPREM-IV.
DOPANTS = {
    "BORON": "boron",
    "PHOSPHOR": "phosphorus",
    "ARSENIC": "arsenic",
    "ANTIMONY": "antimony",
    "BF2": "bf2",          # só o cartão implant aceita
}

#: Materiais da receita → materiais do SUPREM-IV.
MATERIALS = {
    "SILICON": "silicon",
    "OXIDE": "oxide",
    "NITRIDE": "nitride",
    "POLYSILI": "poly",
    "ALUMINUM": "aluminum",
}

#: Ambientes de difusão da receita → ambientes do SUPREM-IV.
AMBIENTS = {
    "DRYO2": "dryo2",
    "WETO2": "weto2",
    "NITROGEN": "nitrogen",
    "BORON": "boron",
    "PHOSPHOR": "phosphorus",
    "ARSENIC": "arsenic",
    "ANTIMONY": "antimony",
}

#: Distribuições de implante. O SUPREM-IV só tem duas; as outras duas da
#: receita não têm equivalente e caem no padrão do motor (ver
#: :func:`approximations`).
DISTRIBUTIONS = {
    "GAUSSIAN": "gauss",
    "PEARSON": "pearson",
}

#: Grandezas da etapa PRINT → expressão do ``select z=``.
QUANTITIES = {
    "NET": "doping",
    "BORON": "boron",
    "PHOSPHOR": "phosphorus",
    "ARSENIC": "arsenic",
    "ANTIMONY": "antimony",
}

#: Limite de nós de malha que mantemos por etapa de simulação. O SUPREM-IV
#: aloca dinamicamente (não tem o teto de 500 do SUPREM-III), mas uma malha 1D
#: com milhares de nós transforma minutos em horas sem ganho de perfil.
MAX_MESH_LINES = 400

#: Espessura de superfície que recebe a malha fina, em µm. Abaixo disso mora o
#: implante; mais fundo, o passo pode crescer sem perder o perfil.
SURFACE_UM = 0.5


def _f(value: Any, default: float) -> float:
    """Lê um número da receita, aceitando ``''``/``None``/``'1E15'``."""
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return default


def _num(value: float) -> str:
    """Formata um número para o deck.

    Inteiros pequenos saem como inteiros (``1000``, não ``1000.0``); doses e
    concentrações saem em notação científica (``1e+15``, não quinze dígitos),
    que é como os exemplos de fábrica escrevem e o parser do motor espera.
    """
    value = float(value)
    if value != 0 and (abs(value) >= 1e6 or abs(value) < 1e-4):
        return f"{value:g}"
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def mesh_lines(thickness_um: float, dx_um: float) -> list[tuple[float, float]]:
    """Linhas de malha ``(posição_µm, espaçamento_µm)`` para a profundidade dada.

    Reproduz a intenção do par ``DX``/``THICKNES`` do SUPREM-III: passo ``dx``
    na superfície, onde fica o implante, e passo folgado no fundo, que só
    precisa existir para fechar o substrato. Entre eles o SUPREM-IV interpola
    respeitando ``interval.r``.

    O resultado sempre tem ao menos duas linhas (topo e fundo) e nunca gera
    mais de :data:`MAX_MESH_LINES` nós — o espaçamento de superfície é afrouxado
    se a profundidade pedida não couber, porque uma malha grosseira que roda é
    melhor que uma fina que não termina.
    """
    thickness_um = max(float(thickness_um), 1e-3)
    dx_um = max(float(dx_um), 1e-5)
    surface = min(SURFACE_UM, thickness_um / 2.0)

    # Afrouxa o passo fino se o orçamento de nós não cobrir a região de
    # superfície mais o corpo do substrato.
    orcamento = MAX_MESH_LINES - 2
    while surface / dx_um + 1 > orcamento and dx_um < surface:
        dx_um *= 2.0

    fundo = max(dx_um * 8.0, (thickness_um - surface) / 20.0)
    linhas = [(0.0, dx_um)]
    if surface < thickness_um:
        linhas.append((surface, dx_um))
    linhas.append((thickness_um, fundo))
    # Remove posições repetidas mantendo a ordem (profundidade rasa demais).
    vistas: set[float] = set()
    saida: list[tuple[float, float]] = []
    for pos, esp in linhas:
        chave = round(pos, 6)
        if chave in vistas:
            continue
        vistas.add(chave)
        saida.append((pos, esp))
    return saida


def _initialize(p: dict) -> list[str]:
    """Os cinco cartões que substituem o ``INITIALIZE`` do SUPREM-III."""
    espessura = _f(p.get("thickness"), 0.5)
    dx = _f(p.get("dx"), 5e-3)
    dopante = DOPANTS.get(str(p.get("dopant", "BORON")).upper(), "boron")
    conc = _f(p.get("concentration"), 1e15)
    orient = str(p.get("orientation", "100")).strip() or "100"

    linhas = ["mode one.dim"]
    malha = mesh_lines(espessura, dx)
    for i, (pos, esp) in enumerate(malha):
        tag = ""
        if i == 0:
            tag = " tag=topo"
        elif i == len(malha) - 1:
            tag = " tag=fundo"
        linhas.append(f"line x loc={_num(pos)} spacing={_num(esp)}{tag}")
    linhas.append("region silicon xlo=topo xhi=fundo")
    # 'exposed' no topo é o que permite oxidar e implantar pela superfície;
    # sem ele a difusão em O2 não cresce óxido.
    linhas.append("boundary exposed xlo=topo xhi=topo")
    linhas.append("boundary backside xlo=fundo xhi=fundo")
    linhas.append(f"init {dopante} conc={_num(conc)} orient={orient}")
    return linhas


def step_to_code(step: StepDict) -> list[str]:
    """Traduz uma etapa da receita para as linhas de deck do SUPREM-IV.

    Devolve uma *lista* (não uma string) porque uma etapa da receita pode
    virar vários cartões — ``INITIALIZE`` vira cinco e ``PRINT`` vira dois.
    Etapas desconhecidas devolvem lista vazia.
    """
    t, p = step.get("type", ""), step.get("params", {}) or {}

    if t == "INITIALIZE":
        return _initialize(p)

    if t == "DIFFUSION":
        amb = AMBIENTS.get(str(p.get("ambient", "DRYO2")).upper(), "nitrogen")
        # temp em °C: diffuse.c soma 273 ao valor lido (o 'units' do
        # suprem.key dizendo Kelvin está errado).
        s = (f"diffuse temp={_num(_f(p.get('temperature'), 1000))}"
             f" time={_num(_f(p.get('time'), 15))} {amb}")
        if p.get("gasConc"):
            s += f" gas.conc={_num(_f(p.get('gasConc'), 1e13))}"
        if p.get("solidSol"):
            s += " solid.sol"
        taxa = p.get("tRate")
        if taxa not in (None, ""):
            # O SUPREM-IV não tem T.RATE: a rampa é start/stop e o motor
            # interpola no tempo da própria etapa.
            t0 = _f(p.get("temperature"), 1000)
            dt = _f(taxa, 0.0) * _f(p.get("time"), 15)
            s += f" ramp start={_num(t0)} stop={_num(t0 + dt)}"
        return [s]

    if t == "IMPLANTI":
        dop = DOPANTS.get(str(p.get("dopant", "BORON")).upper(), "boron")
        s = (f"implant {dop} dose={_num(_f(p.get('dose'), 1e13))}"
             f" energy={_num(_f(p.get('energy'), 45))}")
        modelo = DISTRIBUTIONS.get(str(p.get("distribution", "")).upper())
        if modelo:
            s += f" {modelo}"
        return [s]

    if t == "DEPOSITION":
        mat = MATERIALS.get(str(p.get("material", "OXIDE")).upper(), "oxide")
        s = f"deposit {mat} thick={_num(_f(p.get('thickness'), 0.1))}"
        dop = DOPANTS.get(str(p.get("dopant", "")).upper())
        if dop and dop != "bf2":
            s += f" {dop} concentration={_num(_f(p.get('concentration'), 1e15))}"
        if p.get("temperature"):
            s += f" temperature={_num(_f(p.get('temperature'), 0))}"
        return [s]

    if t == "ETCH":
        mat = MATERIALS.get(str(p.get("material", "OXIDE")).upper(), "oxide")
        if p.get("all", True):
            return [f"etch {mat} all"]
        return [f"etch {mat} dry thick={_num(_f(p.get('thickness'), 0.1))}"]

    if t == "EPITAXY":
        # Aproximação declarada: ver approximations().
        dop = DOPANTS.get(str(p.get("dopant", "PHOSPHOR")).upper(), "phosphorus")
        s = (f"deposit silicon thick={_num(_f(p.get('thickness'), 1.0))}"
             f" {dop} concentration={_num(_f(p.get('concentration'), 5e15))}")
        if p.get("temperature"):
            s += f" temperature={_num(_f(p.get('temperature'), 1000))}"
        return [s]

    if t == "PRINT":
        grandeza = str(p.get("what", "NET")).upper()
        extra = str(p.get("extra", "CONCENTR")).upper()
        z = QUANTITIES.get(grandeza, "doping")
        if extra == "LAYER":
            # 'layers' integra a grandeza e lista as espessuras por região.
            return [f"select z={z}", "print.1d layers"]
        return [f"select z={z}", "print.1d"]

    return []


def approximations(steps: list[StepDict]) -> list[str]:
    """O que a tradução para SUPREM-IV não consegue reproduzir fielmente.

    Existe para a interface poder avisar. Uma receita montada para o
    SUPREM-III pode usar coisas que o SUPREM-IV não tem; calar sobre isso
    faria o usuário comparar os dois motores sem saber que a comparação tem
    um pé fora do lugar.
    """
    avisos: list[str] = []
    for step in steps:
        t, p = step.get("type", ""), step.get("params", {}) or {}
        if t == "EPITAXY":
            avisos.append(
                "Epitaxia: o SUPREM-IV não tem cartão equivalente. Emitida como "
                "deposição de silício dopado — a geometria e a dopagem da camada "
                "ficam certas, a taxa de crescimento e a difusão durante o "
                "crescimento são ignoradas.")
        if t == "IMPLANTI":
            dist = str(p.get("distribution", "")).upper()
            if dist and dist not in DISTRIBUTIONS:
                avisos.append(
                    f"Implante com distribuição {dist}: o SUPREM-IV só tem "
                    "gaussiana e Pearson IV. Vale o padrão do motor (Pearson).")
            if str(p.get("dopant", "")).upper() == "BF2":
                avisos.append(
                    "Implante de BF₂: aceito pelo cartão implant, mas sem "
                    "equivalente nos cartões deposit/init.")
        if t == "DIFFUSION" and p.get("tRate") not in (None, ""):
            avisos.append(
                "Rampa de temperatura: traduzida para ramp start/stop. O "
                "SUPREM-IV interpola no tempo total da etapa, em vez de seguir "
                "uma taxa em °C/min como o SUPREM-III.")
        if t == "PRINT" and str(p.get("extra", "")).upper() not in (
                "CONCENTR", "LAYER", ""):
            avisos.append(
                f"Tabela {p.get('extra')}: o SUPREM-IV só produz perfil de "
                "concentração e lista de camadas pelo print.1d.")
    # Mantém a ordem de aparição, sem repetir o mesmo aviso.
    vistos: set[str] = set()
    return [a for a in avisos if not (a in vistos or vistos.add(a))]


def build_in_file(title: str, steps: list[StepDict]) -> str:
    """Monta o deck completo do SUPREM-IV.

    Sem ``TITLE``/``STOP`` (que são do SUPREM-III): o SUPREM-IV usa comentários
    com ``#`` e termina com ``quit``. O ``option quiet`` corta o eco de cada
    cartão, deixando na saída padrão só o que os parsers precisam ler.
    """
    linhas = [f"# {title}", "option quiet"]
    for step in steps:
        for linha in step_to_code(step):
            linhas.append(linha)
    if not any(l.startswith("print.1d") for l in linhas):
        # Sem nenhuma tabela a execução não produz nada legível. Garante o
        # perfil líquido no fim, como o ensure_profile_print do SUPREM-III.
        linhas += ["select z=doping", "print.1d"]
    linhas.append("quit")
    return "\n".join(linhas) + "\n"


def build_profile_deck(title: str,
                       steps: list[StepDict]) -> tuple[str, list[tuple[str, str]]]:
    """Deck com um ``print.1d`` após **cada** etapa de processo.

    Serve à tela de evolução: devolve ``(texto, plano)``, em que ``plano`` é a
    lista ordenada de ``(rótulo_da_etapa, grandeza)`` correspondente a cada
    bloco de tabela que sairá — na mesma ordem em que os blocos aparecem.
    """
    processo = {"INITIALIZE", "DIFFUSION", "IMPLANTI", "DEPOSITION", "ETCH",
                "EPITAXY"}
    rotulos = {"INITIALIZE": "Substrato", "DIFFUSION": "Difusão",
               "IMPLANTI": "Implante", "DEPOSITION": "Deposição",
               "ETCH": "Corrosão", "EPITAXY": "Epitaxia"}
    linhas = [f"# {title}", "option quiet"]
    plano: list[tuple[str, str]] = []
    for step in steps:
        t = step.get("type", "")
        if t == "PRINT":
            continue          # o plano já imprime a cada etapa
        linhas += step_to_code(step)
        if t in processo:
            linhas += ["select z=doping", "print.1d"]
            plano.append((rotulos.get(t, t), "NET"))
    linhas.append("quit")
    return "\n".join(linhas) + "\n", plano


def deck_title(deck: str, fallback: str = "simulacao") -> str:
    """Título do deck: o primeiro comentário, que é onde o gerador o põe."""
    for linha in deck.splitlines():
        s = linha.strip()
        if s.startswith("#"):
            titulo = s.lstrip("#").strip()
            if titulo:
                return titulo
        elif s:
            break
    return fallback


def ensure_profile_print(deck: str) -> str:
    """Garante que o deck termine imprimindo algo legível.

    Um deck sem ``print.1d`` roda e não produz tabela nenhuma — o motor não
    reclama, e a interface receberia uma execução bem-sucedida e vazia.
    """
    if "print.1d" in deck:
        return deck
    corpo = deck.rstrip()
    linhas = [l for l in corpo.splitlines() if l.strip().lower() not in ("quit", "stop")]
    linhas += ["select z=doping", "print.1d", "quit"]
    return "\n".join(linhas) + "\n"


def strip_plot(deck: str) -> str:
    """Remove ``plot.1d``/``plot.2d``/``contour`` do deck.

    Esta compilação usa ``gpsup/gpfake.c`` — a camada gráfica é um conjunto de
    stubs vazios (mesma decisão do SUPREM-III, ver ADR 0001). Os cartões de
    plot não quebram nada, mas o ``Bugs`` do fonte registra que ``axis=f`` no
    primeiro ``plot_1d`` de uma execução trava o programa, então saem fora.
    """
    saida = []
    for linha in deck.splitlines():
        cabeca = linha.strip().lower()
        if cabeca.startswith(("plot.1d", "plot.2d", "contour")):
            continue
        saida.append(linha)
    return "\n".join(saida) + ("\n" if deck.endswith("\n") else "")
