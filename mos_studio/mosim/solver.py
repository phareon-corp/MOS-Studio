"""Solução 2-D das equações do semicondutor numa malha tensorial (método das caixas).

Modelo "2-D" do MINIMOS para MOSFET: equação de Poisson no domínio todo
(silício + isolante de porta) e equação de continuidade dos elétrons
(minoritários do canal N) no silício, discretizada por Scharfetter–Gummel;
os majoritários (lacunas) seguem Boltzmann com nível de quase-Fermi constante
igual ao potencial do substrato; sem geração–recombinação.

Variáveis escalonadas: ψ̃ = ψ/V_T (ψ = potencial intrínseco), ñ = n/n_i.
Para o canal P o problema é resolvido com as polaridades espelhadas (mesmas
equações para lacunas como "minoritários"): o chamador inverte os sinais de
dopagem, tensões e função trabalho.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from . import fisica


def bern(x):
    """B(x) = x / (e^x − 1), estável."""
    x = np.asarray(x, dtype=float)
    out = np.empty_like(x)
    small = np.abs(x) < 1e-6
    out[small] = 1.0 - x[small] / 2.0
    big = ~small
    xb = x[big]
    with np.errstate(over="ignore"):
        out[big] = np.where(xb > 0, xb * np.exp(-xb) / (1.0 - np.exp(-xb)),
                            xb / np.expm1(xb))
    return out


def dbern(x):
    """B'(x)."""
    x = np.asarray(x, dtype=float)
    out = np.empty_like(x)
    small = np.abs(x) < 1e-4
    out[small] = -0.5 + x[small] / 6.0
    xb = x[~small]
    b = bern(xb)
    # B'(x) = (1 − B(x)·(1 + ... ))  ->  B'(x) = B(x)/x − B(x)·(B(x) + x)/x
    out[~small] = b / xb - b * (b + xb) / xb
    return out


@dataclass
class Geometria:
    x: np.ndarray            # cm, linhas verticais
    y: np.ndarray            # cm, linhas horizontais (y<0 isolante, y>=0 silício)
    L: float                 # cm
    tox: float               # cm
    eps_ins: float
    x_fonte: float           # cm: contato de fonte em y=0 para x <= x_fonte
    x_dreno: float           # cm: contato de dreno em y=0 para x >= x_dreno
    y_filme: float | None = None   # cm: SOI — o silício vai de 0 a y_filme; abaixo, isolante
    eps_box: float = 3.9           # permissividade do isolante enterrado (KBULK)


@dataclass
class Estado:
    psi: np.ndarray           # ψ̃ em todos os nós
    n: np.ndarray             # ñ em todos os nós (0 no isolante)
    mu_x: np.ndarray | None = None
    mu_y: np.ndarray | None = None


