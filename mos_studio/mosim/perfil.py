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


def montar(deck: Deck, canal_n: bool, L_um: float, tins_um: float) -> Perfil:
    perfis = deck.todas("PROFILE")
    if not perfis:
        raise ErroDeck("falta a diretiva PROFILE")
    if any(p.txt("FILE", "NO")[0] in "12Y" for p in perfis):
        raise ErroDeck("PROFILE FILE=1-D/2-D ainda não é suportado pelo motor aberto")
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
        if "NS" in p:
            raise ErroDeck("PROFILE NS (pré-deposição) ainda não é suportado pelo motor aberto")
        if p.logico("ASYM"):
            raise ErroDeck("PROFILE ASYM ainda não é suportado pelo motor aberto")
    if nb is None:
        nb = 0.0
    subs = (perfis[0].txt("SUBS") or ("P" if canal_n else "N"))[0]
    nb_sinal = -nb if subs == "P" else nb
    sd: list[tuple[Implante, float, float]] = []
    # Um único recozimento de fonte/dreno: o comprimento de difusão vale para
    # todos os perfis e usa o D do elemento da diretiva que traz TEMP/TIME.
    com_elem = [p for p in perfis if "ELEM" in p]
    ld_sd = 0.0
    if com_elem:
        if ld is not None:
            ld_sd = ld * 1e4
        else:
            if temp is None or time is None:
                raise ErroDeck("MISSING DATA ON *PROFILE* STATEMENT")
            dono = next((p for p in com_elem if "TEMP" in p), com_elem[0])
            ld_sd = math.sqrt(difusividade(elemento(dono.txt("ELEM")), temp) * time) * 1e4
    for p in com_elem:
        el = elemento(p.txt("ELEM"))
        dose, akev = p.num("DOSE"), p.num("AKEV")
        if dose is None or akev is None:
            raise ErroDeck("MISSING DATA ON *PROFILE* STATEMENT")
        rp, drp, k = momentos(el, akev)
        imp = Implante(el, dose, rp - k * tox, drp, ld_sd)
        xoff = (p.num("XOFF", 0.0) or 0.0) * 1e4
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
