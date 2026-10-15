"""Leitura das saídas do SUPREM-III e do MINIMOS.

Movido de ``suprem3.py`` sem mudança de lógica. Estes parsers foram ajustados
contra a saída real dos binários (tabelas paginadas, cabeçalhos repetidos,
números em notação Fortran) e são a parte do backend mais fácil de quebrar
“melhorando”.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

Point = tuple[float, float]


#: Um número solto, inclusive em notação científica.
_NUMBER_ONLY = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _has_text(line: str) -> bool:
    """``True`` se sobra alguma letra depois de tirar os números da linha.

    O ``E`` de ``1.0E+16`` é letra para uma expressão regular ingênua, e era
    o bastante para o leitor confundir uma linha de dados com o fim da tabela.
    """
    return bool(re.search(r"[A-Za-z]", _NUMBER_ONLY.sub(" ", line)))


def parse_out_file(text: str) -> list[Point]:
    """Extrai o perfil profundidade × concentração de ``PRINT ... CONCENTRATION``.

    A tabela vem em 3 pares (depth, concentration) por linha e pode ocupar
    várias páginas. A concentração é NET (com sinal: + = tipo n, - = tipo p).
    Devolve ``[(profundidade_um, concentracao), ...]`` ordenado por
    profundidade; ``[]`` se não houver tabela de perfil.
    """
    lines = text.replace("\r", "").split("\n")
    pts: list[Point] = []
    in_profile = False
    num_re = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
    for raw in lines:
        low = raw.lower()
        # cabeçalho da tabela de perfil: "depth   concentration ..."
        if "depth" in low and "concentration" in low:
            in_profile = True
            continue
        if not in_profile:
            continue
        s = raw.strip()
        if not s:
            continue
        # Cabeçalho de página no meio da tabela: a impressão se repete a cada
        # quebra, e essas linhas não encerram nada.
        if low.strip() in ("net chemical", "net active", "net", "chemical",
                           "active"):
            continue
        # Texto de verdade encerra a tabela. "De verdade" exclui o ``E`` do
        # expoente: uma linha toda de números como "0.0280  0.00000E+00" é
        # dado. Antes a conta era ao contrário, e a tabela morria na primeira
        # profundidade de concentração nula — ou seja, em todo deck que
        # imprime com óxido ainda sobre a lâmina, porque no óxido a dopagem
        # ativa é zero.
        if _has_text(s):
            in_profile = False
            continue
        nums = num_re.findall(s)
        if len(nums) < 2:
            continue
        try:
            vals = [float(x) for x in nums]
        except ValueError:
            continue
        # processa em pares (profundidade, concentração); a concentração
        # nula do óxido é descartada aqui, e o perfil começa no silício
        for i in range(0, len(vals) - 1, 2):
            d, c = vals[i], vals[i + 1]
            if 0.0 <= d < 1e4 and abs(c) > 1e9:
                pts.append((d, c))
    pts.sort(key=lambda p: p[0])
    return pts


def parse_suprem_profiles(out_text: str) -> list[tuple[list[float], list[float]]]:
    """Extrai todos os blocos ``depth concentration`` do OUTPUT.OUT, em ordem.

    Devolve ``[(depth[], conc[]), ...]`` — profundidade em µm, concentração em
    cm⁻³ (o ``net`` vem com sinal: + tipo N, − tipo P).
    """
    if not out_text:
        return []
    txt = out_text.replace("\f", "")
    blocks: list[tuple[list[float], list[float]]] = []
    lines = txt.split("\n")
    i = 0
    while i < len(lines):
        if "depth" in lines[i].lower() and "concentration" in lines[i].lower():
            depth: list[float] = []
            conc: list[float] = []
            i += 1
            while i < len(lines):
                m = re.findall(r'[-+]?\d*\.\d+(?:E[-+]?\d+)?', lines[i])
                if len(m) >= 2:
                    try:
                        depth.append(float(m[0]))
                        conc.append(float(m[1]))
                    except ValueError:
                        break
                    i += 1
                else:
                    break
            if depth:
                blocks.append((depth, conc))
        else:
            i += 1
    return blocks


def detect_junctions(data: list[Point], min_pts: int = 3,
                     min_mag: float = 1e16) -> list[float]:
    """Detecta junções reais num perfil net (lista de ``(prof, net_com_sinal)``).

    Uma troca de sinal só conta como junção se, dos DOIS lados, o tipo persistir
    por pelo menos ``min_pts`` pontos e a magnitude atingir ``min_mag`` — assim
    ignoramos o artefato da superfície (óxido→Si) e slivers numéricos finos.
    """
    juncs: list[float] = []
    n = len(data)
    for i in range(1, n):
        a, b = data[i - 1][1], data[i][1]
        if a * b >= 0:
            continue
        left = [data[j][1] for j in range(max(0, i - min_pts), i)]
        right = [data[j][1] for j in range(i, min(n, i + min_pts))]
        if len(left) < min_pts or len(right) < min_pts:
            continue
        if not (all(v * a > 0 for v in left) and all(v * b > 0 for v in right)):
            continue
        if max(abs(v) for v in left) < min_mag or max(abs(v) for v in right) < min_mag:
            continue
        xj = data[i - 1][0] + (data[i][0] - data[i - 1][0]) * abs(a) / (abs(a) + abs(b))
        juncs.append(xj)
    return juncs


def parse_oxide_thickness(raw: str) -> float | None:
    """Lê a espessura (µm) da camada de ÓXIDO na tabela ``layer ... material``."""
    for line in raw.split("\n"):
        if re.search(r"\bOXIDE\b", line, re.IGNORECASE):
            nums = re.findall(r"\d*\.\d+", line)
            if nums:
                try:
                    return float(nums[0])
                except ValueError:
                    pass
    return None


#: Cabeçalho da tabela de camadas do ``PRINT LAYER``.
_LAYER_HEADER = re.compile(r"\blayer\b.*\bmaterial\b.*\bthickness\b",
                           re.IGNORECASE)

#: Uma linha da tabela: número da camada, material e espessura.
_LAYER_ROW = re.compile(
    r"^\s*\d+\s+(OXIDE|NITRIDE|SILICON|POLYSILICON|POLYSILI|ALUMINUM)\b"
    r"\s+(\d*\.\d+(?:[eE][-+]?\d+)?)", re.IGNORECASE)


def parse_layers(raw: str) -> list[tuple[str, float]]:
    """Lê a tabela de camadas (``PRINT LAYER``): ``[(material, espessura_um)]``.

    Exige o cabeçalho da tabela e o formato de linha — número, material,
    espessura. Procurar o nome do material em qualquer linha fazia o eco do
    próprio deck virar camada: ``DEPOSITION POLYSILI THICKNES=0.35`` no log
    entrava como uma camada de polissilício de 0,35 µm, e como o OUTPUT.OUT
    vem antes na ordem alfabética, era ele que a tela mostrava, no lugar da
    pilha de verdade.
    """
    out: list[tuple[str, float]] = []
    dentro = False
    for line in raw.replace("\r", "").split("\n"):
        if _LAYER_HEADER.search(line):
            dentro = True
            continue
        if not dentro:
            continue
        m = _LAYER_ROW.match(line)
        if m:
            try:
                out.append((m.group(1).upper(), float(m.group(2))))
            except ValueError:
                pass
            continue
        # A tabela só termina depois de ter rendido alguma camada: o
        # cabeçalho ocupa duas linhas, e a segunda ("no.  (microns) …") não é
        # camada nenhuma.
        if out and line.strip():
            dentro = False
    return out


def parse_minimos_pif(pif_text: str) -> tuple[list[float], list[float], dict[str, list[float]]]:
    """Lê o PIF (fort.30) do MINIMOS: grade estruturada e campos físicos.

    Devolve ``(lat, vert, campos)``, em que ``lat``/``vert`` são as posições
    (µm) dos eixos e ``campos`` é ``{rótulo: valores[nv*nl]}``.

    É a “ressurreição” do gráfico 3D: o MINIMOS gera estes dados, mas o
    visualizador antigo (plotmtv) não existe mais — aqui lemos direto o
    arquivo. Identificamos cada campo pelo NOME do atributo (o
    ``attributeType`` às vezes vem rotulado de forma inconsistente) e só
    expomos os campos da grade completa.
    """
    if not pif_text:
        return [], [], {}
    fnum = re.compile(r'[-+]?\d+\.\d+E[-+]?\d+')

    def floats_before_semicolon(block):
        out = []
        for line in block.splitlines():
            for m in fnum.findall(line.split(";")[0]):
                out.append(float(m))
        return out

    lat: list[float] = []
    vert: list[float] = []
    if "(axes" in pif_text:
        ax = pif_text.split("(axes", 1)[1]
        parts = ax.split("(valueList")
        if len(parts) >= 3:
            vert = floats_before_semicolon(parts[1][:parts[1].find(")")])
            lat = floats_before_semicolon(parts[2][:parts[2].find(")")])
    nl, nv = len(lat), len(vert)
    n = nl * nv
    campos: dict[str, list[float]] = {}
    if n == 0:
        return lat, vert, campos
    # nome do atributo no PIF -> rótulo amigável (só campos escalares na grade cheia)
    alvos = [
        ("ElectrostaticPotential", "Potencial (V)"),
        ("SpaceChargeConcentration", "Carga espacial (cm⁻³)"),
        ("ElectricField_", "Campo elétrico |E| (V/cm)"),
        ("ElectricFieldLateral", "Campo elétrico lateral (V/cm)"),
        ("ElectricFieldVertical", "Campo elétrico vertical (V/cm)"),
    ]
    for nome, rotulo in alvos:
        i = pif_text.find("(attribute " + nome)
        if i < 0:
            continue
        blk = pif_text[i:]
        if "(valueList" not in blk:
            continue
        vlist = blk.split("(valueList", 1)[1]
        end = vlist.find("))")
        vals = floats_before_semicolon(vlist[:end if end > 0 else len(vlist)])
        if len(vals) == n:                      # só a grade completa (nv x nl)
            campos[rotulo] = vals
    return lat, vert, campos


def parse_minimos_iv(iv_text: str) -> tuple[list[str], list[tuple[float, ...]]]:
    """Lê o arquivo ``.iv`` (fort.61) do MINIMOS.

    Formato real::

        ##  UB (V)  UD (V)  UG (V)  US (V)  IB (A)  ID (A)  IG (A)  IS (A)
        <linhas numéricas>

    Devolve ``(headers, rows)``; ``headers`` são nomes curtos (UB, UD, …, IS).
    """
    if not iv_text:
        return [], []
    headers: list[str] = []
    rows: list[tuple[float, ...]] = []
    for ln in iv_text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("##") or (not headers and re.search(r"[A-Za-z]", s) and "(" in s):
            # cabeçalho: pega os rótulos antes dos parênteses (UB, UD, ...)
            headers = re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*\(", s)
            continue
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eEdD][-+]?\d+)?", s)
        if len(nums) >= 2:
            try:
                rows.append(tuple(float(x.replace("D", "E").replace("d", "e"))
                                  for x in nums))
            except ValueError:
                pass
    if rows:
        ncol = Counter(len(r) for r in rows).most_common(1)[0][0]
        rows = [r for r in rows if len(r) == ncol]
        if headers and len(headers) != ncol:
            headers = []  # cabeçalho não casa com os dados; ignora
    return headers, rows


def junction_threshold(data: list[Point]) -> float:
    """Limiar de magnitude adequado a um perfil, para :func:`detect_junctions`.

    O padrão herdado de ``detect_junctions`` (1e16 cm⁻³) foi calibrado para
    perfis de substrato pesadamente dopado: num diodo sobre substrato de
    1e15 cm⁻³ o lado p nunca alcança o limiar e a junção — que existe — não é
    encontrada. Em vez de mexer na função (o comportamento dela está coberto
    por teste de paridade com a versão anterior), derivamos o limiar do próprio
    perfil: metade da magnitude do substrato, que é o último ponto da tabela.

    A fração é um décimo, não a metade, porque a janela de três pontos que
    ``detect_junctions`` examina de cada lado ainda não alcançou o nível do
    substrato tão perto da junção. O piso de 1e13 continua descartando o
    artefato numérico da superfície (óxido→Si), que fica ordens de magnitude
    abaixo do substrato.
    """
    if not data:
        return 1e16
    substrato = abs(data[-1][1])
    return max(1e13, min(1e16, substrato * 0.1))


def parse_minimos_vt(ref_text: str) -> float | None:
    """Tensão de limiar da referência do MINIMOS (``MODEL=THRES``), em volts.

    O motor imprime ``THRESHOLD VOLTAGE`` a cada iteração do laço que a
    procura; o valor que vale é o **último**, já convergido.
    """
    if not ref_text:
        return None
    achados = re.findall(r"THRESHOLD\s+VOLTAGE\s*=\s*([-+]?[\d.]+(?:[eEdD][-+]?\d+)?)",
                         ref_text, re.IGNORECASE)
    if not achados:
        return None
    try:
        return float(achados[-1].replace("D", "E").replace("d", "e"))
    except ValueError:
        return None


# ── SUPREM-IV.GS ──────────────────────────────────────────────────────────
#
# O SUPREM-IV não grava tabela em arquivo como o SUPREM-III: o cartão
# ``print.1d`` escreve na saída padrão. São dois formatos, os dois lidos aqui:
#
#   x coordinate in um	          doping	Material
#          0.00000000	-1.142918e+19   	oxide
#
#   layer  material        thickness  Integrated
#   num    type            microns    doping
#    0     oxide           -0.075     0.000000e+00
#
# Os blocos se repetem, um por ``print.1d``, e a mesma execução pode misturar
# os dois. Daí os parsers serem separados e tolerantes a blocos intercalados.

#: Materiais que o SUPREM-IV nomeia na terceira coluna do ``print.1d``.
S4_MATERIALS = ("gas", "oxide", "oxynitride", "nitride", "silicon", "poly",
                "photoresist", "aluminum", "gaas")

# Num corte vertical 2-D (``print.1d x.value=``) o motor rotula a abscissa
# como "y coordinate", porque o que varia ao longo da tabela é a
# profundidade. Casar só "x" perderia todo corte 2-D.
_S4_HEADER = re.compile(r"[xyz]\s+coordinate\s+in\s+um", re.IGNORECASE)
_S4_LAYER_HEADER = re.compile(r"\blayer\b.*\bmaterial\b.*\bthickness\b", re.IGNORECASE)
_S4_ROW = re.compile(
    r"^\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+"      # x em µm
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s+"          # valor da grandeza
    r"([A-Za-z]+)\s*$")                              # material


def parse_print_1d(text: str) -> list[list[tuple[float, float, str]]]:
    """Lê todos os blocos de perfil do ``print.1d``, na ordem em que saíram.

    Devolve uma lista de blocos; cada bloco é ``[(x_um, valor, material), ...]``
    na ordem impressa pelo motor. O ``x`` pode ser **negativo** — o SUPREM-IV
    põe a origem na interface do substrato, então uma camada depositada por
    cima tem coordenada negativa. Quem só quer o perfil no silício filtra por
    material; quem quer a pilha inteira usa como vem.

    O valor é o que o ``select z=`` pediu: ``doping`` vem com sinal
    (+ tipo n, − tipo p), e uma expressão ``log10(...)`` vem já em log.
    """
    if not text:
        return []
    blocos: list[list[tuple[float, float, str]]] = []
    atual: list[tuple[float, float, str]] | None = None
    for raw in text.replace("\r", "").split("\n"):
        if _S4_HEADER.search(raw):
            # Um cabeçalho fecha o bloco anterior e abre o próximo.
            if atual:
                blocos.append(atual)
            atual = []
            continue
        if atual is None:
            continue
        m = _S4_ROW.match(raw)
        if m is None:
            if raw.strip():
                # Qualquer outra linha com conteúdo encerra o bloco (mensagem
                # do solver, cabeçalho de camadas, texto do motor).
                blocos.append(atual)
                atual = None
            continue
        try:
            x, valor = float(m.group(1)), float(m.group(2))
        except ValueError:
            continue
        atual.append((x, valor, m.group(3).lower()))
    if atual:
        blocos.append(atual)
    return [b for b in blocos if b]


def parse_print_1d_profile(text: str, material: str = "silicon") -> list[Point]:
    """Perfil ``(profundidade_µm, valor)`` do último bloco do ``print.1d``.

    Recorta no material pedido (``"silicon"`` por padrão) e **reancora a
    profundidade em zero na superfície desse material** — é o que a interface
    do MOS-Studio desenha e o que o SUPREM-III já entregava, de modo que os
    dois motores possam ir ao mesmo gráfico. ``material=""`` devolve a pilha
    inteira com as coordenadas originais do motor.
    """
    blocos = parse_print_1d(text)
    if not blocos:
        return []
    bloco = blocos[-1]
    if material:
        bloco = [r for r in bloco if r[2] == material.lower()]
        if not bloco:
            return []
        origem = min(r[0] for r in bloco)
    else:
        origem = 0.0
    pontos = [(r[0] - origem, r[1]) for r in bloco]
    pontos.sort(key=lambda p: p[0])
    return pontos


@dataclass
class S4Layer:
    """Uma camada da tabela ``print.1d layers``.

    ``top`` e ``bottom`` são posições em µm medidas da superfície original do
    substrato: negativas acima dela (material depositado ou óxido crescido
    para fora), positivas para dentro. ``integrated`` é a dopagem integrada da
    camada em cm⁻², com sinal (+ tipo n, − tipo p).
    """

    material: str
    top: float
    bottom: float
    integrated: float = 0.0

    @property
    def thickness(self) -> float:
        return self.bottom - self.top


def parse_print_1d_rows(text: str) -> list[tuple[str, float, float]]:
    """Linhas cruas da tabela de camadas: ``(material, posição, integrado)``.

    A coluna que o motor rotula "thickness microns" **não** é espessura: é a
    posição cumulativa da interface de baixo de cada linha, e a primeira linha
    é o topo da pilha. Confirmado contra o motor: 0,075 µm de óxido depositado
    mais 15 min de O₂ seco a 1000 °C dão as linhas −0,079 / 0,003 / 0,500 num
    substrato de 0,5 µm — ou seja, 0,082 µm de óxido (0,075 depositados mais
    0,007 crescidos, dos quais 0,003 consumiram silício) e 0,497 µm de
    silício. Ler a coluna como espessura daria 0,079 + 0,003 + 0,500.
    """
    if not text:
        return []
    out: list[tuple[str, float, float]] = []
    dentro = False
    for raw in text.replace("\r", "").split("\n"):
        if _S4_LAYER_HEADER.search(raw):
            dentro = True
            out = []
            continue
        if not dentro:
            continue
        campos = raw.split()
        if len(campos) < 3 or not campos[0].isdigit():
            # A segunda linha do cabeçalho ("num type microns …") cai aqui e é
            # ignorada; qualquer outro texto encerra a tabela.
            if raw.strip() and not campos[0].lower().startswith("num"):
                dentro = False
            continue
        if campos[1].lower() not in S4_MATERIALS:
            continue
        try:
            pos = float(campos[2])
            integ = float(campos[3]) if len(campos) > 3 else 0.0
        except ValueError:
            continue
        out.append((campos[1].lower(), pos, integ))
    return out


def parse_print_1d_stack(text: str) -> list[S4Layer]:
    """Camadas com topo, base e espessura de verdade.

    Descarta as camadas de espessura nula, que o motor emite quando uma
    deposição foi corroída naquele corte.
    """
    linhas = parse_print_1d_rows(text)
    if len(linhas) < 2:
        return []
    camadas: list[S4Layer] = []
    topo = linhas[0][1]
    for material, pos, integ in linhas[1:]:
        if pos - topo > 1e-9:
            camadas.append(S4Layer(material, topo, pos, integ))
        topo = pos
    return camadas


def parse_print_1d_layers(text: str) -> list[tuple[str, float]]:
    """Camadas como ``[(material, espessura_µm)]``.

    Forma curta que as telas 1-D consomem. Camadas de mesmo material
    separadas por uma junção aparecem como entradas distintas, porque é isso
    que o motor relata e é informação útil (a primeira é a região dopada).
    """
    return [(c.material, round(c.thickness, 6))
            for c in parse_print_1d_stack(text)]


def parse_print_1d_junction(text: str) -> float | None:
    """Profundidade de junção (µm) lida da tabela de camadas, ou ``None``.

    O motor quebra o silício na junção e troca o sinal da dopagem integrada
    entre as duas partes. A profundidade é medida da superfície do silício,
    não do topo da pilha — é a definição que a literatura usa e a que a tela
    de Resultados mostra.
    """
    camadas = parse_print_1d_stack(text)
    silicio = [c for c in camadas if c.material in ("silicon", "poly", "gaas")]
    if len(silicio) < 2:
        return None
    for a, b in zip(silicio, silicio[1:]):
        if a.material == b.material and a.integrated * b.integrated < 0:
            return round(a.bottom - silicio[0].top, 6)
    return None


def parse_print_1d_oxide(text: str) -> float | None:
    """Espessura total de óxido (µm), ou ``None`` se a tabela não listou óxido.

    Soma as camadas de óxido: uma oxidação sobre óxido depositado aparece
    como camadas consecutivas e o que interessa à análise de oxidação é o
    total.
    """
    total = sum(c.thickness for c in parse_print_1d_stack(text)
                if c.material == "oxide")
    return round(total, 6) if total > 1e-9 else None
