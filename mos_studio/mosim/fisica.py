"""Constantes e modelos físicos do silício, conforme o manual do MINIMOS 6.

Equações citadas como (2.n) são as do capítulo 2 do manual ("The Physical
Models of MINIMOS"), que por sua vez remetem a Selberherr, *Analysis and
Simulation of Semiconductor Devices* (1984).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Q = 1.602189e-19          # C
K_EV = 8.617e-5           # eV/K (VT = 25,85 mV a 300 K, como o MINIMOS imprime)
EPS0 = 8.854187817e-14    # F/cm
EPS_SI = 11.7
EPS_OX = 3.9
EPS_NIT = 7.2

#: Diferença de função trabalho porta–nível intrínseco (V), chave GATE.
FUNCAO_TRABALHO = {"A": -0.59, "N": -0.55, "P": 0.55}


def tensao_termica(T: float) -> float:
    return K_EV * T


def banda_proibida(T: float) -> float:
    """Eg(T) do silício em eV, eqs. (2.41)/(2.42)."""
    if T <= 170.0:
        return 1.17 + 1.059e-5 * T - 6.05e-7 * T * T
    return 1.1785 - 9.025e-5 * T - 3.05e-7 * T * T


def intrinseca(T: float) -> float:
    """ni(T) em cm^-3, eqs. (2.38)–(2.43)."""
    mn = 1.045 + 4.5e-4 * T
    mp = 0.523 + 1.4e-3 * T - 1.48e-6 * T * T
    nc_nv = 2.51e19 * (mn * mp * (T / 300.0) ** 2) ** 0.75
    return nc_nv * math.exp(-banda_proibida(T) / (2.0 * K_EV * T))


@dataclass
class Mobilidade:
    """Modelo de mobilidade do silício, eqs. (2.1)–(2.19) e tabela da p. 20.

    Os pesos da diretiva MOBILITY (ML, MI, MC, MR, MS, MT, MV, MB) multiplicam
    os parâmetros correspondentes; MS divide y_ref.
    """
    T: float = 300.0
    portador: str = "n"
    ML: float = 1.0
    MI: float = 1.0
    MC: float = 1.0
    MR: float = 1.0
    MS: float = 1.0
    MT: float = 1.0
    MV: float = 1.0
    MB: float = 1.0

    def __post_init__(self):
        t = self.T / 300.0
        if self.portador == "n":
            self.mu_l = 1430.0 * t ** -2.0 * self.ML
            mmin = 80.0
            self.c_ref = 1.12e17 * t ** 3.2 * self.MI
            self.mu_ref = 638.0 * t ** -1.19 * self.MR
            self.s_ref = 7.0e5 * self.MT
            self.gama = 1.69 * self.MC
            self.vsat = 1.45e7 * math.sqrt(math.tanh(155.0 / self.T)) * self.MV
            self.beta = 2.0 * self.MB
        else:
            self.mu_l = 460.0 * t ** -2.18 * self.ML
            mmin = 45.0
            self.c_ref = 2.23e17 * t ** 3.2 * self.MI
            self.mu_ref = 240.0 * t ** -1.09 * self.MR
            self.s_ref = 2.7e5 * self.MT
            self.gama = 1.0 * self.MC
            self.vsat = 9.05e6 * math.sqrt(math.tanh(312.0 / self.T)) * self.MV
            self.beta = 1.0 * self.MB
        if self.T >= 200.0:
            self.mu_min = mmin * t ** -0.45
        else:
            self.mu_min = mmin * (200.0 / 300.0) ** -0.45 * (self.T / 200.0) ** -0.15
        self.alfa = 0.72 * t ** 0.065
        self.y_ref = 10e-7 / self.MS  # cm

    def impurezas(self, ci):
        """μ^LI (2.3): rede + espalhamento por impurezas (CI = N_D + N_A)."""
        return self.mu_min + (self.mu_l - self.mu_min) / (1.0 + (np.asarray(ci) / self.c_ref) ** self.alfa)

    def superficie(self, mu_li, y, s):
        """μ^LIS (2.11): espalhamento de superfície; y em cm, s = força normal (V/cm)."""
        yy = np.asarray(y) / self.y_ref
        F = 2.0 * np.exp(-yy * yy) / (1.0 + np.exp(-2.0 * yy * yy))
        return (self.mu_ref + (mu_li - self.mu_ref) * (1.0 - F)) / (
            1.0 + F * (np.maximum(s, 0.0) / self.s_ref) ** self.gama)

    def campo(self, mu_lis, f):
        """μ^LISF (2.15): saturação de velocidade; f = força motriz (V/cm)."""
        b = self.beta
        x = 2.0 * mu_lis * np.abs(f) / self.vsat
        return 2.0 * mu_lis / (1.0 + (1.0 + x ** b) ** (1.0 / b))
