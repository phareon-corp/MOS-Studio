"""Ajuste Deal-Grove a partir de espessuras de óxido simuladas.

Movido de ``suprem3.py`` sem mudança de lógica. A interface de oxidação
é de uma etapa posterior; aqui fica só o cálculo, já isolado e testado.
"""

from __future__ import annotations

import math
from typing import Sequence


def deal_grove_fit(times_min: Sequence[float],
                   xo_list: Sequence[float]) -> dict[str, float]:
    """Ajuste linear de ``t/Xo = (1/B)·Xo + A/B`` (Deal-Grove, τ=0).

    Devolve ``A`` (µm), ``B`` (µm²/min e µm²/h), ``B/A`` (µm/h) e ``R²``.
    """
    xs = list(xo_list)                                  # x = Xo
    ys = [t / x for t, x in zip(times_min, xo_list)]    # y = t/Xo
    n = len(xs)
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    den = (n * sxx - sx * sx)
    m = (n * sxy - sx * sy) / den           # 1/B
    c = (sy - m * sx) / n                   # A/B
    ybar = sy / n
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    ss_res = sum((y - (m * x + c)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    B_min = 1.0 / m
    A = c * B_min
    B_h = B_min * 60.0
    return {"m": m, "c": c, "B_min": B_min, "B_h": B_h, "A": A,
            "BA_h": B_h / A if A else float("nan"), "r2": r2}


def deal_grove_xo(t_min: float, A: float, B_min: float) -> float:
    """Espessura prevista pelo modelo, em µm, para um tempo em minutos."""
    return (-A + math.sqrt(A * A + 4 * B_min * t_min)) / 2.0


# ── varredura de oxidação ─────────────────────────────────────────────────

from dataclasses import dataclass, field          # noqa: E402
from typing import Callable                        # noqa: E402


@dataclass
class OxidationPoint:
    """Uma oxidação simulada."""

    time_min: float
    thickness_um: float | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.thickness_um is not None and self.thickness_um > 0


@dataclass
class OxidationSweep:
    """O resultado de varrer vários tempos de oxidação."""

    points: list[OxidationPoint] = field(default_factory=list)
    fit: dict[str, float] = field(default_factory=dict)
    ambient: str = "WETO2"
    temperature: float = 1000.0
    orientation: str = "100"
    doping: str = "1E15"
    engine_id: str = "suprem3"
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.fit) and len([p for p in self.points if p.ok]) >= 2

    def valid(self) -> list[OxidationPoint]:
        return [p for p in self.points if p.ok]


def oxidation_steps(time_min: float, ambient: str, temperature: float,
                    orientation: str, doping: str) -> list[dict]:
    """Os três passos de receita de uma oxidação isolada.

    Separado de :func:`build_deck` porque cada motor traduz a mesma receita
    para o seu próprio dialeto — é a receita que é comum, não o texto.
    """
    return [
        {"type": "INITIALIZE", "params": {
            "orientation": orientation, "dopant": "BORON",
            "concentration": doping, "dx": "5E-3", "thickness": "0.5"}},
        {"type": "DIFFUSION", "params": {
            "ambient": ambient, "temperature": f"{temperature:g}",
            "time": f"{time_min:g}", "gasConc": "", "solidSol": False,
            "tRate": ""}},
        {"type": "PRINT", "params": {
            "what": "", "curve": "", "extra": "LAYER", "filename": "",
            "linespa": ""}},
    ]


def build_deck(time_min: float, ambient: str, temperature: float,
               orientation: str, doping: str, engine_id: str = "suprem3") -> str:
    """Deck de uma única oxidação, terminando na tabela de camadas."""
    from . import engines

    passos = oxidation_steps(time_min, ambient, temperature, orientation, doping)
    return engines.get(engine_id).build_in_file(
        f"OXIDACAO {ambient} {temperature:g}C {time_min:g}MIN", passos)


def sweep(times_min: list[float], *, ambient: str = "WETO2",
          temperature: float = 1000.0, orientation: str = "100",
          doping: str = "1E15", run_dir=None, engine_id: str = "suprem3",
          on_point: Callable[[int, OxidationPoint], None] | None = None,
          should_stop: Callable[[], bool] | None = None) -> OxidationSweep:
    """Roda uma oxidação por tempo e ajusta Deal-Grove sobre as espessuras.

    ``engine_id`` escolhe o simulador (ver :mod:`mos_studio.core.engines`). O
    ajuste é o mesmo nos dois: é justamente comparando o ``B`` ajustado contra
    o valor tabelado de Deal & Grove (1965) que se verifica se um motor
    recém-compilado está calculando oxidação de verdade.
    """
    from . import engines

    motor = engines.get(engine_id)
    run_sync = motor.run_sync
    ler_espessura = motor.oxide_thickness

    resultado = OxidationSweep(ambient=ambient, temperature=temperature,
                               orientation=orientation, doping=doping,
                               engine_id=motor.id)
    for i, t in enumerate(times_min):
        if should_stop is not None and should_stop():
            resultado.error = "varredura cancelada"
            break
        ponto = OxidationPoint(time_min=t)
        try:
            saida = run_sync(build_deck(t, ambient, temperature, orientation,
                                        doping, motor.id), run_dir=run_dir)
            espessura = ler_espessura(saida)
            if espessura is None:
                ponto.error = "a saída não trouxe a camada de óxido"
            else:
                ponto.thickness_um = espessura
        except Exception as exc:                 # noqa: BLE001 - vira recado
            primeira = str(exc).strip().splitlines()
            ponto.error = primeira[0] if primeira else "falha ao executar"
        resultado.points.append(ponto)
        if on_point is not None:
            on_point(i, ponto)

    validos = resultado.valid()
    if len(validos) >= 2:
        resultado.fit = deal_grove_fit([p.time_min for p in validos],
                                       [p.thickness_um for p in validos])
    elif not resultado.error:
        resultado.error = "poucas espessuras válidas para ajustar"
    return resultado


def regime(thickness_um: float, A: float) -> str:
    """Em que regime a oxidação está, comparando Xo com A."""
    if thickness_um < A * 0.5:
        return "linear"
    if thickness_um > A * 2:
        return "parabólico"
    return "transição"


def linear_xo(t_min: float, A: float, B_min: float) -> float:
    """Aproximação linear (óxido fino): Xo ≈ (B/A)·t."""
    return (B_min / A) * t_min if A else 0.0


def parabolic_xo(t_min: float, B_min: float) -> float:
    """Aproximação parabólica (óxido espesso): Xo ≈ √(B·t)."""
    return math.sqrt(B_min * t_min)
