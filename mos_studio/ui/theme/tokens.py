"""Fonte única de verdade do visual do MOS-Studio.

Todo valor de cor, tipografia, espaçamento, raio e dimensão usado pela
interface está aqui. Nenhum widget escreve uma cor ou uma fonte literal: eles
leem destes dicionários ou recebem a folha de estilo gerada por
:mod:`mos_studio.ui.theme.qss` a partir deles.

Os valores foram extraídos do arquivo de design (``MOS-Studio
(standalone).html``): as variáveis CSS de ``:root`` são o tema escuro e as de
``[data-theme="light"]`` são o tema claro, que é o padrão do design.
"""

from __future__ import annotations

from typing import Literal

ThemeName = Literal["claro", "escuro"]

#: Tema padrão, como no arquivo de design.
DEFAULT_THEME: ThemeName = "claro"

# ── Cores ─────────────────────────────────────────────────────────────────
# Chaves iguais às variáveis CSS do design, sem o prefixo "--".

DARK: dict[str, str] = {
    "bg": "#08080B",
    "bg-2": "#0E0E12",
    "bg-3": "#14141A",
    "bg-4": "#1C1C24",
    "chrome": "#050507",
    "code-bg": "#0B0B0E",
    "ink": "#F4F1E9",
    "ink-dim": "#A8A39A",
    "ink-faint": "#5C594F",
    "accent": "#FF4A1C",
    "accent-glow": "#FF6B3D",
    "accent-ink": "#FF6B3D",
    "accent-soft": "rgba(255, 74, 28, 31)",     # .12 de alfa
    "amber": "#FFAA1C",
    "line": "rgba(244, 241, 233, 20)",          # .08
    "line-strong": "rgba(244, 241, 233, 46)",   # .18
    "scrim": "rgba(4, 4, 6, 184)",              # .72
    # Escala divergente dos mapas 2-D do MINIMOS. Os campos têm sinal e o
    # zero significa alguma coisa, então a escala é de dois polos com meio
    # neutro — nunca um arco-íris, e nunca uma matiz no meio.
    # Conferida com o validador de paletas: ΔE 27,3 em protanopia e 36,4 em
    # visão normal entre os dois polos, e ambos acima de 3:1 contra o fundo.
    "field-neg": "#3987e5",                     # polo frio (negativo)
    "field-mid": "#2A2A30",                     # neutro do tema escuro
    "field-pos": "#FF4A1C",                     # polo quente (positivo)
    "al": "#6F6B63",                            # alumínio, nas camadas
    "nfill": "rgba(255, 74, 28, 87)",           # silício tipo n
    # O herói da tela inicial é escuro nos dois temas (é assim no design).
    "hero-bg": "#08080B",
    "hero-ink": "#F4F1E9",
    "hero-ink-dim": "#A8A39A",
    "hero-line": "rgba(244, 241, 233, 18)",
    "hero-surface": "rgba(14, 14, 18, 217)",
    "hero-border": "rgba(244, 241, 233, 31)",
}

LIGHT: dict[str, str] = {
    "bg": "#EFECE4",
    "bg-2": "#E5E1D7",
    "bg-3": "#DCD7CB",
    "bg-4": "#D2CCBE",
    "chrome": "#E0DCD1",
    "code-bg": "#F6F4EE",
    "ink": "#0A0A0D",
    "ink-dim": "#4A463D",
    "ink-faint": "#8A867A",
    "accent": "#FF4A1C",
    "accent-glow": "#FF6B3D",
    "accent-ink": "#B8300B",
    "accent-soft": "rgba(255, 74, 28, 31)",     # .12
    "amber": "#A86400",
    "line": "rgba(10, 10, 13, 26)",             # .10
    "line-strong": "rgba(10, 10, 13, 56)",      # .22
    "scrim": "rgba(40, 36, 28, 89)",            # .35
    "field-neg": "#2a78d6",
    "field-mid": "#DCD7CB",
    "field-pos": "#FF4A1C",
    "al": "#A39F95",
    "nfill": "rgba(255, 74, 28, 77)",           # .30
    # Iguais aos do tema escuro: o herói não muda com o tema.
    "hero-bg": "#08080B",
    "hero-ink": "#F4F1E9",
    "hero-ink-dim": "#A8A39A",
    "hero-line": "rgba(244, 241, 233, 18)",
    "hero-surface": "rgba(14, 14, 18, 217)",
    "hero-border": "rgba(244, 241, 233, 31)",
}

