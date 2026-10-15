"""A malha do SUPREM-IV: linhas, espaçamento e a contagem de nós que sai delas.

No SUPREM-III a malha era implícita — o usuário dava ``DX`` e ``THICKNES`` e o
motor resolvia. No SUPREM-IV a malha é do usuário: cada cartão ``line`` fixa
uma posição e o espaçamento *naquele ponto*, e entre duas linhas o motor
interpola o espaçamento de forma gradual.

Este módulo reproduz essa geração para que a interface possa mostrar a malha
antes de rodar — é o que transforma "spacing = 0,02" em "1.173 nós, 12 s
estimados" antes de o usuário esperar o motor.

A regra está em ``dvpram()``, em ``mesh/rect.c``, e **não** é interpolação
linear do espaçamento: entre duas linhas o passo cresce por uma razão
geométrica fixa, limitada a ``interval.r`` (1,5 por padrão). O número de nós
interiores é ``int(log(hr/hl)/log(r) + 0.5)`` — um arredondamento que às vezes
deixa o primeiro passo até 10% acima do espaçamento pedido.

:func:`positions` transcreve essa função. A diferença importa: para a malha
padrão, a interpolação linear erraria a contagem de nós em cerca de 10%, e a
pré-visualização mostraria uma malha que o motor não gera. Os valores foram
conferidos contra ``initialize line.data``, que faz o motor listar as posições
que realmente criou (ver ``tests/test_mesh.py``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Razão máxima entre passos vizinhos (``interval.r`` do cartão ``initialize``
#: e ``mr`` em ``mesh/rect.c``).
MAX_RATIO = 1.5

#: ``EPS`` de ``include/constant.h``, usado nos mesmos testes de igualdade.
_EPS = 1.0e-6

#: Espaçamento mínimo aceito, em µm. Abaixo disso a malha explode em nós sem
#: ganho de precisão (e o motor fica minutos num passo de tempo).
MIN_SPACING = 1e-3

#: Teto de nós por eixo. Serve de guarda contra um ``spacing`` digitado com
#: uma casa decimal a menos, que geraria dezenas de milhares de linhas.
MAX_LINES_PER_AXIS = 2000

#: Acima disto a interface avisa que a execução vai ser lenta. Medido nesta
#: máquina com o LDD: 5.400 nós levam 12 s, 8.500 levam 22 s.
SLOW_NODE_COUNT = 5000

#: Acima disto o motor **cai** — falha de segmentação, sem mensagem. Medido
#: bisseccionando uma malha uniforme com só um ``initialize``: 10.653 nós
#: passam, 11.256 não. Com um processo de verdade o teto é menor, porque cada
#: deposição acrescenta nós; o LDD do manual roda até 8.540 nós.
#:
#: O limite não está numa constante do fonte — as listas de linhas crescem por
#: ``realloc`` em ``mesh/rect.c``. É o solver que não aguenta.
MAX_SAFE_NODES = 9000

#: O ponto em que a malha deixou de mudar o resultado, para o aviso explicar
#: que refinar além disso só custa tempo. Medido com o LDD: a junção em
#: x = 0,9 µm vai de 0,1545 µm (1.450 nós) a 0,1491 µm (8.540 nós), com menos
#: de 1% de diferença a partir de ~3.000.
CONVERGED_NODE_COUNT = 3000

#: Segundos por nó, medido nesta máquina com os exemplos de fábrica. Serve só
#: para dar ordem de grandeza na interface, não é promessa de desempenho.
SECONDS_PER_NODE = 0.0042


@dataclass
class Line:
    """Um cartão ``line``: posição e espaçamento local, ambos em µm."""

    loc: float
    spacing: float
    tag: str = ""

    def to_card(self, axis: str) -> str:
        """Texto do cartão, como vai para o deck."""
        s = f"line {axis} loc={_num(self.loc)} spacing={_num(self.spacing)}"
        if self.tag:
            s += f" tag={self.tag}"
        return s


def _num(v: float) -> str:
    """Número no formato que o deck usa (sem zeros à direita sobrando)."""
    return f"{float(v):g}"


@dataclass
class Mesh:
    """As linhas dos dois eixos, mais as tags que ``region``/``boundary`` usam.

    ``x`` é a direção lateral e ``y`` a profundidade — a mesma convenção dos
    exemplos de fábrica, em que ``y`` cresce para dentro da lâmina.
    """

    x: list[Line] = field(default_factory=list)
    y: list[Line] = field(default_factory=list)
    material: str = "silicon"

    def axis(self, name: str) -> list[Line]:
        return self.x if name == "x" else self.y


def validate_axis(lines: list[Line]) -> str:
    """Mensagem do primeiro problema do eixo, ou ``""`` se estiver válido."""
    if len(lines) < 2:
        return "Defina pelo menos duas linhas para o eixo ter extensão."
    for i, ln in enumerate(lines):
        if ln.spacing <= 0:
            return f"Linha {i + 1}: o espaçamento precisa ser maior que zero."
        if ln.spacing < MIN_SPACING:
            return (f"Linha {i + 1}: espaçamento {_num(ln.spacing)} µm é menor "
                    f"que o mínimo de {_num(MIN_SPACING)} µm.")
        if i and ln.loc <= lines[i - 1].loc:
            return (f"Linha {i + 1}: a posição precisa ser maior que a da "
                    f"linha anterior ({_num(lines[i - 1].loc)} µm).")
    return ""


def divide(hl: float, hr: float, el: float) -> tuple[int, float, float]:
    """Transcrição de ``dvpram()`` (``mesh/rect.c``).

    Dados os espaçamentos pedidos nas duas pontas (``hl``, ``hr``) e o
    comprimento do trecho (``el``), devolve ``(nós_interiores, razão,
    primeiro_passo_relativo)``. O passo inicial é ``primeiro * el`` e cada
    passo seguinte é o anterior vezes ``razão``.
    """
    if hl <= 0 or hr <= 0 or el <= 0:
        return (0, 1.0, 1.0)
    hl, hr = min(hl, el), min(hr, el)
    # Um trecho curto demais para subdividir vira um intervalo só.
    if abs(el - hl) <= _EPS * el and abs(el - hr) <= _EPS * el:
        return (0, 1.0, 1.0)
    # Mesmo espaçamento nas duas pontas: divisão uniforme. O -0.49999 é do
    # original e arredonda para baixo no empate.
    if abs(hr - hl) <= _EPS * el:
        n = int(el / hl - 0.49999)
        return (max(n, 0), 1.0, 1.0 / (n + 1) if n >= 0 else 1.0)
    # O limite de razão entra aqui: nenhuma das pontas pode pedir um passo
    # que force vizinhos com razão acima de MAX_RATIO.
    hr = min(hr, hl / MAX_RATIO + (1 - 1 / MAX_RATIO) * el)
    hl = min(hl, hr / MAX_RATIO + (1 - 1 / MAX_RATIO) * el)
    r = (el - hl) / (el - hr)
    rn = hr / hl
    if r <= 0 or abs(r - 1.0) < 1e-12 or rn <= 0:
        return (0, 1.0, 1.0)
    n = int(math.log(rn) / math.log(r) + 0.5)
    if n <= 0:
        return (0, 1.0, 1.0)
    ratio = min(max(math.exp(math.log(rn) / n), 1 / MAX_RATIO), MAX_RATIO)
    denom = math.exp((n + 1) * math.log(ratio)) - 1
    if abs(denom) < 1e-15:
        return (n, ratio, 1.0 / (n + 1))
    return (n, ratio, (ratio - 1) / denom)


def positions(lines: list[Line]) -> list[float]:
    """Posições dos nós que o motor vai criar neste eixo.

    Devolve ``[]`` se o eixo não for válido — quem chama trata o aviso com
    :func:`validate_axis`, que explica *qual* é o problema.
    """
    if validate_axis(lines):
        return []
    out: list[float] = [lines[0].loc]
    for a, b in zip(lines, lines[1:]):
        el = b.loc - a.loc
        n, ratio, first = divide(a.spacing, b.spacing, el)
        n = min(n, MAX_LINES_PER_AXIS)
        step = first * el
        p = a.loc
        for _ in range(n):
            p += step
            out.append(p)
            step *= ratio
        out.append(b.loc)
    return out


@dataclass
class MeshStats:
    """O que a interface mostra sobre a malha gerada."""

    nodes: int = 0
    triangles: int = 0
    min_spacing: float = 0.0
    x_positions: list[float] = field(default_factory=list)
    y_positions: list[float] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and self.nodes > 0

    @property
    def slow(self) -> bool:
        """``True`` quando a malha é grande o bastante para a espera incomodar."""
        return self.nodes >= SLOW_NODE_COUNT

    @property
    def risky(self) -> bool:
        """``True`` quando a malha passa do que o motor aguenta.

        Não é um aviso de lentidão: acima de :data:`MAX_SAFE_NODES` o
        SUPREM-IV termina em falha de segmentação, sem mensagem, e a execução
        não produz resultado nenhum.
        """
        return self.nodes >= MAX_SAFE_NODES

    @property
    def converged(self) -> bool:
        """``True`` quando refinar mais já não muda o resultado."""
        return self.nodes >= CONVERGED_NODE_COUNT

    @property
    def estimated_seconds(self) -> float:
        return self.nodes * SECONDS_PER_NODE


def stats(mesh: Mesh) -> MeshStats:
    """Nós, triângulos e menor passo da malha — ou o erro que impede gerá-la."""
    err = validate_axis(mesh.x) or validate_axis(mesh.y)
    if err:
        return MeshStats(error=err)
    xs, ys = positions(mesh.x), positions(mesh.y)
    if not xs or not ys:
        return MeshStats(error="A malha não pôde ser gerada.")
    menor = min(
        [b - a for a, b in zip(xs, xs[1:])] + [b - a for a, b in zip(ys, ys[1:])]
        or [0.0])
    return MeshStats(nodes=len(xs) * len(ys),
                     triangles=2 * (len(xs) - 1) * (len(ys) - 1),
                     min_spacing=menor, x_positions=xs, y_positions=ys)


def extent(mesh: Mesh) -> tuple[float, float, float, float]:
    """``(x0, x1, y0, y1)`` da área simulada, em µm."""
    if not mesh.x or not mesh.y:
        return (0.0, 1.0, 0.0, 1.0)
    return (mesh.x[0].loc, mesh.x[-1].loc, mesh.y[0].loc, mesh.y[-1].loc)


def to_cards(mesh: Mesh) -> list[str]:
    """A malha completa em cartões: ``line``, ``region`` e ``boundary``.

    As tags são fixas (``esq``/``dir``/``topo``/``fundo``) porque é a interface
    que gera o deck: deixar o usuário nomeá-las só criaria uma forma de quebrar
    o ``region`` sem ganho nenhum.
    """
    xs, ys = list(mesh.x), list(mesh.y)
    if len(xs) < 2 or len(ys) < 2:
        return []
    cards = ["mode two.dim"]
    for i, ln in enumerate(xs):
        tag = "esq" if i == 0 else "dir" if i == len(xs) - 1 else ""
        cards.append(Line(ln.loc, ln.spacing, tag).to_card("x"))
    for i, ln in enumerate(ys):
        tag = "topo" if i == 0 else "fundo" if i == len(ys) - 1 else ""
        cards.append(Line(ln.loc, ln.spacing, tag).to_card("y"))
    cards.append(f"region {mesh.material} xlo=esq xhi=dir ylo=topo yhi=fundo")
    # 'exposed' no topo é o que permite oxidar e depositar pela superfície;
    # sem ele a difusão em O2 não cresce óxido.
    cards.append("boundary exposed xlo=esq xhi=dir ylo=topo yhi=topo")
    cards.append("boundary backside xlo=esq xhi=dir ylo=fundo yhi=fundo")
    # A borda esquerda é o plano de simetria: só metade do dispositivo é
    # simulada, como nos exemplos de fábrica.
    cards.append("boundary reflecting xlo=esq xhi=esq ylo=topo yhi=fundo")
    cards.append("boundary reflecting xlo=dir xhi=dir ylo=topo yhi=fundo")
    return cards


def to_dict(mesh: Mesh) -> dict:
    """A malha em JSON, para o arquivo de projeto."""
    def eixo(linhas: list[Line]) -> list[dict]:
        return [{"loc": ln.loc, "spacing": ln.spacing} for ln in linhas]

    return {"x": eixo(mesh.x), "y": eixo(mesh.y), "material": mesh.material}


def from_dict(dados: dict | None) -> Mesh:
    """Malha lida do projeto. Sem dados ou com dados inúteis, volta a padrão.

    As tags não são lidas nem gravadas: :func:`to_cards` as atribui pela
    posição, e guardá-las só criaria uma forma de o arquivo discordar do deck.
    """
    if not dados:
        return default_mesh()

    def eixo(chave: str) -> list[Line]:
        saida: list[Line] = []
        for item in dados.get(chave, []) or []:
            try:
                saida.append(Line(float(item["loc"]), float(item["spacing"])))
            except (KeyError, TypeError, ValueError):
                continue
        return saida

    m = Mesh(x=eixo("x"), y=eixo("y"),
             material=str(dados.get("material") or "silicon"))
    return m if len(m.x) >= 2 and len(m.y) >= 2 else default_mesh()


def engine_check(mesh: Mesh, run_dir=None) -> tuple[int, str]:
    """Pede ao motor que gere esta malha e devolve ``(nós, mensagem)``.

    É a única forma de saber que a pré-visualização concorda com o motor: o
    ``initialize line.data`` faz o SUPREM-IV listar as posições que realmente
    criou. Custa frações de segundo porque não há etapa de processo nenhuma.

    ``nós`` vem ``0`` quando o motor recusou a malha; a mensagem explica.
    """
    import re

    from . import suprem4

    cartoes = to_cards(mesh)
    if not cartoes:
        return (0, "A malha ainda não tem linhas suficientes.")
    deck = "\n".join(cartoes
                     + ["initialize boron conc=1e15 orient=100 line.data",
                        "quit"]) + "\n"
    try:
        saida = suprem4.run_sync(deck, run_dir=run_dir, timeout=120)
    except RuntimeError as exc:
        return (0, str(exc))
    m = re.search(r"Points\s*=\s*(\d+)", saida)
    if m is None:
        return (0, "O motor não relatou a contagem de nós.")
    return (int(m.group(1)), "")


def default_mesh() -> Mesh:
    """Malha inicial: fina na superfície e perto da borda da porta.

    São os valores do ``exam5`` do manual, que é o transistor LDD: meio micron
    de lateral, dois de profundidade, refino em ``x = 0,35`` (onde a porta
    termina) e na superfície, onde o implante mora.
    """
    return Mesh(
        x=[Line(0.0, 0.1), Line(0.35, 0.03), Line(0.6, 0.05), Line(1.0, 0.1)],
        y=[Line(0.0, 0.02), Line(0.5, 0.05), Line(1.0, 0.15), Line(2.0, 0.4)],
    )
