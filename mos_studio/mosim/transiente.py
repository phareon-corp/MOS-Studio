"""Simulação transiente do MOSIM (diretiva TRANSIENT do MINIMOS).

Formas de onda por contato (manual do MINIMOS 6, seção 1.4), chave Wi:

* Wi=1 — tensão constante, a do BIAS (padrão);
* Wi=2 — trapézio periódico: Ti1 período, Ti2 descida, Ti3 patamar de baixo,
  Ti4 subida, Ti5 fim; Ui2 amplitude (negativa espelha), Ui3/Ui4 incrementos
  de tensão que fixam o passo de tempo na descida/subida;
* Wi=3 — três níveis: Ti1 período, Ti2 primeira descida, Ti3 nível do meio,
  Ti4 segunda descida, Ti5 subida, Ti6 patamar de cima, Ti7 fim; Ui2
  amplitude, Ui3 nível do meio, Ui4/Ui5/Ui6 incrementos das três rampas.

Sem forma de onda em contato algum: TG1 é o primeiro passo, TG2 o segundo, os
seguintes crescem na razão TG2/TG1 até TG3.

Passos de tempo medidos no .tra do MINIMOS: nas rampas, Δt = T_rampa·ΔU/|A|;
nos patamares, o passo começa no da rampa anterior e cresce 1,5× até o fim.

Equações: o modelo de dois portadores (bipolar.py) com Euler implícito. A
corrente de cada terminal é condução (elétrons + lacunas) mais deslocamento,
a derivada da carga induzida no contato.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .deck import Deck, ErroDeck

CRESCIMENTO = 1.5


@dataclass
class Onda:
    """Tensão de um contato no tempo: segmentos (t0, t1, u0, u1, passo)."""
    u0: float
    segmentos: list = field(default_factory=list)
    periodo: float | None = None
    fim: float = 0.0

    def tensao(self, t: float) -> float:
        if not self.segmentos:
            return self.u0
        tt = t
        if self.periodo:
            tt = math.fmod(t, self.periodo)
            if tt < 0:
                tt += self.periodo
        for t0, t1, a, b, _ in self.segmentos:
            if t0 - 1e-18 <= tt <= t1 + 1e-18:
                if t1 <= t0:
                    return b
                return a + (b - a) * (tt - t0) / (t1 - t0)
        return self.segmentos[-1][3]


def _num(tr, chave, obrig=True):
    v = tr.num(chave)
    if v is None and obrig:
        raise ErroDeck(f"*TRANSIENT* falta a chave {chave}")
    return v


def ondas(deck: Deck, U0: dict[str, float]) -> tuple[dict[str, Onda], float, list[float] | None]:
    """Formas de onda dos quatro contatos, tempo final e passos livres (sem ondas)."""
    tr = deck.uma("TRANSIENT")
    out: dict[str, Onda] = {}
    fins = []
    for c in "SGDB":
        w = int(tr.num(f"W{c}", 1) or 1)
        u1 = tr.num(f"U{c}1", U0[c])
        o = Onda(u0=u1)
        if w == 2:
            T = [_num(tr, f"T{c}{k}") for k in range(1, 6)]
            A = _num(tr, f"U{c}2")
            inc_desce = abs(_num(tr, f"U{c}3", False) or abs(A) / 10)
            inc_sobe = abs(_num(tr, f"U{c}4", False) or abs(A) / 10)
            per, td, tl, ts, fim = T
            baixo = u1 - A
            t = 0.0
            seg = [(t, t + td, u1, baixo, td * inc_desce / abs(A))]
            t += td
            seg.append((t, t + tl, baixo, baixo, None))
            t += tl
            seg.append((t, t + ts, baixo, u1, ts * inc_sobe / abs(A)))
            t += ts
            seg.append((t, per, u1, u1, None))
            o.segmentos, o.periodo, o.fim = seg, per, fim
            fins.append(fim)
        elif w == 3:
            T = [_num(tr, f"T{c}{k}") for k in range(1, 8)]
            A = _num(tr, f"U{c}2")
            meio = _num(tr, f"U{c}3")
            incs = [abs(_num(tr, f"U{c}{k}", False) or abs(A) / 10) for k in (4, 5, 6)]
            per, t1, tm, t2, ts, tc, fim = T
            baixo = u1 - A
            t = 0.0
            seg = [(t, t + t1, u1, meio, t1 * incs[0] / max(abs(u1 - meio), 1e-12))]
            t += t1
            seg.append((t, t + tm, meio, meio, None))
            t += tm
            seg.append((t, t + t2, meio, baixo, t2 * incs[1] / max(abs(meio - baixo), 1e-12)))
            t += t2
            tb = per - (t1 + tm + t2 + ts + tc)
            if tb < -1e-15:
                raise ErroDeck(f"*TRANSIENT* as durações de {c} passam do período T{c}1")
            seg.append((t, t + tb, baixo, baixo, None))
            t += tb
            seg.append((t, t + ts, baixo, u1, ts * incs[2] / abs(A)))
            t += ts
            seg.append((t, per, u1, u1, None))
            o.segmentos, o.periodo, o.fim = seg, per, fim
            fins.append(fim)
        elif w != 1:
            raise ErroDeck(f"*TRANSIENT* W{c}={w}: as formas de onda são 1, 2 ou 3")
        out[c] = o
    livres = None
    if not fins:
        # passos livres: TG1, TG2, depois na razão TG2/TG1 até TG3
        a, b, fim = (_num(tr, "TG1"), _num(tr, "TG2"), _num(tr, "TG3"))
        passos, t, h = [a], a, b
        while t + h < fim * (1 - 1e-12):
            t += h
            passos.append(t)
            h *= b / a
        passos.append(fim)
        return out, fim, passos
    fim = max(fins)
    if any(abs(f - fim) > 1e-12 * fim for f in fins):
        raise ErroDeck("*TRANSIENT* o tempo final tem de ser o mesmo em todas as ondas")
    return out, fim, livres


def instantes(o: dict[str, Onda], fim: float) -> list[float]:
    """Instantes de cálculo: rampas em passos fixos, patamares crescendo 1,5×."""
    marcos = set()
    rampas = []          # (t0, t1, passo) absolutos
    for onda in o.values():
        if not onda.segmentos:
            continue
        k = 0
        while k * onda.periodo < fim:
            base = k * onda.periodo
            for t0, t1, a, b, passo in onda.segmentos:
                marcos.add(base + t0)
                marcos.add(base + t1)
                if passo:
                    rampas.append((base + t0, base + t1, passo))
            k += 1
    marcos = sorted(m for m in marcos if 0 <= m <= fim * (1 + 1e-12))
    marcos = sorted(set(marcos + [fim]))
    ts = [0.0]
    passo = None
    for t0, t1 in zip(marcos[:-1], marcos[1:]):
        if t1 - t0 <= 1e-18:
            continue
        r = [rp for rp in rampas if rp[0] <= t0 + 1e-18 and rp[1] >= t1 - 1e-18]
        if r:
            h = min(rp[2] for rp in r)
            n = max(1, int(round((t1 - t0) / h)))
            ts += [t0 + (t1 - t0) * k / n for k in range(1, n + 1)]
            passo = (t1 - t0) / n
        else:
            # patamar: começa no passo da rampa anterior e cresce 1,5× (o .tra do
            # MINIMOS no extra.inp: 1,1 → 1,25 → 1,475 → 1,8125 → 2,0 µs)
            h = passo or (t1 - t0) / 10
            t = t0
            while t + h < t1 * (1 - 1e-9):
                t += h
                ts.append(t)
                h *= CRESCIMENTO
            ts.append(t1)
    out = [ts[0]]
    for t in ts[1:]:
        if t - out[-1] > 1e-18 and t <= fim * (1 + 1e-9):
            out.append(t)
    return out


def simular(m, deck: Deck, U0: dict[str, float], log=None):
    """Roda o transiente a partir do regime permanente em U0.

    Devolve a lista de registros por instante: t, U (por contato) e correntes
    (por contato e por tipo: ele, hol, dis).
    """
    from . import simular as sim
    from .bipolar import Bipolar, Estado2, ParamGR
    from . import fisica
    s = m.sinal
    est2d, e2, corr = sim.resolver_aval(m, U0, log=log)
    bip: Bipolar = m.est["bipolar"][0]
    o, fim, livres = ondas(deck, U0)
    ts = livres if livres is not None else instantes(o, fim)
    if ts[0] != 0.0:
        ts = [0.0] + ts
    W = m.W
    regs = []
    q_ant = bip.cargas(e2, W)
    cond = bip.conducao(e2, W)
    regs.append({"t": 0.0, "U": dict(U0), "ele": {k: s * v[0] for k, v in cond.items()},
                 "hol": {k: s * v[1] for k, v in cond.items()}, "dis": {k: 0.0 for k in "SGDB"}})
    atual = e2
    for k in range(1, len(ts)):
        t, dt = ts[k], ts[k] - ts[k - 1]
        U = {c: o[c].tensao(t) for c in "SGDB"}
        alvo = {c: s * v for c, v in U.items()}
        # chute: o estado anterior (a malha é a do regime permanente)
        novo = bip.resolver(alvo, Estado2(atual.psi.copy(), atual.n.copy(), atual.p.copy(),
                                          atual.mu_n, atual.mu_p, atual.G),
                            impacto=True, ciclos=6, dt=dt, anterior=atual)
        q = bip.cargas(novo, W)
        cond = bip.conducao(novo, W, dt, atual)
        reg = {"t": t, "U": U,
               "ele": {c: s * cond[c][0] for c in "SGDB"},
               "hol": {c: s * cond[c][1] for c in "SGDB"},
               "dis": {c: s * (q[c] - q_ant[c]) / dt for c in "SGDB"}}
        regs.append(reg)
        if log:
            tot = {c: reg["ele"][c] + reg["hol"][c] + reg["dis"][c] for c in "SGDB"}
            log(f"  t={t:.4e}  UG={U['G']:6.3f}  ID={tot['D']:.3e}  IG={tot['G']:.3e}")
        q_ant = q
        atual = novo
    return regs


def tra(regs) -> str:
    """Arquivo .tra no formato do MINIMOS (unidade NUMTRA)."""
    linhas = ["        T (S)  UB (V)      IB (A)  UD (V)      ID (A)  UG (A)      IG (A)  US (V)      IS (A)"]

    def f(v):
        # 0.370E-16: mantissa < 1, como o Fortran imprime
        if v == 0:
            return "  0.000E+00"
        e = int(math.floor(math.log10(abs(v)))) + 1
        man = v / 10 ** e
        if abs(man) >= 0.9995:
            man /= 10
            e += 1
        return f"{man:7.3f}E{e:+03d}".replace("0.", "0.", 1).rjust(11)

    for r in regs:
        tot = {c: r["ele"][c] + r["hol"][c] + r["dis"][c] for c in "SGDB"}
        linhas.append(f"  {r['t']:.5E} {r['U']['B']:7.3f} {f(tot['B'])} {r['U']['D']:7.3f} {f(tot['D'])} "
                      f"{r['U']['G']:7.3f} {f(tot['G'])} {r['U']['S']:7.3f} {f(tot['S'])}")
    return "\n".join(linhas) + "\n"
