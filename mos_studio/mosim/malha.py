"""Malha tensorial (linhas em x e em y) graduada a partir de pontos de interesse."""
from __future__ import annotations

import numpy as np


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
