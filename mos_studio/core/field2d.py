"""O campo 2-D da seção transversal, montado com dados do próprio motor.

Esta compilação não tem camada gráfica: ``gpsup/gpfake.c`` substitui o X11 e o
gplot por stubs vazios, então ``plot.2d`` e ``contour`` não desenham nada. O
que o motor *sabe* fazer é imprimir um corte vertical em texto
(``print.1d x.value=``).

Daí a estratégia: varrer a seção com vários cortes verticais e montar o campo
a partir deles. O resultado é a malha de dados que o motor calculou — não um
desenho aproximado — e dela saem os contornos, a linha de junção e a
geometria das camadas.

O custo é um deck mais longo, não uma execução mais longa: os cortes são
impressos no fim, depois de toda a física já ter sido resolvida.

Uma armadilha que vale repetir aqui porque ela determina o que se vê:
``z=doping`` é a concentração **ativa**. Logo depois de um ``implant``, sem
tratamento térmico, ela mostra só o substrato — o implante aparece em
``z=<espécie>``, que é a concentração química. Medido nesta compilação: um
implante de 5×10¹⁵ cm⁻² de arsênio dá 1,9×10²⁰ cm⁻³ em ``z=arsenic`` e zero
em ``z=doping`` até um recozimento ativá-lo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .parsers import parse_print_1d, parse_print_1d_stack

#: Número de cortes verticais na varredura. 48 colunas dão contornos lisos num
#: painel de ~700 px sem inflar o deck além de alguns milissegundos de leitura.
DEFAULT_COLUMNS = 48

#: Materiais que são o corpo da lâmina. O polissilício fica **fora** de
#: propósito: ele é camada depositada, e tratá-lo como corpo fazia a
#: superfície ser lida no topo da porta e inventava uma junção poli/silício
#: sob a máscara, onde não há junção nenhuma.
BULK = ("silicon", "gaas")


@dataclass
class Column:
    """Um corte vertical: profundidade, valor e material em cada nó."""

    x: float
    depth: list[float] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    material: list[str] = field(default_factory=list)

    def surface(self) -> float | None:
        """Profundidade do primeiro nó de silício, ou ``None`` se não houver."""
        for d, m in zip(self.depth, self.material):
            if m in BULK:
                return d
        return None

    def at(self, depth: float) -> float | None:
        """Valor interpolado nessa profundidade; ``None`` fora do corte."""
        if not self.depth:
            return None
        if depth <= self.depth[0]:
            return self.value[0]
        if depth >= self.depth[-1]:
            return self.value[-1]
        for i in range(1, len(self.depth)):
            d0, d1 = self.depth[i - 1], self.depth[i]
            if d0 <= depth <= d1:
                if d1 - d0 < 1e-12:
                    return self.value[i]
                t = (depth - d0) / (d1 - d0)
                return self.value[i - 1] + t * (self.value[i] - self.value[i - 1])
        return None


@dataclass
class Field2D:
    """A seção transversal: colunas, mais a expressão que as gerou."""

    columns: list[Column] = field(default_factory=list)
    z_expr: str = "doping"
    #: Camadas lidas da tabela de camadas do último corte, para a legenda.
    stack: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.columns) >= 2 and any(c.value for c in self.columns)

    @property
    def xs(self) -> list[float]:
        return [c.x for c in self.columns]

    def extent(self) -> tuple[float, float, float, float]:
        """``(x0, x1, y0, y1)`` dos dados, em µm."""
        if not self.ok:
            return (0.0, 1.0, 0.0, 1.0)
        ds = [d for c in self.columns for d in c.depth]
        return (self.columns[0].x, self.columns[-1].x, min(ds), max(ds))

    def value_range(self) -> tuple[float, float]:
        """Menor e maior ``|valor|`` não nulo, para escalar a cor."""
        vs = [abs(v) for c in self.columns for v in c.value if abs(v) > 0]
        return (min(vs), max(vs)) if vs else (1.0, 1.0)


def build_scan_deck(title: str, mesh_cards: list[str], step_cards: list[str],
                    xs: list[float], z_expr: str = "doping") -> str:
    """Deck que resolve o processo e imprime um corte por posição em ``xs``.

    O ``select`` vai uma vez antes dos cortes: a expressão vale até o próximo
    ``select``, e repeti-la por corte só deixaria o deck mais longo.
    """
    linhas = [f"# {title}"]
    linhas += mesh_cards
    linhas += step_cards
    linhas.append(f"select z={z_expr}")
    for x in xs:
        linhas.append(f"print.1d x.value={x:g}")
    # A tabela de camadas vem do último corte e precisa do x.value: sem ele o
    # print.1d cai no modo de interface e as espessuras saem zeradas.
    if xs:
        linhas.append(f"print.1d x.value={xs[-1]:g} layers")
    linhas.append("quit")
    return "\n".join(linhas) + "\n"


def scan_positions(x0: float, x1: float, n: int = DEFAULT_COLUMNS) -> list[float]:
    """``n`` posições de corte igualmente espaçadas, inclusive nas bordas."""
    n = max(2, int(n))
    if x1 <= x0:
        return [x0, x0]
    passo = (x1 - x0) / (n - 1)
    return [x0 + i * passo for i in range(n)]


def parse_scan(output: str, xs: list[float], z_expr: str = "doping") -> Field2D:
    """Monta o campo a partir da saída de um deck de varredura.

    Os blocos do ``print.1d`` saem na ordem dos cortes, então o pareamento com
    ``xs`` é posicional. Se o motor emitir menos blocos que o pedido (um corte
    fora da malha, por exemplo), as colunas que sobram são descartadas em vez
    de desalinharem o campo.
    """
    blocos = parse_print_1d(output)
    colunas: list[Column] = []
    for x, bloco in zip(xs, blocos):
        col = Column(x=x)
        for depth, valor, material in bloco:
            col.depth.append(depth)
            col.value.append(valor)
            col.material.append(material)
        if col.depth:
            colunas.append(col)
    return Field2D(columns=colunas, z_expr=z_expr,
                   stack=parse_print_1d_stack(output))


# ── Contornos ─────────────────────────────────────────────────────────────

def _grid(fld: Field2D, rows: int) -> tuple[list[float], list[list[float | None]]]:
    """Reamostra as colunas numa grade regular em profundidade.

    As colunas do motor não compartilham as mesmas profundidades (a malha é
    adaptativa e as interfaces duplicam nós), então contornar exige uma grade
    comum. ``None`` marca ponto fora do dado.
    """
    _, _, y0, y1 = fld.extent()
    if y1 <= y0:
        return ([y0], [[None] * len(fld.columns)])
    ys = [y0 + (y1 - y0) * i / (rows - 1) for i in range(rows)]
    grade: list[list[float | None]] = []
    for y in ys:
        linha: list[float | None] = []
        for c in fld.columns:
            v = c.at(y) if c.depth and c.depth[0] <= y <= c.depth[-1] else None
            linha.append(v)
        grade.append(linha)
    return ys, grade


def contour(fld: Field2D, level: float, *, rows: int = 96,
            logarithmic: bool = True) -> list[list[tuple[float, float]]]:
    """Linhas de nível ``level`` como polilinhas ``[(x, y)]`` em µm.

    Marching squares sobre a grade reamostrada. Em escala logarítmica o
    contorno é feito sobre ``log10|valor|``, que é como perfis de dopagem são
    sempre lidos — em escala linear uma década inteira viraria uma linha só.
    """
    if not fld.ok or level <= 0:
        return []
    ys, grade = _grid(fld, rows)
    xs = fld.xs
    alvo = math.log10(level) if logarithmic else level

    def val(r: int, c: int) -> float | None:
        v = grade[r][c]
        if v is None:
            return None
        if not logarithmic:
            return v
        a = abs(v)
        return math.log10(a) if a > 0 else None

    segmentos: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            v00, v10 = val(r, c), val(r, c + 1)
            v01, v11 = val(r + 1, c), val(r + 1, c + 1)
            if None in (v00, v10, v01, v11):
                continue
            quadrado = [(v00, xs[c], ys[r]), (v10, xs[c + 1], ys[r]),
                        (v11, xs[c + 1], ys[r + 1]), (v01, xs[c], ys[r + 1])]
            pontos: list[tuple[float, float]] = []
            for i in range(4):
                va, xa, ya = quadrado[i]
                vb, xb, yb = quadrado[(i + 1) % 4]
                if (va - alvo) * (vb - alvo) < 0:
                    t = (alvo - va) / (vb - va)
                    pontos.append((xa + t * (xb - xa), ya + t * (yb - ya)))
            if len(pontos) >= 2:
                segmentos.append((pontos[0], pontos[1]))
    return _chain(segmentos)


def junction(fld: Field2D, *, rows: int = 96
             ) -> list[list[tuple[float, float]]]:
    """Linha onde a dopagem líquida troca de sinal.

    Só faz sentido quando o campo é ``doping``; para uma espécie química não
    há junção e o resultado é vazio.
    """
    if not fld.ok:
        return []
    ys, grade = _grid(fld, rows)
    xs = fld.xs
    segmentos: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            quad = [(grade[r][c], xs[c], ys[r]),
                    (grade[r][c + 1], xs[c + 1], ys[r]),
                    (grade[r + 1][c + 1], xs[c + 1], ys[r + 1]),
                    (grade[r + 1][c], xs[c], ys[r + 1])]
            if any(v is None for v, _, _ in quad):
                continue
            pontos: list[tuple[float, float]] = []
            for i in range(4):
                va, xa, ya = quad[i]
                vb, xb, yb = quad[(i + 1) % 4]
                # ``<= 0`` com ``va != vb`` para não perder o nó que cai
                # exatamente em zero: ali a dopagem líquida é nula, ou seja, é
                # a junção em pessoa, e o teste estrito a descartaria.
                if va * vb <= 0 and va != vb:
                    t = va / (va - vb)
                    pontos.append((xa + t * (xb - xa), ya + t * (yb - ya)))
            if len(pontos) >= 2:
                segmentos.append((pontos[0], pontos[1]))
    return _chain(segmentos)


def _chain(segmentos, tol: float = 1e-4) -> list[list[tuple[float, float]]]:
    """Costura segmentos soltos em polilinhas, para traçar com poucos caminhos."""
    restantes = list(segmentos)
    saida: list[list[tuple[float, float]]] = []
    while restantes:
        a, b = restantes.pop()
        linha = [a, b]
        mudou = True
        while mudou:
            mudou = False
            for i, (p, q) in enumerate(restantes):
                if _perto(linha[-1], p, tol):
                    linha.append(q)
                elif _perto(linha[-1], q, tol):
                    linha.append(p)
                elif _perto(linha[0], q, tol):
                    linha.insert(0, p)
                elif _perto(linha[0], p, tol):
                    linha.insert(0, q)
                else:
                    continue
                restantes.pop(i)
                mudou = True
                break
        if len(linha) >= 2:
            saida.append(linha)
    return saida


def _perto(a, b, tol: float) -> bool:
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


# ── Geometria das camadas ─────────────────────────────────────────────────

def material_bands(fld: Field2D) -> dict[str, list[tuple[float, float, float]]]:
    """Faixas de cada material por coluna: ``{material: [(x, topo, base)]}``.

    É a geometria que o motor construiu — bico de pássaro da oxidação, degrau
    do espaçador, poli recortado pela corrosão — lida dos materiais que cada
    corte atravessa, sem supor nenhuma forma.
    """
    faixas: dict[str, list[tuple[float, float, float]]] = {}
    for c in fld.columns:
        if not c.depth:
            continue
        atual = c.material[0]
        inicio = c.depth[0]
        for d, m in zip(c.depth[1:], c.material[1:]):
            if m != atual:
                faixas.setdefault(atual, []).append((c.x, inicio, d))
                atual, inicio = m, d
        faixas.setdefault(atual, []).append((c.x, inicio, c.depth[-1]))
    return faixas


def surface_line(fld: Field2D) -> list[tuple[float, float]]:
    """Perfil da superfície do silício ao longo de ``x``."""
    pts = []
    for c in fld.columns:
        s = c.surface()
        if s is not None:
            pts.append((c.x, s))
    return pts


def junction_depth_at(fld: Field2D, x: float) -> float | None:
    """Profundidade de junção na coluna mais próxima de ``x``, em µm.

    Medida da superfície do silício, como a literatura define. Devolve
    ``None`` quando aquele corte não tem junção — sob a porta, por exemplo.
    """
    if not fld.ok:
        return None
    col = min(fld.columns, key=lambda c: abs(c.x - x))
    sup = col.surface()
    if sup is None:
        return None
    anterior = None
    for d, v, m in zip(col.depth, col.value, col.material):
        if m not in BULK:
            continue
        if v == 0.0:
            # Dopagem líquida nula é a junção, não um ponto a ignorar.
            return round(d - sup, 6)
        if anterior is not None and anterior[1] * v < 0:
            d0, v0 = anterior
            t = v0 / (v0 - v) if (v0 - v) else 0.0
            return round(d0 + t * (d - d0) - sup, 6)
        anterior = (d, v)
    return None


def column_at(fld: Field2D, x: float) -> Column | None:
    """A coluna mais próxima de ``x`` — o corte 1-D que a tela desenha."""
    if not fld.columns:
        return None
    return min(fld.columns, key=lambda c: abs(c.x - x))
