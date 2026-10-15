"""Resolução das famílias tipográficas do design para fontes do Qt.

O design pede Geist (corpo), Bricolage Grotesque (títulos), Geist Mono
(números e identificadores) e Instrument Serif itálico (ênfase). Nem toda
família está instalada em toda máquina; aqui escolhemos a primeira disponível
de cada cadeia definida em :mod:`tokens` e, se preciso, caímos na fonte de
sistema. As divergências ficam registradas em ``docs/fidelidade-visual.md``.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase

from . import tokens


@lru_cache(maxsize=None)
def resolve_family(role: str) -> str:
    """Primeira família instalada da cadeia do papel pedido."""
    available = {f.lower() for f in QFontDatabase.families()}
    for family in tokens.font_stack(role):
        if family.lower() in available:
            return family
    # nenhuma instalada: deixa o Qt escolher pelo tipo genérico
    generic = tokens.font_stack(role)[-1]
    return {"monospace": "monospace", "serif": "serif"}.get(generic, "sans-serif")


@lru_cache(maxsize=None)
def missing_families() -> tuple[str, ...]:
    """Famílias pedidas pelo design que não estão instaladas.

    Serve para o diagnóstico de fidelidade visual: a interface funciona sem
    elas, mas o desenho não é o do arquivo de design.
    """
    available = {f.lower() for f in QFontDatabase.families()}
    wanted = ("Geist", "Bricolage Grotesque", "Geist Mono", "Instrument Serif")
    return tuple(f for f in wanted if f.lower() not in available)


def font(role: str = "sans", size: str = "body", weight: str = "regular",
         spacing: str = "normal", italic: bool = False) -> QFont:
    """Monta um :class:`QFont` a partir dos tokens.

    ``role`` é ``sans``/``display``/``mono``/``serif``; ``size``, ``weight`` e
    ``spacing`` são chaves de :mod:`tokens`. O espaçamento entre letras existe
    aqui porque o QSS não tem ``letter-spacing``.
    """
    f = QFont(resolve_family(role))
    f.setPixelSize(tokens.FONT_SIZES.get(size, tokens.FONT_SIZES["body"]))
    f.setWeight(QFont.Weight(tokens.FONT_WEIGHTS.get(weight, 400)))
    f.setItalic(italic)
    pct = tokens.LETTER_SPACING.get(spacing, 100.0)
    if pct != 100.0:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, pct)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f