@dataclass
class Dispositivo:
    geo: Geometria
    C: np.ndarray            # dopagem líquida (cm^-3) por nó
    CI: np.ndarray           # N_D + N_A por nó
    T: float = 300.0
    nss: float = 0.0         # carga fixa na interface (cm^-2)
    wf: float = -0.55        # função trabalho da porta em relação a n_i (V)
    mob: fisica.Mobilidade | None = None
    ni: float = 0.0
    vt: float = 0.0
    _pre: dict = field(default_factory=dict)

    def __post_init__(self):
        self.vt = fisica.tensao_termica(self.T)
        if not self.ni:
            self.ni = fisica.intrinseca(self.T)
        if self.mob is None:
            self.mob = fisica.Mobilidade(self.T, "n")
        self._montar()

    # ── estrutura ────────────────────────────────────────────────────────
    def _montar(self):
        g = self.geo
        x, y = g.x, g.y
        nx, ny = len(x), len(y)
        self.nx, self.ny, self.N = nx, ny, nx * ny
        hx, hy = np.diff(x), np.diff(y)
        X, Y = np.meshgrid(x, y)
        self.X, self.Y = X.ravel(), Y.ravel()
        idx = np.arange(self.N).reshape(ny, nx)
        # célula entre y[j] e y[j+1] é silício se está abaixo da interface (e, no
        # SOI, acima do isolante enterrado)
        si_row = y[:-1] >= -1e-14
        self.soi = g.y_filme is not None
        if self.soi:
            si_row &= y[1:] <= g.y_filme * (1 + 1e-9)
        eps_row = np.where(si_row, fisica.EPS_SI, np.where(y[:-1] < -1e-14, g.eps_ins, g.eps_box))
        # arestas horizontais (i,j)-(i+1,j)
        a_h = idx[:, :-1].ravel()
        b_h = idx[:, 1:].ravel()
        h_h = np.tile(hx, ny)
        up = np.zeros(ny); dn = np.zeros(ny)
        up_si = np.zeros(ny); dn_si = np.zeros(ny)
        for j in range(ny):
            if j > 0:
                up[j] = eps_row[j - 1] * hy[j - 1] / 2
                up_si[j] = hy[j - 1] / 2 if si_row[j - 1] else 0.0
            if j < ny - 1:
                dn[j] = eps_row[j] * hy[j] / 2
                dn_si[j] = hy[j] / 2 if si_row[j] else 0.0
        Aeps_h = np.repeat(up + dn, nx - 1)
        Asi_h = np.repeat(up_si + dn_si, nx - 1)
        # arestas verticais (i,j)-(i,j+1)
        a_v = idx[:-1, :].ravel()
        b_v = idx[1:, :].ravel()
        h_v = np.repeat(hy, nx)
        wx = np.zeros(nx)
        wx[:-1] += hx / 2
        wx[1:] += hx / 2
        Aeps_v = (eps_row[:, None] * wx[None, :]).ravel()
        Asi_v = (np.where(si_row, 1.0, 0.0)[:, None] * wx[None, :]).ravel()
        self.ea = np.concatenate([a_h, a_v])
        self.eb = np.concatenate([b_h, b_v])
        self.eh = np.concatenate([h_h, h_v])
        self.eAeps = np.concatenate([Aeps_h, Aeps_v])
        self.eAsi = np.concatenate([Asi_h, Asi_v])
        self.n_h = len(a_h)
        self.e_horiz = np.arange(len(self.ea)) < self.n_h
        # posição do ponto médio da aresta
        self.emx = 0.5 * (self.X[self.ea] + self.X[self.eb])
        self.emy = 0.5 * (self.Y[self.ea] + self.Y[self.eb])
        # volume de silício por nó
        wy_si = np.zeros(ny)
        for j in range(ny):
            if j > 0 and si_row[j - 1]:
                wy_si[j] += hy[j - 1] / 2
            if j < ny - 1 and si_row[j]:
                wy_si[j] += hy[j] / 2
        self.Vsi = (wy_si[:, None] * wx[None, :]).ravel()
        self.si = self.Vsi > 0
        # interface y=0
        j0 = int(np.argmin(np.abs(y)))
        self.j0 = j0
        self.no_interface = idx[j0, :]
        # carga de interface: só onde há isolante por cima (entre os contatos)
        xs = x
        sob_ins = (xs > g.x_fonte + 1e-12) & (xs < g.x_dreno - 1e-12)
        self.sig = np.zeros(self.N)
        self.sig[idx[j0, :]] = np.where(sob_ins, wx, 0.0) * self.nss
        # contatos
        tipo = np.zeros(self.N, dtype=int)   # 0 livre, 1 fonte, 2 dreno, 3 porta, 4 substrato
        tipo[idx[j0, xs <= g.x_fonte + 1e-12]] = 1
        tipo[idx[j0, xs >= g.x_dreno - 1e-12]] = 2
        jg = int(np.argmin(np.abs(y + g.tox)))
        porta = (xs >= -1e-12) & (xs <= g.L + 1e-12)
        tipo[idx[jg, porta]] = 3
        if not self.soi:
            tipo[idx[-1, :]] = 4          # no SOI o fundo do isolante é livre (sem eletrodo)
        self.tipo = tipo
        # quase-Fermi dos majoritários no modelo 2-D: o substrato; no SOI (corpo
        # flutuante, sem contato) a fonte
        self.ref_maj = "S" if self.soi else "B"
        self.jb = int(np.argmin(np.abs(y - g.y_filme))) if self.soi else None
        self.lam = fisica.EPS0 * self.vt / (fisica.Q * self.ni)
        self.Cs = self.C / self.ni
        # mapeamento das incógnitas
        self.livre_psi = np.where((tipo == 0))[0]
        self.livre_n = np.where((tipo == 0) & self.si)[0]
        # arestas de corrente (as duas pontas no silício e área de Si > 0)
        self.ecur = self.eAsi > 0

    # ── condições de contorno ───────────────────────────────────────────
    def contorno(self, U: dict[str, float]):
        """Valores de ψ̃ e ñ nos contatos para as tensões U (V)."""
        vt = self.vt
        psi = np.zeros(self.N)
        n = np.zeros(self.N)
        c = self.Cs
        neq = c / 2 + np.sqrt(c * c / 4 + 1.0)
        peq = 1.0 / neq
        for t, nome in ((1, "S"), (2, "D"), (4, "B")):
            m = self.tipo == t
            psi[m] = U[nome] / vt + np.log(neq[m])   # ψ = U + V_T ln(n/n_i)
            n[m] = neq[m]
        m = self.tipo == 3
        psi[m] = (U["G"] - self.wf) / vt
        return psi, n

    # ── mobilidade ───────────────────────────────────────────────────────
    media_aresta: str = "aritmetica"

    def _grad_no(self, f, eixo):
        """Gradiente nodal como média dos módulos das diferenças à frente e atrás."""
        h = np.diff(self.geo.x if eixo == 1 else self.geo.y)
        d = np.diff(f, axis=eixo)
        if eixo == 1:
            d = np.abs(d) / h[None, :]
            g = np.zeros_like(f)
            g[:, 1:-1] = 0.5 * (d[:, :-1] + d[:, 1:])
            g[:, 0], g[:, -1] = d[:, 0], d[:, -1]
        else:
            d = np.abs(d) / h[:, None]
            g = np.zeros_like(f)
            g[1:-1, :] = 0.5 * (d[:-1, :] + d[1:, :])
            g[0, :], g[-1, :] = d[0, :], d[-1, :]
        return g

    def mobilidade_nos(self, est: Estado, campo: bool = True) -> np.ndarray:
        """Mobilidade nodal no silício, como no MINIMOS 6.

        S (força normal) é o campo vertical local quando atrai os portadores
        (média dos campos dos dois intervalos vizinhos; na interface, só o do
        silício); μ^LIS nunca passa de μ^LI; a força motriz é |∇φ_n| com cada
        componente tomada como a média dos módulos das diferenças vizinhas.
        """
        mob = self.mob
        vt = self.vt
        ny, nx, j0 = self.ny, self.nx, self.j0
        y = self.geo.y
        psi = (est.psi * vt).reshape(ny, nx)[j0:]
        ys = y[j0:]
        hy = np.diff(ys)
        e_int = -(np.diff(psi, axis=0)) / hy[:, None]      # campo vertical nos intervalos
        ev = np.empty_like(psi)
        ev[1:-1] = 0.5 * (e_int[:-1] + e_int[1:])
        ev[0] = e_int[0]
        ev[-1] = e_int[-1]
        ci = self.CI.reshape(ny, nx)[j0:]
        mu_li = mob.impurezas(ci)
        Y = np.broadcast_to(np.maximum(ys, 0.0)[:, None], psi.shape)
        mu = np.minimum(mob.superficie(mu_li, Y, np.maximum(ev, 0.0)), mu_li)
        if campo:
            n = est.n.reshape(ny, nx)[j0:]
            phin = (psi / vt - np.log(np.maximum(n, 1e-300))) * vt
            fx = self._grad_no(phin, 1)
            fy = np.zeros_like(phin)
            d = np.abs(np.diff(phin, axis=0)) / hy[:, None]
            fy[1:-1] = 0.5 * (d[:-1] + d[1:])
            fy[0], fy[-1] = d[0], d[-1]
            mu = mob.campo(mu, np.hypot(fx, fy))
        out = np.zeros((ny, nx))
        out[j0:] = mu
        return out.ravel() * self.si

    def mobilidade(self, est: Estado, campo: bool = True) -> np.ndarray:
        """Mobilidade nas arestas a partir da nodal."""
        m = self.mobilidade_nos(est, campo)
        a, b = m[self.ea], m[self.eb]
        # arestas com uma ponta no isolante: usa a ponta do silício
        a = np.where(a > 0, a, b)
        b = np.where(b > 0, b, a)
        a = np.where(a > 0, a, 1.0)     # arestas só no isolante (sem corrente)
        b = np.where(b > 0, b, 1.0)
        if self.media_aresta == "harmonica":
            return 2 * a * b / np.maximum(a + b, 1e-300)
        if self.media_aresta == "geometrica":
            return np.sqrt(a * b)
        return 0.5 * (a + b)

    # ── resíduo e jacobiana ────────────────────────────────────────────
    def sistema(self, psi, n, mu, phip):
        N = self.N
        ea, eb, eh = self.ea, self.eb, self.eh
        # Poisson
        cpe = self.lam * self.eAeps / eh
        dpsi = psi[eb] - psi[ea]
        F = np.zeros(N)
        np.add.at(F, ea, cpe * dpsi)
        np.add.at(F, eb, -cpe * dpsi)
        p = np.where(self.si, np.exp(np.clip(phip - psi, -700, 700)), 0.0)
        F += self.Vsi * (p - n + self.Cs) + self.sig / self.ni
        # continuidade
        cur = self.ecur
        a, b = ea[cur], eb[cur]
        d = psi[b] - psi[a]
        ce = mu[cur] * self.vt * self.eAsi[cur] / eh[cur]
        Bp, Bm = bern(d), bern(-d)
        flux = ce * (n[b] * Bp - n[a] * Bm)           # fluxo de "entrada" em a
        G = np.zeros(N)
        np.add.at(G, a, flux)
        np.add.at(G, b, -flux)
        # jacobiana: blocos [Fψ Fn; Gψ Gn] com N incógnitas de ψ e N de n
        rows, cols, vals = [], [], []
        # Fψ
        rows += [ea, ea, eb, eb]
        cols += [ea, eb, eb, ea]
        vals += [-cpe, cpe, -cpe, cpe]
        rows.append(np.arange(N)); cols.append(np.arange(N)); vals.append(-self.Vsi * p)
        # Fn
        rows.append(np.arange(N)); cols.append(N + np.arange(N)); vals.append(-self.Vsi)
        # Gn
        rows += [N + a, N + a, N + b, N + b]
        cols += [N + b, N + a, N + a, N + b]
        vals += [ce * Bp, -ce * Bm, ce * Bm, -ce * Bp]
        # Gψ
        dB = n[b] * dbern(d) + n[a] * dbern(-d)
        t = ce * dB
        rows += [N + a, N + a, N + b, N + b]
        cols += [a, b, b, a]
        vals += [-t, t, -t, t]
        J = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(2 * N, 2 * N))
        return F, G, J

    def corrente(self, psi, n, mu, contato: int) -> float:
        """Corrente de elétrons (A/cm de largura) que entra no dispositivo pelo contato."""
        cur = self.ecur
        a, b = self.ea[cur], self.eb[cur]
        d = psi[b] - psi[a]
        ce = mu[cur] * self.vt * self.eAsi[cur] / self.eh[cur]
        flux = ce * (n[b] * bern(d) - n[a] * bern(-d))     # elétrons/… de b para a, escalonado
        ta, tb = self.tipo[a] == contato, self.tipo[b] == contato
        # corrente convencional = −q × fluxo de elétrons; fluxo b→a positivo
        tot = np.sum(flux[ta & ~tb]) - np.sum(flux[tb & ~ta])
        return fisica.Q * self.ni * tot

    def corrente_canal(self, psi, n, mu) -> float:
        """Corrente de elétrons (A/cm) atravessando o corte x = L/2, da fonte ao dreno.

        Em regime estacionário é a corrente de canal; medida onde n é pequeno,
        não sofre o cancelamento numérico dos fluxos enormes no contato n+.
        """
        x = self.geo.x
        i = int(np.searchsorted(x, 0.5 * self.geo.L)) - 1
        i = max(0, min(i, self.nx - 2))
        hmask = self.e_horiz & self.ecur & ((self.ea % self.nx) == i)
        a, b = self.ea[hmask], self.eb[hmask]
        d = psi[b] - psi[a]
        ce = mu[hmask] * self.vt * self.eAsi[hmask] / self.eh[hmask]
        flux = ce * (n[b] * bern(d) - n[a] * bern(-d))   # elétrons de b (dreno) para a (fonte)
        return -fisica.Q * self.ni * np.sum(flux)

    # ── Newton acoplado ────────────────────────────────────────────────
    def resolver(self, U: dict[str, float], est: Estado | None = None,
                 tol: float = 1e-6, maxit: int = 300, eletrons: bool = True,
                 campo: bool = True, tol_mu: float = 1e-5, tol_n: float = 1e-4,
                 phin_fixo: np.ndarray | None = None, log=None) -> Estado:
        """Newton acoplado (ψ, n) com a mobilidade reavaliada a cada iteração.

        A dependência da mobilidade com o campo fica fora da jacobiana (Newton
        inexato); a convergência exige passo pequeno e mobilidade estável.
        """
        vt = self.vt
        psi_c, n_c = self.contorno(U)
        phip = U[self.ref_maj] / vt
        if est is None:
            est = self.inicial(U)
        psi = est.psi.copy()
        n = est.n.copy()
        fixo = self.tipo != 0
        psi[fixo] = psi_c[fixo]
        n[fixo] = n_c[fixo]
        n[~self.si] = 0.0
        livre = np.concatenate([self.livre_psi, self.N + self.livre_n]) if eletrons \
            else self.livre_psi
        mu = est.mu_x if est.mu_x is not None else self.mobilidade(Estado(psi, n), campo=False)
        hist_mu: list[np.ndarray] = []
        hist_g: list[np.ndarray] = []
        convergiu = False
        for it in range(maxit):
            if not eletrons:
                ref = phin_fixo if phin_fixo is not None else U["S"] / vt
                n = np.where(self.si & ~fixo, np.exp(np.clip(psi - ref, -700, 700)), n)
            F, G, J = self.sistema(psi, n, mu, phip)
            if not eletrons:
                Jpp = J[:self.N, :self.N] - sp.diags(self.Vsi * np.where(self.si & ~fixo, n, 0.0))
                dx = spla.spsolve(Jpp[livre][:, livre].tocsc(), -F[livre])
                dpsi_l, dn_l = dx, None
            else:
                R = np.concatenate([F, G])
                dx = spla.spsolve(J[livre][:, livre].tocsc(), -R[livre])
                dpsi_l = dx[:len(self.livre_psi)]
                dn_l = dx[len(self.livre_psi):]
            mx = np.max(np.abs(dpsi_l)) if dpsi_l.size else 0.0
            fator = 1.0 if mx <= 2.0 else 2.0 / mx
            psi[self.livre_psi] += fator * dpsi_l
            rel_n = 0.0
            if dn_l is not None:
                nl = n[self.livre_n]
                novo = nl + fator * dn_l
                novo = np.where(novo < 1e-3 * nl, 1e-3 * nl, novo)
                n[self.livre_n] = novo
                rel_n = np.max(np.abs(novo - nl) / np.maximum(nl, 1e-300))
            dmu = 0.0
            if eletrons and campo and fator == 1.0 and mx < 0.5:
                mu_calc = self.mobilidade(Estado(psi, n), campo=True)
                g = mu_calc - mu
                dmu = np.max(np.abs(g) / mu)
                # aceleração de Anderson (memória curta) no ponto fixo da mobilidade
                hist_mu.append(mu.copy()); hist_g.append(g)
                if len(hist_mu) > 4:
                    hist_mu.pop(0); hist_g.pop(0)
                if len(hist_g) >= 2:
                    dG = np.array([hist_g[k + 1] - hist_g[k] for k in range(len(hist_g) - 1)]).T
                    dM = np.array([hist_mu[k + 1] - hist_mu[k] for k in range(len(hist_mu) - 1)]).T
                    w = 1.0 / mu
                    try:
                        gam, *_ = np.linalg.lstsq(dG * w[:, None], g * w, rcond=None)
                        mu_novo = mu + g - (dM + dG) @ gam
                    except np.linalg.LinAlgError:
                        mu_novo = mu + g
                    # salvaguarda: mobilidade positiva e dentro de [0.2, 5]× do valor calculado
                    mu_novo = np.clip(mu_novo, 0.2 * mu_calc, 5 * mu_calc)
                else:
                    mu_novo = mu + g
                mu = mu_novo
            elif eletrons and campo:
                mu = self.mobilidade(Estado(psi, n), campo=True)
                hist_mu.clear(); hist_g.clear()
                dmu = 1.0
            if log:
                log(f"    it {it:2d} |dψ|={mx:.2e} |dn/n|={rel_n:.2e} dμ={dmu:.1e}")
            if mx < tol and rel_n < tol_n and fator == 1.0 and dmu < tol_mu:
                convergiu = True
                break
        if not convergiu and log:
            log("    (não convergiu)")
        return Estado(psi, n, mu, None)

    def prever(self, est: Estado, U0: dict, U1: dict) -> Estado:
        """Chute para U1 a partir da solução em U0: desloca ψ nas regiões ligadas a
        cada contato e refaz Poisson com o quase-Fermi dos elétrons congelado."""
        vt = self.vt
        psi = est.psi.copy()
        n = est.n.copy()
        phin = psi - np.log(np.maximum(n, 1e-300))
        xm = 0.5 * self.geo.L
        tipo_n = self.si & (self.C > 0)
        tipo_p = self.si & (self.C <= 0)
        dS, dD, dB = ((U1[k] - U0[k]) / vt for k in ("S", "D", self.ref_maj))
        regs = [(tipo_n & (self.X >= xm), dD), (tipo_n & (self.X < xm), dS), (tipo_p, dB)]
        for m_, d in regs:
            psi[m_] += d
            phin[m_] += d
        # canal: quase-Fermi interpolado entre fonte e dreno ao longo de x
        canal = tipo_p & (self.X > 0) & (self.X < self.geo.L)
        t = np.clip(self.X[canal] / self.geo.L, 0, 1)
        phin[canal] += -dB + (1 - t) * dS + t * dD
        P = psi.reshape(self.ny, self.nx)
        y = self.geo.y
        j0 = self.j0
        pg = (U1["G"] - self.wf) / vt
        for j in range(j0):
            tt = (y[j] - y[j0]) / (y[0] - y[j0])
            P[j, :] = (1 - tt) * P[j0, :] + tt * pg
        e = Estado(P.ravel(), np.where(self.si, np.exp(np.clip(P.ravel() - phin, -700, 700)), 0.0),
                   est.mu_x)
        e = self.resolver(U1, e, eletrons=False, phin_fixo=phin, tol=1e-4)
        e.n = np.where(self.si, np.exp(np.clip(e.psi - phin, -700, 700)), 0.0)
        e.mu_x = est.mu_x
        return e

    def inicial(self, U) -> Estado:
        """Neutralidade de carga com o substrato no potencial de UB."""
        vt = self.vt
        c = self.Cs
        neq = c / 2 + np.sqrt(c * c / 4 + 1.0)
        psi = np.where(self.si, U[self.ref_maj] / vt + np.log(neq), 0.0)
        # isolante: interpola linearmente entre a porta e o silício (por coluna)
        ny, nx = self.ny, self.nx
        P = psi.reshape(ny, nx)
        y = self.geo.y
        j0 = self.j0
        pg = (U["G"] - self.wf) / vt
        for j in range(j0):
            t = (y[j] - y[j0]) / (y[0] - y[j0])
            P[j, :] = (1 - t) * P[j0, :] + t * pg
        n = np.where(self.si, neq * np.exp(-0.0), 0.0)
        return Estado(P.ravel(), n)
