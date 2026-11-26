"""Modelo de dois portadores do MOSIM (o MODEL=AVAL do MINIMOS).

Resolve, no mesmo Dispositivo (malha e discretização do modelo 2-D):

* Poisson no domínio todo;
* continuidade dos elétrons e das lacunas, por Scharfetter–Gummel;
* recombinação SRH (2.27), Auger (2.28) e de superfície na interface
  porta-silício (2.29), com os parâmetros da diretiva RECOMBINATION;
* geração por ionização por impacto (2.31–2.34) com o fator de profundidade
  do MINIMOS 6, atualizada em subciclo (como o "avalanche subcycle" do
  manual: a geração só entra depois que o resto convergiu).

Convenção do Dispositivo: para o canal P o problema é espelhado, e ``n`` é o
portador do canal (lacunas físicas). Os parâmetros de cada equação são
escolhidos pelo tipo físico do portador.

Medido contra o MINIMOS (mapas de geração do exavl, na malha dele): sem o
fator de profundidade a geração sai 14× maior; com ele e os padrões do
manual, a geração total bate dentro da precisão do gradiente nodal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import fisica
from .solver import Dispositivo, Estado, bern, dbern

DEPURAR = False


@dataclass
class ParamGR:
    """Diretiva RECOMBINATION (unidades CGS, como no deck)."""
    tn: float = 1e-6
    tp: float = 1e-6
    cn: float = 2.8e-31
    cp: float = 9.9e-32
    sn: float = 100.0
    sp: float = 100.0
    an: float = 9.20e5
    ap: float = 1.70e7
    bn: float = 2.02e6
    bp: float = 3.20e6
    dn: float = 1.5e-6
    dp: float = 1.5e-6
    en: float = 1.0
    ep: float = 1.0
    fn: float = 2.2
    fp: float = 2.2

    @classmethod
    def do_deck(cls, deck) -> "ParamGR":
        r = deck.uma("RECOMBINATION")
        p = cls()
        for k in ("TN", "TP", "CN", "CP", "SN", "SP", "AN", "AP", "BN", "BP", "DN", "DP",
                  "EN", "EP", "FN", "FP"):
            v = r.num(k)
            if v is not None:
                setattr(p, k.lower(), v)
        return p

    def por_portador(self, fisico: str) -> dict:
        """Parâmetros do portador físico 'n' ou 'p'."""
        if fisico == "n":
            return dict(t=self.tn, c=self.cn, s=self.sn, a=self.an, b=self.bn, d=self.dn,
                        e=self.en, f=self.fn)
        return dict(t=self.tp, c=self.cp, s=self.sp, a=self.ap, b=self.bp, d=self.dp,
                    e=self.ep, f=self.fp)


@dataclass
class Estado2:
    psi: np.ndarray
    n: np.ndarray
    p: np.ndarray
    mu_n: np.ndarray | None = None
    mu_p: np.ndarray | None = None
    G: np.ndarray | None = None        # geração por impacto (escalonada por n_i), por nó


class Bipolar:
    """Equações de dois portadores sobre um Dispositivo já montado."""

    def __init__(self, d: Dispositivo, gr: ParamGR, canal_n: bool,
                 mob_maj: fisica.Mobilidade):
        self.d = d
        self.gr = gr
        self.fis_n = "n" if canal_n else "p"      # tipo físico do portador "n"
        self.fis_p = "p" if canal_n else "n"
        self.pn = gr.por_portador(self.fis_n)
        self.pp = gr.por_portador(self.fis_p)
        self.mob_maj = mob_maj
        g = d.geo
        # nós da interface porta-silício (recombinação de superfície), área por nó
        idx = np.arange(d.N).reshape(d.ny, d.nx)
        x = g.x
        hx = np.diff(x)
        wx = np.zeros(d.nx)
        wx[:-1] += hx / 2
        wx[1:] += hx / 2
        sob = (x > g.x_fonte + 1e-12) & (x < g.x_dreno - 1e-12)
        self.A_sup = np.zeros(d.N)
        self.A_sup[idx[d.j0, :]] = np.where(sob, wx, 0.0)
        self.profund = np.maximum(d.Y, 0.0)          # cm, abaixo da interface
        self.livre_c = np.where((d.tipo == 0) & d.si)[0]

    # ── mobilidade dos majoritários ──────────────────────────────────────
    def mobilidade_maj(self, est: Estado2) -> np.ndarray:
        """Como a do Dispositivo, mas com a força normal que atrai o outro portador."""
        d = self.d
        mob = self.mob_maj
        vt = d.vt
        ny, nx, j0 = d.ny, d.nx, d.j0
        y = d.geo.y
        psi = (est.psi * vt).reshape(ny, nx)[j0:]
        ys = y[j0:]
        hy = np.diff(ys)
        e_int = (np.diff(psi, axis=0)) / hy[:, None]       # sinal oposto: atrai lacunas
        ev = np.empty_like(psi)
        ev[1:-1] = 0.5 * (e_int[:-1] + e_int[1:])
        ev[0], ev[-1] = e_int[0], e_int[-1]
        ci = d.CI.reshape(ny, nx)[j0:]
        mu_li = mob.impurezas(ci)
        Y = np.broadcast_to(np.maximum(ys, 0.0)[:, None], psi.shape)
        mu = np.minimum(mob.superficie(mu_li, Y, np.maximum(ev, 0.0)), mu_li)
        p = est.p.reshape(ny, nx)[j0:]
        phip = (psi / vt + np.log(np.maximum(p, 1e-300))) * vt
        fx = d._grad_no(phip, 1)
        fy = np.zeros_like(phip)
        dd = np.abs(np.diff(phip, axis=0)) / hy[:, None]
        fy[1:-1] = 0.5 * (dd[:-1] + dd[1:])
        fy[0], fy[-1] = dd[0], dd[-1]
        mu = mob.campo(mu, np.hypot(fx, fy))
        out = np.zeros((ny, nx))
        out[j0:] = mu
        m = out.ravel()
        a, b = m[d.ea], m[d.eb]
        a = np.where(a > 0, a, b)
        b = np.where(b > 0, b, a)
        a = np.where(a > 0, a, 1.0)
        b = np.where(b > 0, b, 1.0)
        return 0.5 * (a + b)

    # ── geração–recombinação (escalonadas por n_i) ───────────────────────
    def recombinacao(self, n, p):
        """R e suas derivadas (por volume), escalonadas: R_real = n_i·R."""
        d = self.d
        ni = d.ni
        tn, tp = self.pn["t"], self.pp["t"]
        den = tp * (n + 1.0) + tn * (p + 1.0)
        np1 = n * p - 1.0
        R = np1 / den
        dRn = p / den - np1 * tp / den ** 2
        dRp = n / den - np1 * tn / den ** 2
        cn, cp = self.pn["c"], self.pp["c"]
        aug = ni * ni * (cn * n + cp * p)
        R = R + aug * np1
        dRn = dRn + aug * p + ni * ni * cn * np1
        dRp = dRp + aug * n + ni * ni * cp * np1
        si = d.si
        return np.where(si, R, 0.0), np.where(si, dRn, 0.0), np.where(si, dRp, 0.0)

    def recomb_superficie(self, n, p):
        """R_s (por área, escalonada) e derivadas, na interface porta-silício."""
        sn, sp_ = self.pn["s"], self.pp["s"]
        if sn <= 0 or sp_ <= 0:
            z = np.zeros_like(n)
            return z, z, z
        den = (n + 1.0) / sp_ + (p + 1.0) / sn
        np1 = n * p - 1.0
        R = np1 / den
        dRn = p / den - np1 / (sp_ * den ** 2)
        dRp = n / den - np1 / (sn * den ** 2)
        m = self.A_sup > 0
        return np.where(m, R, 0.0), np.where(m, dRn, 0.0), np.where(m, dRp, 0.0)

    def geracao_impacto(self, est: Estado2) -> np.ndarray:
        """Geração por ionização por impacto por nó (cm⁻³/s), escalonada por n_i.

        α = A·exp(−(B·β(y)/E∥)^E), β(y) = 1 + F·exp(−y/D) — eqs. (2.31)–(2.34);
        G = α_n|J_n|/q + α_p|J_p|/q, com E∥ o campo na direção da corrente.
        """
        d = self.d
        vt = d.vt
        psi = est.psi
        cur = d.ecur
        a, b = d.ea[cur], d.eb[cur]
        h = d.eh[cur]
        dd = psi[b] - psi[a]
        E_e = -dd * vt / h                                     # campo ao longo da aresta (a→b)
        jn_e = (est.mu_n[cur] * vt / h) * (est.n[b] * bern(dd) - est.n[a] * bern(-dd))
        jp_e = (est.mu_p[cur] * vt / h) * (est.p[a] * bern(dd) - est.p[b] * bern(-dd))
        horiz = d.e_horiz[cur]
        N = d.N

        def nodal(v):
            sx = np.zeros(N); cx = np.zeros(N)
            sy = np.zeros(N); cy = np.zeros(N)
            for s_, c_, mask in ((sx, cx, horiz), (sy, cy, ~horiz)):
                np.add.at(s_, a[mask], v[mask]); np.add.at(c_, a[mask], 1)
                np.add.at(s_, b[mask], v[mask]); np.add.at(c_, b[mask], 1)
            return sx / np.maximum(cx, 1), sy / np.maximum(cy, 1)

        Ex, Ey = nodal(E_e)
        Jnx, Jny = nodal(jn_e)       # partículas·cm⁻²·s⁻¹ / n_i (escalonado)
        Jpx, Jpy = nodal(jp_e)
        G = np.zeros(N)
        y = self.profund
        for (Jx, Jy), prm in (((Jnx, Jny), self.pn), ((Jpx, Jpy), self.pp)):
            J = np.hypot(Jx, Jy)
            Ep = np.abs(Ex * Jx + Ey * Jy) / np.maximum(J, 1e-300)
            beta = 1.0 + prm["f"] * np.exp(-y / prm["d"]) if prm["d"] > 0 else 1.0
            with np.errstate(over="ignore", divide="ignore"):
                alfa = prm["a"] * np.exp(-((prm["b"] * beta / np.maximum(Ep, 1.0)) ** prm["e"]))
            G += alfa * J
        return np.where(d.si, G, 0.0)

    # ── sistema completo ────────────────────────────────────────────────
    def sistema(self, psi, n, p, mu_n, mu_p, G):
        d = self.d
        N = d.N
        ea, eb, eh = d.ea, d.eb, d.eh
        cpe = d.lam * d.eAeps / eh
        dpsi = psi[eb] - psi[ea]
        F = np.zeros(N)
        np.add.at(F, ea, cpe * dpsi)
        np.add.at(F, eb, -cpe * dpsi)
        F += d.Vsi * (p - n + d.Cs) + d.sig / d.ni
        cur = d.ecur
        a, b = ea[cur], eb[cur]
        dd = psi[b] - psi[a]
        Bp, Bm = bern(dd), bern(-dd)
        dBp, dBm = dbern(dd), dbern(-dd)
        cn = mu_n[cur] * d.vt * d.eAsi[cur] / eh[cur]
        cp_ = mu_p[cur] * d.vt * d.eAsi[cur] / eh[cur]
        fn = cn * (n[b] * Bp - n[a] * Bm)          # elétrons entrando em a
        fp = cp_ * (p[b] * Bm - p[a] * Bp)         # lacunas entrando em a
        R, dRn, dRp = self.recombinacao(n, p)
        Rs, dRsn, dRsp = self.recomb_superficie(n, p)
        U = d.Vsi * R + self.A_sup * Rs - d.Vsi * G
        Gn = np.zeros(N); Gp = np.zeros(N)
        np.add.at(Gn, a, fn); np.add.at(Gn, b, -fn)
        np.add.at(Gp, a, fp); np.add.at(Gp, b, -fp)
        Gn -= U
        Gp -= U
        dUn = d.Vsi * dRn + self.A_sup * dRsn
        dUp = d.Vsi * dRp + self.A_sup * dRsp
        I = np.arange(N)
        r, c, v = [], [], []
        # Poisson
        r += [ea, ea, eb, eb]; c += [ea, eb, eb, ea]; v += [-cpe, cpe, -cpe, cpe]
        r += [I, I, I]; c += [N + I, 2 * N + I, I]; v += [-d.Vsi, d.Vsi, 0 * d.Vsi]
        # elétrons
        r += [N + a, N + a, N + b, N + b]; c += [N + b, N + a, N + a, N + b]
        v += [cn * Bp, -cn * Bm, cn * Bm, -cn * Bp]
        t = cn * (n[b] * dBp + n[a] * dBm)
        r += [N + a, N + a, N + b, N + b]; c += [a, b, b, a]; v += [-t, t, -t, t]
        r += [N + I, N + I]; c += [N + I, 2 * N + I]; v += [-dUn, -dUp]
        # lacunas
        r += [2 * N + a, 2 * N + a, 2 * N + b, 2 * N + b]
        c += [2 * N + b, 2 * N + a, 2 * N + a, 2 * N + b]
        v += [cp_ * Bm, -cp_ * Bp, cp_ * Bp, -cp_ * Bm]
        t = cp_ * (-p[b] * dBm - p[a] * dBp)
        r += [2 * N + a, 2 * N + a, 2 * N + b, 2 * N + b]; c += [a, b, b, a]; v += [-t, t, -t, t]
        r += [2 * N + I, 2 * N + I]; c += [N + I, 2 * N + I]; v += [-dUn, -dUp]
        J = sp.csr_matrix((np.concatenate(v), (np.concatenate(r), np.concatenate(c))),
                          shape=(3 * N, 3 * N))
        return F, Gn, Gp, J

    def contorno(self, U):
        d = self.d
        psi_c, n_c = d.contorno(U)
        p_c = np.where(n_c > 0, 1.0 / np.maximum(n_c, 1e-300), 0.0)
        return psi_c, n_c, p_c

    def de_estado(self, est: Estado, U) -> Estado2:
        """Estado de dois portadores a partir do modelo 2-D (lacunas de Boltzmann)."""
        d = self.d
        phip = U["B"] / d.vt
        p = np.where(d.si, np.exp(np.clip(phip - est.psi, -700, 700)), 0.0)
        return Estado2(est.psi.copy(), est.n.copy(), p, est.mu_x)

    def resolver(self, U, e: Estado2, tol=1e-9, maxit=200, log=None, impacto=True,
                 ciclos=40) -> Estado2:
        """Newton acoplado em (ψ, n, p); mobilidades e geração por impacto em subciclo."""
        d = self.d
        N = d.N
        psi_c, n_c, p_c = self.contorno(U)
        fixo = d.tipo != 0
        psi, n, p = e.psi.copy(), e.n.copy(), e.p.copy()
        psi[fixo], n[fixo], p[fixo] = psi_c[fixo], n_c[fixo], p_c[fixo]
        n[~d.si] = 0.0
        p[~d.si] = 0.0
        livre = np.concatenate([d.livre_psi, N + self.livre_c, 2 * N + self.livre_c])
        nl = len(d.livre_psi)
        nc = len(self.livre_c)
        mu_n = e.mu_n if e.mu_n is not None else d.mobilidade(Estado(psi, n), campo=True)
        est = Estado2(psi, n, p, mu_n, None, np.zeros(N) if e.G is None else e.G)
        est.mu_p = e.mu_p if e.mu_p is not None else self.mobilidade_maj(est)
        G = est.G if impacto else np.zeros(N)
        ib_ant = None
        for ciclo in range(ciclos):
            for it in range(maxit):
                F, Gn, Gp, J = self.sistema(psi, n, p, est.mu_n, est.mu_p, G)
                R = np.concatenate([F, Gn, Gp])[livre]
                A = J[livre][:, livre].tocsc()
                # escala das linhas e colunas de n e p pela concentração (condicionamento)
                sc = np.concatenate([np.ones(nl), np.maximum(n[self.livre_c], 1e-30),
                                     np.maximum(p[self.livre_c], 1e-30)])
                A = A @ sp.diags(sc)
                dx = spla.spsolve(A.tocsc(), -R) * sc
                dpsi = dx[:nl]
                mx = np.max(np.abs(dpsi)) if nl else 0.0
                fator = 1.0 if mx <= 1.0 else 1.0 / mx
                dn = dx[nl:nl + nc]
                dp = dx[nl + nc:]
                cn_ = n[self.livre_c]
                cp_ = p[self.livre_c]
                # limite por nó: cada concentração muda no máximo 10× por passo. Um
                # limite global travaria o passo inteiro por causa de um único nó
                # quase vazio (lacunas a 1e-17·nᵢ pedem mudanças relativas de 1e17).
                razn = 1.0 + fator * dn / np.maximum(cn_, 1e-300)
                razp = 1.0 + fator * dp / np.maximum(cp_, 1e-300)
                lim = max(np.max(np.abs(razn - 1.0)) if nc else 0.0,
                          np.max(np.abs(razp - 1.0)) if nc else 0.0)
                psi[d.livre_psi] += fator * dpsi
                n[self.livre_c] = cn_ * np.clip(razn, 0.1, 10.0)
                p[self.livre_c] = cp_ * np.clip(razp, 0.1, 10.0)
                if log and DEPURAR:
                    log(f"      newton {it}: |dψ|={mx:.2e} lim={lim:.2e} fator={fator:.2e} "
                        f"|R|={np.abs(R).max():.2e}")
                if mx < tol and lim < 1e-8 and fator == 1.0:
                    break
                if fator == 1.0 and mx < 1e-3 and it % 3 == 2:
                    est.mu_n = d.mobilidade(Estado(psi, n), campo=True)
                    est.mu_p = self.mobilidade_maj(Estado2(psi, n, p))
            est = Estado2(psi, n, p, d.mobilidade(Estado(psi, n), campo=True), None, G)
            est.mu_p = self.mobilidade_maj(est)
            if not impacto:
                break
            G_novo = self.geracao_impacto(est)
            ib = float(np.sum(d.Vsi * G_novo))
            if log:
                log(f"    avalanche {ciclo}: ∫G = {ib * d.ni * fisica.Q:.4e} A/cm")
            if ib_ant is not None and abs(ib - ib_ant) <= 1e-4 * max(abs(ib), 1e-300):
                G = G_novo
                break
            # subrelaxação: a geração muda o campo que a produz
            G = G_novo if ib_ant is None else 0.5 * (G + G_novo)
            ib_ant = ib
        est.G = G
        return est

    # ── correntes ───────────────────────────────────────────────────────
    def correntes(self, est: Estado2, W: float) -> dict:
        """Correntes de terminal (A, convencionais, entrando no dispositivo)."""
        d = self.d
        Q = fisica.Q * d.ni
        cur = d.ecur
        a, b = d.ea[cur], d.eb[cur]
        dd = est.psi[b] - est.psi[a]
        cn = est.mu_n[cur] * d.vt * d.eAsi[cur] / d.eh[cur]
        cp_ = est.mu_p[cur] * d.vt * d.eAsi[cur] / d.eh[cur]
        fn = cn * (est.n[b] * bern(dd) - est.n[a] * bern(-dd))    # elétrons b→a
        fp = cp_ * (est.p[b] * bern(-dd) - est.p[a] * bern(dd))   # lacunas b→a

        def no_contato(t):
            ta, tb = d.tipo[a] == t, d.tipo[b] == t
            # corrente convencional entrando pelo contato: elétrons saindo dele para dentro
            # (fluxo de a=contato para b) e lacunas entrando no dispositivo
            e_in = -np.sum(fn[ta & ~tb]) + np.sum(fn[tb & ~ta])   # elétrons contato→dentro
            h_in = -np.sum(fp[ta & ~tb]) + np.sum(fp[tb & ~ta])
            return Q * (-e_in + h_in) * W

        # o contato n+ do canal tem fluxos enormes que se cancelam: para fonte e
        # dreno usa-se a corrente no meio do canal mais a geração líquida de cada lado
        R, _, _ = self.recombinacao(est.n, est.p)
        Rs, _, _ = self.recomb_superficie(est.n, est.p)
        liq = (d.Vsi * (est.G - R) - self.A_sup * Rs)
        xm = 0.5 * d.geo.L
        canal = d.corrente_canal(est.psi, est.n, est.mu_n) * W
        lado_d = Q * np.sum(liq[d.X >= xm]) * W
        lado_s = Q * np.sum(liq[d.X < xm]) * W
        ib = no_contato(4)
        idr = canal + lado_d
        return {"D": idr, "S": -(canal - lado_s) - 0.0, "B": ib, "G": 0.0,
                "canal": canal, "gerada": Q * np.sum(liq) * W}