PALETTES: dict[str, dict[str, str]] = {"escuro": DARK, "claro": LIGHT}

#: Cor do texto sobre o acento (botão primário) — fixa nos dois temas.
ON_ACCENT = "#000000"

# ── Tipografia ────────────────────────────────────────────────────────────
# Cada papel tem uma cadeia de famílias: a primeira que existir no sistema é
# usada. "Geist" (sans) pode não estar instalada; ver docs/fidelidade-visual.md.

FONT_STACKS: dict[str, tuple[str, ...]] = {
    "sans": ("Geist", "Inter", "Noto Sans", "DejaVu Sans", "sans-serif"),
    "display": ("Bricolage Grotesque", "Geist", "Noto Sans", "sans-serif"),
    "mono": ("Geist Mono", "JetBrains Mono", "DejaVu Sans Mono", "monospace"),
    "serif": ("Instrument Serif", "Georgia", "serif"),
}

#: Tamanhos em pt (o design usa px CSS; a conversão é 1:1 por simplicidade e
#: porque o Qt aplica o DPI do sistema por cima — ver fidelidade-visual.md).
FONT_SIZES: dict[str, int] = {
    "micro": 10,       # rótulos monospace de 10/10.5px
    "tiny": 11,        # 11/11.5px
    "small": 12,       # 12/12.5px
    "base": 13,        # 13/13.5px
    "body": 14,        # corpo do design
    "medium": 15,
    "lead": 18,
    "title": 20,
    "h3": 24,
    "h2": 26,
    "h1": 32,
    "display": 56,     # número grande (xj)
}

FONT_WEIGHTS: dict[str, int] = {
    "regular": 400,
    "medium": 500,
    "semibold": 600,
    "bold": 700,
}

#: Espaçamento entre letras, em porcentagem (QFont.PercentageSpacing).
#: O design usa em; 0.1em ≈ 110%.
LETTER_SPACING: dict[str, float] = {
    "tight": 97.0,      # títulos display (-.03em)
    "tighter": 95.5,    # display grande (-.045em)
    "normal": 100.0,
    "wide": 110.0,      # mono .1em
    "wider": 114.0,     # mono .14em
    "widest": 120.0,    # mono .2em (eyebrow)
}

LINE_HEIGHT = 1.45

# ── Espaçamento, raios e dimensões ────────────────────────────────────────

SPACE: dict[str, int] = {
    "0": 0, "1": 2, "2": 4, "3": 6, "4": 8, "5": 10, "6": 12, "7": 14,
    "8": 16, "9": 18, "10": 20, "11": 22, "12": 24, "13": 26, "14": 28,
    "16": 32, "20": 40, "24": 48,
}

RADIUS: dict[str, int] = {
    "xs": 4, "sm": 6, "md": 8, "lg": 10, "xl": 12, "pill": 999,
}

DIMENSION: dict[str, int] = {
    "header-height": 56,
    "strip-height": 44,
    "footer-height": 28,
    "nav-height": 42,
    "button-sm": 28,
    "button-md": 32,
    "button-lg": 38,
    "button-xl": 50,
    "field-height": 42,
    "field-height-sm": 38,
    "input-height": 36,
    "sidebar-width": 320,
    "deck-min-width": 380,
    "detail-max-width": 780,
    "window-min-width": 1280,
    "window-min-height": 760,
    "scrollbar": 10,
    "border": 1,
}

#: Durações de animação, em ms (o design usa transições CSS; aqui só o pulso
#: do indicador de execução é animado — ver docs/fidelidade-visual.md).
DURATION: dict[str, int] = {"pulse": 3000, "quick": 180}


def palette(theme: str = DEFAULT_THEME) -> dict[str, str]:
    """Paleta do tema pedido; cai no padrão se o nome não existir."""
    return PALETTES.get(theme, PALETTES[DEFAULT_THEME])


def font_stack(role: str) -> tuple[str, ...]:
    """Cadeia de famílias de um papel tipográfico."""
    return FONT_STACKS.get(role, FONT_STACKS["sans"])
