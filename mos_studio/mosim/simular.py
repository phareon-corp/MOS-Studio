"""Monta o dispositivo a partir do deck e resolve pontos de polarização."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import fisica, malha, perfil as perfil_mod
from .deck import Deck, ErroDeck
from .solver import Dispositivo, Estado, Geometria


@dataclass
class Modelo:
    deck: Deck
    canal_n: bool
    W: float            # cm
    L: float            # cm
    tins: float         # cm
    eps_ins: float
    wf: float           # V (sinal físico)
    T: float
    nb: float           # dopagem do substrato (módulo)
    perfil: perfil_mod.Perfil
    disp: Dispositivo
    sgap: float
    dgap: float
    xj: float           # µm
    sub: float          # µm (subdifusão lateral)
    nss: float
    est: dict = field(default_factory=dict)

    @property
    def sinal(self) -> float:
        return 1.0 if self.canal_n else -1.0


def _funcao_trabalho(dev, canal_n: bool) -> float:
    g = dev.chaves.get("GATE")
    if g is None:
        raise ErroDeck("falta GATE na diretiva DEVICE")
    try:
        return float(g)
    except ValueError:
        c = g.upper()[0]
        if c not in fisica.FUNCAO_TRABALHO:
            raise ErroDeck(f"material de porta desconhecido: {g}")
        return fisica.FUNCAO_TRABALHO[c]


def _profundidade_juncao(prof: perfil_mod.Perfil, x_um: float) -> float:
    y = np.linspace(0, 5.0, 50001)
    n = prof.liquida(np.full_like(y, x_um), y)
    s = np.sign(n)
    i = np.where(s[1:] != s[:-1])[0]
    if not len(i):
        return 0.0
    k = i[0]
    return float(y[k] - n[k] * (y[k + 1] - y[k]) / (n[k + 1] - n[k]))


def _subdifusao(prof: perfil_mod.Perfil) -> float:
    x = np.linspace(-2.0, prof.L / 2, 40001)
    n = prof.liquida(x, np.zeros_like(x))
    s = np.sign(n)
    i = np.where(s[1:] != s[:-1])[0]
    if not len(i):
        return 0.0
    k = i[0]
    return float(x[k] - n[k] * (x[k + 1] - x[k]) / (n[k + 1] - n[k]))


def construir(deck: Deck, resolucao: float = 1.0, linhas_x=None, linhas_y=None) -> Modelo:
    dev = deck.uma("DEVICE")
    if (dev.txt("MAT") or "SI")[0] == "G":
        raise ErroDeck("GaAs/MESFET ainda não é suportado pelo motor aberto")
    canal = (dev.txt("CHANNEL") or "")[:1]
    if canal not in ("N", "P"):
        raise ErroDeck("CHANNEL deve ser N ou P")
    canal_n = canal == "N"
    W, L, tins = dev.num("W"), dev.num("L"), dev.num("TINS")
    if W is None or L is None or tins is None:
        raise ErroDeck("DEVICE precisa de W, L e TINS")
    if tins <= 0:
        raise ErroDeck("TINS=0 (MESFET) ainda não é suportado pelo motor aberto")
    if "FILM" in dev:
        raise ErroDeck("SOI (FILM) ainda não é suportado pelo motor aberto")
    ins = dev.chaves.get("INS")
    if ins is None:
        eps_ins = fisica.EPS_OX
    else:
        try:
            eps_ins = float(ins)
        except ValueError:
            eps_ins = fisica.EPS_NIT if ins.upper().startswith("N") else fisica.EPS_OX
    opt = deck.uma("OPTION")
    T = opt.num("TEMP", 300.0)
    wf = _funcao_trabalho(dev, canal_n)
    sgap = dev.num("SGAP", 10 * tins)
    dgap = dev.num("DGAP", sgap)
    prof = perfil_mod.montar(deck, canal_n, L * 1e4, tins * 1e4)
    nss = deck.uma("INTERFACE").num("NSS", 0.0) or 0.0
    xj = _profundidade_juncao(prof, -3.0 - 10 * prof.sigma_x)
    sub = _subdifusao(prof) if prof.sd else 0.0
    nb = abs(prof.nb)

    # ── malha (µm) ──
    L_um, tox_um = L * 1e4, tins * 1e4
    sg, dg = sgap * 1e4, dgap * 1e4
    ni = fisica.intrinseca(T)
    vt = fisica.tensao_termica(T)
    nb_eff = max(nb, 1e12)
    wdep = math.sqrt(2 * fisica.EPS_SI * fisica.EPS0 * (10.0 + 1.0) / (fisica.Q * nb_eff)) * 1e4
    ymax = min(max(2.0 * xj + 0.5, xj + wdep, 1.0), 60.0)
    xcont = max(0.5, 3 * sub, xj)
    xl, xr = -(sg + xcont), L_um + dg + xcont
    r = resolucao
    alvos_x = [(-sg, 0.02 / r), (0.0, min(0.005, L_um / 60) / r), (L_um, min(0.005, L_um / 60) / r),
               (L_um + dg, 0.02 / r)]
    if prof.sd:
        alvos_x += [(sub, min(0.005, L_um / 60) / r), (L_um - sub, min(0.005, L_um / 60) / r)]
    alvos_x = [(a, h) for a, h in alvos_x if xl < a < xr]
    xs = malha.linhas(xl, xr, alvos_x, max(min(L_um / 25, 0.5), 0.02) / r, 1.0 + 0.2 * r ** -0.5)
    alvos_y = [(0.0, 0.0003 / r)]
    if xj > 0:
        alvos_y.append((xj, max(xj / 40, 0.002) / r))
    ys_si = malha.linhas(0.0, ymax, alvos_y, max(ymax / 20, 0.05) / r, 1.0 + 0.25 * r ** -0.5)
    nox = max(4, int(4 * r))
    ys_ox = np.linspace(-tox_um, 0.0, nox + 1)[:-1]
    ys = np.concatenate([ys_ox, ys_si])
    if len(xs) * len(ys) > 60000 and linhas_x is None:
        raise ErroDeck(f"geometria fora do alcance do motor aberto (malha de {len(xs)}×{len(ys)}): "
                       "confira L, W e as unidades (cm)")
    if linhas_x is not None:
        xs = np.asarray(linhas_x, dtype=float)
    if linhas_y is not None:
        ys = np.asarray(linhas_y, dtype=float)
    X, Y = np.meshgrid(xs, ys)
    C = np.where(Y >= 0, prof.liquida(X, np.maximum(Y, 0)), 0.0).ravel()
    CI = np.where(Y >= 0, prof.total(X, np.maximum(Y, 0)), 0.0).ravel()
    s = 1.0 if canal_n else -1.0
    mob = fisica.Mobilidade(T, "n" if canal_n else "p")
    _aplicar_pesos(mob, deck)
    geo = Geometria(x=xs * 1e-4, y=ys * 1e-4, L=L, tox=tins, eps_ins=eps_ins,
                    x_fonte=-sgap, x_dreno=L + dgap)
    disp = Dispositivo(geo=geo, C=s * C, CI=CI, T=T, nss=s * nss, wf=s * wf, mob=mob, ni=ni)
    return Modelo(deck=deck, canal_n=canal_n, W=W, L=L, tins=tins, eps_ins=eps_ins, wf=wf,
                  T=T, nb=nb, perfil=prof, disp=disp, sgap=sgap, dgap=dgap, xj=xj, sub=sub,
                  nss=nss)


def _aplicar_pesos(mob: fisica.Mobilidade, deck: Deck):
    d = deck.uma("MOBILITY")
    if not d.chaves:
        return
    pesos = {k: d.num(k) for k in ("ML", "MI", "MC", "MR", "MS", "MT", "MV", "MB") if k in d}
    novo = fisica.Mobilidade(mob.T, mob.portador, **pesos)
    mob.__dict__.update(novo.__dict__)


def resolver_ponto(m: Modelo, U: dict[str, float], est: Estado | None = None, log=None,
                   passo_max: float = 0.5) -> tuple[Estado, float]:
    """Resolve o ponto U (tensões físicas) e devolve (estado, ID em A).

    Faz continuação em pequenos passos a partir do último estado convergido.
    """
    s = m.sinal
    alvo = {k: s * v for k, v in U.items()}
    d = m.disp
    if est is None:
        base = {"S": alvo["S"], "D": alvo["S"], "G": alvo["G"], "B": alvo["B"]}
        e0 = d.inicial(base)
        e0 = d.resolver(base, e0, eletrons=False, log=log)
        e0 = d.resolver(base, e0, log=log)
        atual = base
        est = e0
    else:
        atual = dict(est_u := m.est.get("U", alvo))
    # continuação linear em todas as tensões
    delta = max(abs(alvo[k] - atual[k]) for k in alvo)
    npassos = max(1, int(math.ceil(delta / passo_max)))
    for k in range(1, npassos + 1):
        t = k / npassos
        u = {kk: atual[kk] + t * (alvo[kk] - atual[kk]) for kk in alvo}
        u_ant = {kk: atual[kk] + (k - 1) / npassos * (alvo[kk] - atual[kk]) for kk in alvo}
        est = d.prever(est, u_ant, u)
        est = d.resolver(u, est, log=log, tol_mu=1e-5 if k == npassos else 1e-2,
                         tol=1e-10 if k == npassos else 1e-3,
                         tol_n=1e-9 if k == npassos else 1e-2)
    m.est["U"] = alvo
    mu = est.mu_x
    idr = d.corrente_canal(est.psi, est.n, mu)
    return est, s * idr * m.W


def corrente_limiar(m: Modelo) -> float:
    """Critério de corrente do MODEL=THRES: OPTION CURRENT ou 1e-7·W/L A."""
    c = m.deck.uma("OPTION").num("CURRENT")
    if c is not None:
        return abs(c)
    return 1e-7 * m.W / m.L


def estimativa_limiar(m: Modelo, U: dict[str, float]) -> float:
    """Limiar de depleção 1-D no meio do canal (só para o chute inicial)."""
    from scipy.integrate import cumulative_trapezoid
    d = m.disp
    vt, ni = d.vt, d.ni
    s = m.sinal
    nb = max(m.nb, 1e10)
    phif = vt * math.log(nb / ni)
    cox = m.eps_ins * fisica.EPS0 / m.tins
    vfb = s * m.wf - phif - fisica.Q * s * m.nss / cox
    y = np.linspace(0, 5, 20001)
    N = np.maximum(-s * m.perfil.liquida(np.full_like(y, m.L * 1e4 / 2), y), 0.0)
    ycm = y * 1e-4
    eps = fisica.EPS_SI * fisica.EPS0
    Qc = cumulative_trapezoid(N, ycm, initial=0)
    Mc = cumulative_trapezoid(N * ycm, ycm, initial=0)
    alvo = 2 * phif + s * (U["S"] - U["B"])
    psi = fisica.Q * (ycm * Qc - Mc) / eps
    k = min(int(np.searchsorted(psi, alvo)), len(y) - 1)
    return s * (vfb + alvo + fisica.Q * Qc[k] / cox) + U["S"] * 0


def limiar(m: Modelo, U: dict[str, float], est: Estado | None = None, log=None,
           tol: float = 2e-4) -> tuple[float, float, Estado]:
    """Tensão de porta em que |ID| atinge o critério (secante em ln ID)."""
    alvo = corrente_limiar(m)
    ug = estimativa_limiar(m, U)
    pts: list[tuple[float, float]] = []
    for _ in range(40):
        u = dict(U, G=ug)
        est, idr = resolver_ponto(m, u, est, log=log, passo_max=0.25)
        i = max(abs(idr), 1e-30)
        pts.append((ug, math.log(i)))
        if log:
            log(f"  limiar: UG={ug:.4f} ID={idr:.4e} alvo={alvo:.3e}")
        if len(pts) == 1:
            # inclinação de sublimiar típica: 1 década / 90 mV
            inc = (math.log(alvo) - pts[-1][1]) / (math.log(10) / 0.09)
        else:
            (u1, l1), (u2, l2) = pts[-2], pts[-1]
            sl = (l2 - l1) / (u2 - u1) if u2 != u1 else math.log(10) / 0.09
            if not math.isfinite(sl) or sl * m.sinal <= 0:
                sl = m.sinal * math.log(10) / 0.09
            inc = (math.log(alvo) - l2) / sl
        inc = max(-0.5, min(0.5, inc))
        if abs(inc) < tol:
            return ug + inc, idr, est
        ug += inc * (1 if m.sinal > 0 else 1)
    return ug, idr, est
