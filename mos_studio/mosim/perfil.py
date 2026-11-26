"""Dopagem analítica a partir das diretivas PROFILE e IMPLANT.

Modelo (verificado contra a saída do MINIMOS 6.1):

* implantação: gaussiana de alcance Rp e desvio ΔRp; através de um óxido de
  espessura t o pico recua ``k·t`` e a parte que fica no óxido se perde (sem
  renormalizar a dose);
* recozimento: difusão com coeficiente intrínseco D(T) e superfície refletora,
  com solução exata para a gaussiana truncada em y ≥ 0; ``LD = sqrt(D·t)``;
* fonte e dreno: perfil vertical vezes ``½·erfc(Δx / (√2·σx))`` a partir da
  borda da máscara, com ``σx = √2·LD``;
* implante de canal: uniforme em x, através do isolante de porta.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.special import erf, erfc

from .deck import Deck, ErroDeck
from .fisica import K_EV

_DADOS = json.loads((Path(__file__).with_name("implante.json")).read_text())["elementos"]

DOADORES = {"AS", "P", "SB"}


def elemento(nome: str) -> str:
    n = nome.upper()
    if n.startswith("SB"):
        return "SB"
    if n.startswith("A"):
        return "AS"
    if n.startswith("B"):
        if n.startswith("BE"):
            raise ErroDeck("berílio só existe para GaAs")
        return "B"
    if n.startswith("P"):
        return "P"
    raise ErroDeck(f"elemento de implantação não suportado: {nome}")


def momentos(el: str, akev: float) -> tuple[float, float, float]:
    """(Rp, ΔRp, k_ox) em µm para o elemento e energia em keV."""
    d = _DADOS[el]
    if not d["emin"] <= akev <= d["emax"]:
        raise ErroDeck(f"energia fora da faixa para {el}: {akev} keV "
                       f"({d['emin']}–{d['emax']})")
    x = math.log(akev)
    rp = math.exp(np.polyval(d["ln_rp"], x))
    drp = math.exp(np.polyval(d["ln_drp"], x))
    k = float(np.polyval(d["k_ox"], x))
    return rp, drp, k


def difusividade(el: str, temp_c: float) -> float:
    d = _DADOS[el]
    return d["d0"] * math.exp(-d["ea"] / (K_EV * (temp_c + 273.15)))


def vertical(y_um, dose: float, rp: float, drp: float, ld: float):
    """Concentração (cm^-3) da gaussiana implantada e recozida, y em µm."""
    y = np.asarray(y_um, dtype=float)
    sd2 = 2.0 * ld * ld
    s2 = drp * drp + sd2
    s = math.sqrt(s2)
    pre = dose / (math.sqrt(2.0 * math.pi) * s * 1e-4)
    if sd2 < 1e-24:
        return np.where(y >= 0, pre * np.exp(-(y - rp) ** 2 / (2.0 * s2)), 0.0)
    sd = math.sqrt(sd2)
    den = math.sqrt(2.0) * drp * sd * s
    a1 = (rp * sd2 + y * drp * drp) / den
    a2 = (rp * sd2 - y * drp * drp) / den
    return pre * (np.exp(-(y - rp) ** 2 / (2.0 * s2)) * 0.5 * (1.0 + erf(a1))
                  + np.exp(-(y + rp) ** 2 / (2.0 * s2)) * 0.5 * (1.0 + erf(a2)))


@dataclass
class Implante:
    el: str
    dose: float
    rp: float      # já deslocado pelo óxido (µm, pode ser negativo)
    drp: float
    ld: float

    @property
    def sinal(self) -> float:
        return 1.0 if self.el in DOADORES else -1.0

    def __call__(self, y_um):
        return self.sinal * vertical(y_um, self.dose, self.rp, self.drp, self.ld)


@dataclass
class Perfil:
    """N(x, y) líquida (doadores − aceitadores), x e y em µm (y para dentro do Si)."""
    nb: float                      # dopagem de substrato com sinal
    L: float                       # comprimento de porta (µm)
    sd: list[tuple[Implante, float, float]] = field(default_factory=list)  # (perfil, borda fonte, borda dreno)
    canal: list[Implante] = field(default_factory=list)
    sigma_x: float = 0.0
    ld_sd: float = 0.0

    def liquida(self, x_um, y_um):
        x = np.asarray(x_um, dtype=float)
        y = np.asarray(y_um, dtype=float)
        n = np.full(np.broadcast(x, y).shape, self.nb)
        sx = max(self.sigma_x, 1e-4) * math.sqrt(2.0)
        for imp, xs, xd in self.sd:
            lat = 0.5 * erfc((x - xs) / sx) + 0.5 * erfc((xd - x) / sx)
            n = n + imp(y) * lat
        for imp in self.canal:
            n = n + imp(y)
        return n

    def total(self, x_um, y_um):
        """N_D + N_A (para a mobilidade)."""
        x = np.asarray(x_um, dtype=float)
        y = np.asarray(y_um, dtype=float)
        n = np.full(np.broadcast(x, y).shape, abs(self.nb))
        sx = max(self.sigma_x, 1e-4) * math.sqrt(2.0)
        for imp, xs, xd in self.sd:
            lat = 0.5 * erfc((x - xs) / sx) + 0.5 * erfc((xd - x) / sx)
            n = n + np.abs(imp(y)) * lat
        for imp in self.canal:
            n = n + np.abs(imp(y))
        return n


class Predeposicao:
    """Fonte/dreno por pré-deposição (chave NS): fonte constante, N = NS·erfc(y/2√(Dt)).

    O elemento é o fósforo no canal N e o boro no canal P, como diz o manual.
    """

    def __init__(self, el: str, ns: float, ld: float):
        self.el, self.ns, self.ld = el, ns, ld
        self.sinal = 1.0 if el in ("P", "AS", "SB") else -1.0

    def __call__(self, y_um):
        y = np.maximum(np.asarray(y_um, dtype=float), 0.0)
        return self.sinal * self.ns * erfc(y / (2.0 * max(self.ld, 1e-6)))


def _registros(dados: bytes) -> list[bytes]:
    """Registros de um arquivo Fortran não formatado (marcador de 4 bytes)."""
    import struct
    out, i = [], 0
    while i + 4 <= len(dados):
        (n,) = struct.unpack_from("<i", dados, i)
        if n < 0 or i + 8 + n > len(dados):
            raise ErroDeck("arquivo de dopagem corrompido ou fora do formato Fortran não formatado")
        out.append(dados[i + 4:i + 4 + n])
        i += 8 + n
    return out


class PerfilTabela:
    """Dopagem lida de um arquivo externo (PROFILE FILE=2-D ou 1-D), manual cap. 4.

    2-D: a tabela (PL lateral, PV vertical) vale para a fonte; o dreno é o
    espelho em x = L. PL < 0 é a superfície livre, PL = 0 a borda da máscara,
    PL > 0 o trecho sob a porta; além da tabela vale a coluna da ponta.
    """

    def __init__(self, L: float, pl, pv, doador, aceitador, dreno=None):
        from scipy.interpolate import RegularGridInterpolator
        self.L = L
        pl, pv = np.asarray(pl, dtype=float), np.asarray(pv, dtype=float)
        # só pontos estritamente crescentes (um arquivo com coordenada repetida
        # quebraria a interpolação)
        kl = np.concatenate([[True], np.diff(pl) > 0])
        kv = np.concatenate([[True], np.diff(pv) > 0])
        doador = np.asarray(doador)[np.ix_(kv, kl)]
        aceitador = np.asarray(aceitador)[np.ix_(kv, kl)]
        if dreno is not None:
            dreno = (np.asarray(dreno[0])[np.ix_(kv, kl)], np.asarray(dreno[1])[np.ix_(kv, kl)])
        self.pl, self.pv = pl[kl], pv[kv]
        def interp(t):
            return RegularGridInterpolator((self.pv, self.pl), np.asarray(t), bounds_error=False,
                                           fill_value=None)
        self._d, self._a = interp(doador), interp(aceitador)
        self._dd = self._ad = None
        if dreno is not None:
            self._dd, self._ad = interp(dreno[0]), interp(dreno[1])
        meio = (np.asarray(doador)[-1, -1] - np.asarray(aceitador)[-1, -1])
        self.nb = float(meio)
        self.sd = [True]
        # subdifusão típica para a malha: a borda da junção na superfície
        self.sigma_x = 0.0
        self.ld_sd = 0.0

    def _avaliar(self, x_um, y_um):
        x = np.asarray(x_um, dtype=float)
        y = np.asarray(y_um, dtype=float)
        x, y = np.broadcast_arrays(x, y)
        fonte = x <= self.L / 2
        pl = np.where(fonte, x, self.L - x)
        pl = np.clip(pl, self.pl[0], self.pl[-1])
        yy = np.clip(np.maximum(y, 0.0), self.pv[0], self.pv[-1])
        pts = np.column_stack([yy.ravel(), pl.ravel()])
        d = self._d(pts).reshape(x.shape)
        a = self._a(pts).reshape(x.shape)
        if self._dd is not None:
            d = np.where(fonte, d, self._dd(pts).reshape(x.shape))
            a = np.where(fonte, a, self._ad(pts).reshape(x.shape))
        return np.maximum(d, 0.0), np.maximum(a, 0.0)

    def liquida(self, x_um, y_um):
        d, a = self._avaliar(x_um, y_um)
        return d - a

    def total(self, x_um, y_um):
        d, a = self._avaliar(x_um, y_um)
        return d + a


def ler_arquivo_2d(caminho, L_um: float) -> PerfilTabela:
    """Lê o arquivo FILE=2-D (NPIECE; NL,NV; PL; PV; doadores; aceitadores[; derivadas])."""
    import struct
    from pathlib import Path as _P
    regs = _registros(_P(caminho).read_bytes())
    if len(regs) < 4:
        raise ErroDeck("arquivo de dopagem 2-D incompleto")
    (npiece,) = struct.unpack("<i", regs[0][:4])
    nl, nv = struct.unpack("<ii", regs[1][:8])
    if not (2 <= nl <= 10000 and 2 <= nv <= 10000):
        raise ErroDeck(f"arquivo de dopagem 2-D: NL={nl}, NV={nv} fora da faixa")
    dbl = lambda r: np.frombuffer(r, dtype="<f8")
    pl = dbl(regs[2])[:nl] * 1e4
    pv = dbl(regs[3])[:nv] * 1e4
    k = 4
    pecas = []
    deriv = npiece > 0
    for _ in range(2 if abs(npiece) == 2 else 1):
        tabs = []
        for _esp in range(2):                 # doadores, aceitadores
            linhas = [dbl(regs[k + j])[:nl] for j in range(nv)]
            k += nv
            if deriv:
                k += 2 * nv                   # dC/dl e dC/dv: o MOSIM interpola sem elas
            tabs.append(np.array(linhas))
        pecas.append(tabs)
    # o manual pede um PL = 0 exato (a borda da máscara); a interpolação não
    # precisa dele, e o write_2d_profile do próprio programa nem sempre o inclui
    dreno = pecas[1] if len(pecas) == 2 else None
    return PerfilTabela(L_um, pl, pv, pecas[0][0], pecas[0][1], dreno)


def ler_arquivo_1d(caminho, L_um: float, assim: bool, xoff_um: float, nb_padrao: float) -> "Perfil":
    """FILE=1-D: fatias (fonte/dreno, canal[, segunda fonte/dreno]) estendidas a 2-D.

    O espalhamento lateral das fatias de fonte/dreno segue o modelo analítico:
    σ = 0,8·xj/√2, a subdifusão típica de uma difusão (o manual não o especifica).
    """
    import struct
    from pathlib import Path as _P
    regs = _registros(_P(caminho).read_bytes())
    _, yinc = struct.unpack("<dd", regs[0][:16])
    n = len(regs[1]) // 8
    nslice = n // 4
    tab = np.array([np.frombuffer(r, dtype="<f8")[:4 * nslice] for r in regs[1:] if len(r) >= 32 * nslice])
    y = np.arange(len(tab)) * yinc * 1e4

    class Fatia:
        def __init__(self, j):
            self.liq = tab[:, 4 * j + 2] - tab[:, 4 * j]
            self.tot = tab[:, 4 * j + 2] + tab[:, 4 * j]
            s_ = np.sign(self.liq)
            mud = np.where(s_[1:] != s_[:-1])[0]
            self.xj = float(y[mud[0]]) if len(mud) else float(y[-1])
            self.ld = 0.8 * self.xj / math.sqrt(2.0)
            self.sinal = 1.0

        def __call__(self, yy):
            return np.interp(np.asarray(yy, dtype=float), y, self.liq, right=self.liq[-1])

        def total(self, yy):
            return np.interp(np.asarray(yy, dtype=float), y, self.tot, right=self.tot[-1])

    sd1, ch = Fatia(0), Fatia(1)
    canal_liq = lambda yy: ch(yy)

    class Canal:
        ld = 0.0
        def __call__(self, yy):
            return canal_liq(yy)

    perfis = []
    if nslice >= 3:
        sd3 = Fatia(2)
        if assim and not xoff_um:
            perfis = [(sd1, -0.0, math.inf), (sd3, -math.inf, L_um)]
        elif assim:
            perfis = [(sd1, 0.0, L_um), (sd3, -math.inf, L_um + xoff_um)]
        else:
            perfis = [(sd1, 0.0, L_um), (sd3, -xoff_um, L_um + xoff_um)]
    else:
        perfis = [(sd1, 0.0, L_um)]
    # a fatia de canal já traz o substrato: nb = 0 e o canal entra como implante
    sigma = math.sqrt(2.0) * max(f[0].ld for f in perfis)
    return Perfil(nb=0.0, L=L_um, sd=[(f[0], f[1], f[2]) for f in perfis], canal=[Canal()],
                  sigma_x=sigma, ld_sd=0.0)


def montar(deck: Deck, canal_n: bool, L_um: float, tins_um: float, dopfile=None) -> Perfil:
    perfis = deck.todas("PROFILE")
    if not perfis:
        raise ErroDeck("falta a diretiva PROFILE")
    arq = [p for p in perfis if (p.txt("FILE", "NO") or "NO")[0] in "12Y"]
    if arq:
        if dopfile is None:
            raise ErroDeck("PROFILE FILE=…: falta o arquivo de dopagem (unidade NUMDOP)")
        tipo = arq[0].txt("FILE")[0]
        if tipo == "2":
            return ler_arquivo_2d(dopfile, L_um)
        return ler_arquivo_1d(dopfile, L_um, arq[0].logico("ASYM"),
                              (arq[0].num("XOFF", 0.0) or 0.0) * 1e4, 0.0)
    nb = None
    temp = time = ld = None
    tox = 0.0
    for p in perfis:
        if "NB" in p:
            nb = p.num("NB")
        temp = p.num("TEMP", temp)
        time = p.num("TIME", time)
        ld = p.num("LD", ld)
        tox = p.num("TOX", tox * 1e-4) * 1e4 if "TOX" in p else tox
        if "NS" in p and any(k in p for k in ("ELEM", "DOSE", "AKEV")):
            raise ErroDeck("*PROFILE* NS não se combina com ELEM, DOSE ou AKEV")
    if nb is None:
        nb = 0.0
    subs = (perfis[0].txt("SUBS") or ("P" if canal_n else "N"))[0]
    nb_sinal = -nb if subs == "P" else nb
    sd: list[tuple[Implante, float, float]] = []
    # Um único recozimento de fonte/dreno: o comprimento de difusão vale para
    # todos os perfis e usa o D do elemento da diretiva que traz TEMP/TIME.
    com_elem = [p for p in perfis if "ELEM" in p or "NS" in p]
    ld_sd = 0.0
    if com_elem:
        if ld is not None:
            ld_sd = ld * 1e4
        else:
            if temp is None or time is None:
                raise ErroDeck("MISSING DATA ON *PROFILE* STATEMENT")
            dono = next((p for p in com_elem if "TEMP" in p), com_elem[0])
            el_dono = elemento(dono.txt("ELEM")) if "ELEM" in dono else ("P" if canal_n else "B")
            ld_sd = math.sqrt(difusividade(el_dono, temp) * time) * 1e4
    assim = any(p.logico("ASYM") for p in perfis)
    if assim and len(com_elem) != 2:
        raise ErroDeck("*PROFILE* ASYM=YES exige duas diretivas PROFILE (fonte e dreno)")
    for i, p in enumerate(com_elem):
        xoff = (p.num("XOFF", 0.0) or 0.0) * 1e4
        if "NS" in p:
            el = "P" if canal_n else "B"
            imp = Predeposicao(el, p.num("NS"), ld_sd)
            if xoff < 0 and not assim:
                raise ErroDeck("*PROFILE* XOFF negativo exige ASYM=YES")
            sd.append((imp, -xoff, L_um + xoff))
            continue
        el = elemento(p.txt("ELEM"))
        dose, akev = p.num("DOSE"), p.num("AKEV")
        if dose is None or akev is None:
            raise ErroDeck("MISSING DATA ON *PROFILE* STATEMENT")
        rp, drp, k = momentos(el, akev)
        imp = Implante(el, dose, rp - k * tox, drp, ld_sd)
        if assim and i == 0:
            # primeiro PROFILE: só a fonte, se não houver XOFF; com XOFF, os dois lados
            tem_xoff = any("XOFF" in q for q in com_elem)
            sd.append((imp, 0.0, L_um if tem_xoff else math.inf))
        elif assim and i == 1:
            # segundo PROFILE: só o dreno (deslocado de XOFF, se houver)
            sd.append((imp, -math.inf, L_um + xoff))
        else:
            sd.append((imp, -xoff, L_um + xoff))
    canal: list[Implante] = []
    imps = deck.todas("IMPLANT")
    ctemp = ctime = None
    for p in imps:
        ctemp = p.num("TEMP", ctemp)
        ctime = p.num("TIME", ctime)
    dono_c = next((p for p in imps if "TEMP" in p), imps[0] if imps else None)
    for p in imps:
        el = elemento(p.txt("ELEM") or "")
        dose, akev = p.num("DOSE"), p.num("AKEV")
        if dose is None or akev is None:
            raise ErroDeck("MISSING DATA ON *IMPLANT* STATEMENT")
        rp, drp, k = momentos(el, akev)
        if "LD" in p:
            lc = p.num("LD") * 1e4
        else:
            if ctemp is None or ctime is None:
                raise ErroDeck("MISSING DATA ON *IMPLANT* STATEMENT")
            el_d = elemento(dono_c.txt("ELEM") or el)
            lc = math.sqrt(difusividade(el_d, ctemp) * ctime) * 1e4
        canal.append(Implante(el, dose, rp - k * tins_um, drp, lc))
    sigma_x = math.sqrt(2.0) * max((s[0].ld for s in sd), default=0.0)
    return Perfil(nb=nb_sinal, L=L_um, sd=sd, canal=canal, sigma_x=sigma_x, ld_sd=ld_sd)


def exportar_2d(caminho, liquida, total, L_um: float, pl_um, pv_um) -> None:
    """Grava um perfil no formato FILE=2-D (NPIECE=−1, sem derivadas).

    ``liquida(x, y)`` e ``total(x, y)`` em µm e cm⁻³; ``pl_um`` é a posição
    lateral a partir da borda da máscara (negativa para a fonte), ``pv_um`` a
    profundidade. É o que a ponte com o SUPREM usa para entregar o perfil
    calculado, ponto a ponto, ao motor de dispositivo.
    """
    import struct
    def unicos(v):
        v = np.sort(np.asarray(v, dtype=float))
        manter = np.concatenate([[True], np.diff(v) > 1e-9 * max(1.0, float(np.abs(v).max()))])
        return v[manter]

    pl = unicos(pl_um)
    pv = unicos(pv_um)
    X, Y = np.meshgrid(pl, pv)
    liq = liquida(X, Y)
    tot = total(X, Y)
    doador = np.maximum((tot + liq) / 2.0, 0.0)
    aceit = np.maximum((tot - liq) / 2.0, 0.0)

    def reg(b: bytes) -> bytes:
        return struct.pack("<i", len(b)) + b + struct.pack("<i", len(b))

    with open(caminho, "wb") as f:
        f.write(reg(struct.pack("<i", -1)))
        f.write(reg(struct.pack("<ii", len(pl), len(pv))))
        f.write(reg((pl * 1e-4).astype("<f8").tobytes()))
        f.write(reg((pv * 1e-4).astype("<f8").tobytes()))
        for tab in (doador, aceit):
            for linha in tab:
                f.write(reg(linha.astype("<f8").tobytes()))
