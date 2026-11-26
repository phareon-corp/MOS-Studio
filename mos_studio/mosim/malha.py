"""Malhas tensoriais do MOSIM.

Duas coisas moram aqui:

* ``linhas``: malha graduada a partir de pontos de interesse (a malha fina
  original do MOSIM, usada quando se pede ``resolucao`` explícita);
* a **malha adaptativa no estilo do MINIMOS** (``inicial`` + ``adaptar``): uma
  malha grossa construída pela razão áurea e refinada pela solução, dividindo
  ao meio todo intervalo cuja função de peso (BWF) passe de 1. Os critérios e
  os valores padrão são os da diretiva GRID do manual do MINIMOS 6 (DPXC,
  DPXD, DPYC, DPYD em volts; PGMI como espaçamento mínimo). Medido contra o
  próprio MINIMOS: dentro do canal, o BWF dele é exatamente max Δψ / DPXC.

Por que imitar a malha grossa em vez de usar uma fina: o MINIMOS resolve numa
malha de ~36×40 linhas, e a corrente que ele imprime carrega o erro de
discretização dessa malha (no exa2d, +7 % sobre o valor convergido). Quem
troca o MINIMOS pelo MOSIM espera os mesmos números; a malha fina dá números
"mais certos" e diferentes. O teste de sensibilidade mostrou que o que pesa é
a densidade de linhas por região, não a posição exata de cada uma.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

PHI = (1.0 + math.sqrt(5.0)) / 2.0


def linhas(a: float, b: float, alvos: list[tuple[float, float]], hmax: float,
           crescimento: float = 1.25) -> np.ndarray:
    """Linhas entre ``a`` e ``b`` com espaçamento local h(x) = min_f(h_f + (g−1)·|x−x_f|).

    ``alvos`` é uma lista de (posição, espaçamento desejado na posição).
    Os próprios alvos (dentro do intervalo) entram como linhas.
    """
    g = crescimento - 1.0

    def h(x):
        v = hmax
        for xf, hf in alvos:
            v = min(v, hf + g * abs(x - xf))
        return v

    fixos = sorted({a, b, *[xf for xf, _ in alvos if a < xf < b]})
    out = [fixos[0]]
    for lo, hi in zip(fixos[:-1], fixos[1:]):
        # marcha de lo até hi; o último passo é distribuído para cair em hi
        pts = [lo]
        x = lo
        while True:
            step = min(h(x), h(min(x + h(x), hi)))
            if x + 1.5 * step >= hi:
                break
            x += step
            pts.append(x)
        pts.append(hi)
        # suaviza: reescala os pontos interiores para que o último intervalo não fique estreito
        pts = np.array(pts)
        if len(pts) > 2:
            d = np.diff(pts)
            d[-2:] = d[-2:].sum() / 2.0
            pts = lo + np.concatenate(([0.0], np.cumsum(d)))
            pts[-1] = hi
        out.extend(pts[1:].tolist())
    return np.array(out)


# ── malha adaptativa no estilo do MINIMOS ─────────────────────────────────

@dataclass
class ParamMalha:
    """Parâmetros da diretiva GRID (unidades do deck convertidas: V e µm)."""
    dpxc: float = 0.7        # V, Δψ máximo entre linhas x no canal
    dpxd: float = 1.25       # V, fora do canal
    dpyc: float = 0.7
    dpyd: float = 1.25
    pgmi: float = 0.25e-3    # µm, espaçamento mínimo nas atualizações (0,25e-7 cm)
    dopx: float = 0.35       # peso da dopagem em x (BWF = DOPX·max Δasinh(C/2nᵢ))
    dopy: float = 0.35
    dgmi: float = 0.02       # µm, espaçamento mínimo pelo critério de dopagem (20e-7 cm)
    gfill: int = 6           # seções sob a porta na malha inicial
    max_adapt: int = 8       # rodadas de adaptação por ponto
    h0_y: float = 0.0016     # µm, primeiro intervalo no silício (malha inicial)
    equi_c: float = 1.3      # V/µm, parcela uniforme do peso na redistribuição sob a porta

    @classmethod
    def do_deck(cls, deck) -> "ParamMalha":
        g = deck.uma("GRID")
        p = cls()
        for chave, attr, escala in (("DPXC", "dpxc", 1.0), ("DPXD", "dpxd", 1.0),
                                    ("DPYC", "dpyc", 1.0), ("DPYD", "dpyd", 1.0),
                                    ("PGMI", "pgmi", 1e4), ("DOPX", "dopx", 1.0),
                                    ("DOPY", "dopy", 1.0), ("DGMI", "dgmi", 1e4)):
            v = g.num(chave)
            if v is not None:
                setattr(p, attr, v * escala)
        v = g.num("GFILL")
        if v is not None:
            p.gfill = int(v)
        return p


def _seq_y() -> list[float]:
    """Linhas iniciais em y no silício (µm), as mesmas em todo deck do MINIMOS.

    Medidas nas malhas finais dele: 0; 1,62; 2,80; 4,72; 6,63; 9,74; 14,75 nm…
    os intervalos crescem pela razão áurea a partir do quinto.
    """
    v = [0.0, 1.618e-3, 2.80e-3, 4.72e-3, 6.63e-3, 9.74e-3]
    h = 5.01e-3
    while v[-1] < 100.0:
        v.append(v[-1] + h)
        h *= PHI
    return v


SEQ_Y = _seq_y()

#: Linhas que o MINIMOS acrescenta junto à interface quando o canal inverte
#: (µm). Sempre as mesmas nas malhas finais dele (exa2d, exavl, exthr, proj56B…):
#: 0,62; 1,24; 2,07; 3,53 nm. Regra medida, não critério do manual.
LINHAS_INVERSAO = (0.618e-3, 1.236e-3, 2.07e-3, 3.53e-3)


def _passos_aureos(h: float, minimo: float) -> list[float]:
    """Passos h, h, φh, φ²h… até a soma alcançar ``minimo``."""
    passos = [h]
    while sum(passos) < minimo - 1e-12:
        passos.append(h if len(passos) == 1 else passos[-1] * PHI)
    return passos


def _degrau_aureo(v: float) -> float:
    """Menor φ^k (k inteiro) que não fica abaixo de ``v``."""
    k = math.ceil(math.log(max(v, 1e-6)) / math.log(PHI) - 1e-9)
    return PHI ** k


def inicial(L: float, sgap: float, dgap: float, tox: float, xj: float, sub: float,
            profundidade: float, p: ParamMalha, extra_x: tuple[float, ...] = (),
            extra_y: tuple[float, ...] = ()) -> tuple[np.ndarray, np.ndarray]:
    """Malha inicial (µm): x com o contato de fonte à esquerda, y com o isolante em y<0.

    * sob a porta, ``gfill`` seções iguais, com a seção da ponta subdividida
      pela razão áurea (como faz o MINIMOS);
    * os intervalos de porta-fonte e porta-dreno, divididos ao meio;
    * nos contatos, passos áureos a partir da borda até cobrir ~2·xj;
    * em y, crescimento áureo a partir da interface até o fundo, que cai num
      degrau áureo (0,618; 1; 1,618; 2,618 µm…).
    """
    sec = L / p.gfill
    gate = [k * sec for k in range(p.gfill + 1)]
    gate += [sec / PHI ** 2, L - sec / PHI ** 2]
    alcance = max(2.0 * xj, 3.0 * sub, 0.3)
    xs_f = [-sgap]
    for passo in _passos_aureos(PHI * sgap / 2.0, alcance):
        xs_f.append(xs_f[-1] - passo)
    xs_d = [L + dgap]
    for passo in _passos_aureos(PHI * dgap / 2.0, alcance):
        xs_d.append(xs_d[-1] + passo)
    xs = sorted(set(np.round(gate + xs_f + xs_d + [-sgap / 2.0, L + dgap / 2.0, *extra_x], 9)))

    fundo = _degrau_aureo(profundidade)
    ys = [v for v in SEQ_Y if v < fundo * 0.999]
    if fundo - ys[-1] < 0.3 * (ys[-1] - ys[-2]):
        ys[-1] = fundo
    else:
        ys.append(fundo)
    ys += [v for v in extra_y if 0 < v < fundo]
    # isolante: espelha os primeiros intervalos do silício até a espessura do óxido
    ins = []
    yy, h = 0.0, p.h0_y
    while yy + h < tox * 0.999:
        yy += h
        ins.append(-yy)
        h *= PHI
    ins.append(-tox)
    ys = sorted(set(np.round(ys + ins, 9)))
    return np.array(xs), np.array(ys)


def bwf_dopagem(C: np.ndarray, ni: float, p: ParamMalha) -> tuple[np.ndarray, np.ndarray]:
    """Peso pela dopagem: DOPX·max Δasinh(C/2nᵢ) em cada intervalo.

    Medido nas malhas do MINIMOS: o único intervalo sem junção que escapa da
    divisão tem 0,35 × 2,74 = 0,96; os que cruzam a junção têm peso enorme e
    param quando a metade ficaria abaixo de DGMI.
    """
    a = np.arcsinh(C / (2.0 * ni))
    bx = p.dopx * np.abs(np.diff(a, axis=1)).max(axis=0)
    by = p.dopy * np.abs(np.diff(a, axis=0)).max(axis=1)
    return bx, by


def bwf(xs: np.ndarray, ys_si: np.ndarray, psi_v: np.ndarray, L: float,
        p: ParamMalha) -> tuple[np.ndarray, np.ndarray]:
    """Função de peso de cada intervalo (x e y), a partir do potencial no silício (V).

    ``psi_v`` tem forma (len(ys_si), len(xs)). Canal = colunas/linhas com
    0 ≤ x ≤ L; lá vale DPXC/DPYC, fora, DPXD/DPYD.
    """
    dx = np.abs(np.diff(psi_v, axis=1))          # (ny, nx−1)
    xm = 0.5 * (xs[1:] + xs[:-1])
    canal_x = (xm >= -1e-9) & (xm <= L + 1e-9)
    bx = dx.max(axis=0) / np.where(canal_x, p.dpxc, p.dpxd)
    dy = np.abs(np.diff(psi_v, axis=0))          # (ny−1, nx)
    canal_col = (xs >= -1e-9) & (xs <= L + 1e-9)
    by = np.maximum(dy[:, canal_col].max(axis=1, initial=0.0) / p.dpyc,
                    dy[:, ~canal_col].max(axis=1, initial=0.0) / p.dpyd)
    return bx, by


def _corte_aureo(v: np.ndarray, i: int) -> float:
    """Ponto que divide [v[i], v[i+1]] em 0,382/0,618, com a parte menor do
    lado do vizinho menor (a malha cresce suave a partir dos intervalos finos)."""
    h = np.diff(v)
    esq = h[i - 1] if i > 0 else np.inf
    dir_ = h[i + 1] if i + 1 < len(h) else np.inf
    curto = h[i] / PHI ** 2
    return v[i] + curto if esq <= dir_ else v[i + 1] - curto


def refinar(v: np.ndarray, w: np.ndarray, pgmi: float, w_dop: np.ndarray | None = None,
            dgmi: float = 0.02) -> np.ndarray | None:
    """Uma rodada de refinamento; devolve as linhas novas ou None se nada mudou.

    * critério de potencial (``w``): divide ao meio, se a metade ≥ ``pgmi``
      (os registros do MINIMOS mostram a linha nova no ponto médio);
    * critério de dopagem (``w_dop``): divide pela razão áurea, se o intervalo
      ≥ φ·``dgmi`` (as malhas do MINIMOS têm pares 0,0213 + 0,0131 µm);
    * depois, suaviza: nenhum intervalo passa de φ² vezes o vizinho.
    """
    h = np.diff(v)
    meio = (w > 1.0) & (h / 2.0 >= pgmi)
    aureo = np.zeros_like(meio)
    if w_dop is not None:
        aureo = (w_dop > 1.0) & (h >= PHI * dgmi) & ~meio
    if not meio.any() and not aureo.any():
        return None
    novos = list(0.5 * (v[1:] + v[:-1])[meio])
    novos += [_corte_aureo(v, i) for i in np.where(aureo)[0]]
    return suavizar(np.sort(np.concatenate([v, novos])))


def suavizar(v: np.ndarray, razao: float = PHI ** 2 * 1.01, limite: int = 200) -> np.ndarray:
    """Divide (pela razão áurea) todo intervalo maior que ``razao`` vezes um vizinho."""
    v = np.asarray(v, dtype=float)
    for _ in range(limite):
        h = np.diff(v)
        if len(h) < 2:
            return v
        grande = np.zeros(len(h), dtype=bool)
        grande[1:] |= h[1:] > razao * h[:-1]
        grande[:-1] |= h[:-1] > razao * h[1:]
        if not grande.any():
            return v
        novos = [_corte_aureo(v, i) for i in np.where(grande)[0]]
        v = np.sort(np.concatenate([v, novos]))
    return v


def equidistribuir(xs: np.ndarray, grad: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    """Redistribui as linhas em [a, b] (mesma contagem) para igualar ∫(g + c)dx entre elas.

    ``grad`` é |∂ψ/∂x| máximo (V/µm) em cada intervalo de ``xs``. A malha final
    do MINIMOS tem linhas que nunca foram inseridas (no exa2d, 0,667; 0,675;
    0,683 µm, onde o canal estrangula): depois de inserir, ele as desloca para
    onde o potencial varia mais. Sem isso, a corrente de canal curto sai até
    5 % abaixo da dele com o mesmo número de linhas.
    """
    sel = (xs >= a - 1e-9) & (xs <= b + 1e-9)
    k = int(sel.sum())
    if k < 3:
        return xs
    xm = 0.5 * (xs[1:] + xs[:-1])
    xx = np.linspace(a, b, 4001)
    w = np.interp(xx, xm, grad) + c
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (w[1:] + w[:-1]) * np.diff(xx))])
    novos = np.interp(np.linspace(0.0, cum[-1], k), cum, xx)
    novos[0], novos[-1] = a, b
    return np.sort(np.concatenate([xs[xs < a - 1e-9], novos, xs[xs > b + 1e-9]]))
