"""Camada de tema: tokens do design, fontes e folha de estilo.

API usada pelo resto da interface::

    from mos_studio.ui import theme
    theme.apply(app, "claro")          # aplica a folha de estilo
    theme.color("accent")              # cor do tema em vigor
    theme.font("mono", "small")        # QFont a partir dos tokens
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget

from . import fonts, qss, tokens
from .fonts import font, missing_families, resolve_family
from .qss import stylesheet
from .tokens import (DIMENSION, DURATION, FONT_SIZES, FONT_WEIGHTS,
                     LETTER_SPACING, RADIUS, SPACE, DEFAULT_THEME)

_current = tokens.DEFAULT_THEME


def apply(app: QApplication, theme: str = tokens.DEFAULT_THEME) -> None:
    """Aplica o tema ao aplicativo inteiro."""
    global _current
    _current = theme if theme in tokens.PALETTES else tokens.DEFAULT_THEME
    app.setStyleSheet(qss.stylesheet(_current))
    app.setFont(fonts.font("sans", "body"))


def current() -> str:
    """Nome do tema em vigor."""
    return _current


def color(key: str) -> str:
    """Valor de um token de cor no tema em vigor."""
    return tokens.palette(_current)[key]


def qcolor(key: str) -> QColor:
    """Token de cor como :class:`QColor` (entende o ``rgba(r, g, b, a)``)."""
    raw = color(key)
    if raw.startswith("rgba"):
        parts = [int(x) for x in raw[raw.index("(") + 1:raw.index(")")].split(",")]
        return QColor(*parts)
    return QColor(raw)


def space(key: str) -> int:
    """Valor da escala de espaçamento."""
    return tokens.SPACE[key]


def dimension(key: str) -> int:
    """Valor da escala de dimensões."""
    return tokens.DIMENSION[key]


def radius(key: str) -> int:
    """Valor da escala de raios."""
    return tokens.RADIUS[key]


def mark(widget: QWidget, **props) -> QWidget:
    """Marca propriedades dinâmicas (as variantes do QSS) e devolve o widget.

    Exemplo: ``theme.mark(botao, variant="primary")``.
    """
    for key, value in props.items():
        widget.setProperty(key, value)
    return widget


def restyle(widget: QWidget) -> None:
    """Recalcula o estilo após mudar uma propriedade dinâmica."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


__all__ = ["apply", "current", "color", "qcolor", "space", "dimension",
           "radius", "mark", "restyle", "font", "stylesheet", "fonts",
           "tokens", "missing_families", "resolve_family", "QFont",
           "DIMENSION", "DURATION", "FONT_SIZES", "FONT_WEIGHTS",
           "LETTER_SPACING", "RADIUS", "SPACE", "DEFAULT_THEME"]
