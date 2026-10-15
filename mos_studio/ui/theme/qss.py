"""Geração da folha de estilo Qt a partir dos tokens do design.

Este módulo não contém uma única cor ou família tipográfica literal: tudo vem
de :mod:`mos_studio.ui.theme.tokens`. Trocar um token troca a interface inteira.

Variantes de widget são selecionadas por propriedades dinâmicas do Qt, não por
estilo embutido no widget — por exemplo ``botao.setProperty("variant",
"primary")`` ou ``rotulo.setProperty("role", "eyebrow")``.
"""

from __future__ import annotations

from . import fonts, tokens


def stylesheet(theme: str = tokens.DEFAULT_THEME) -> str:
    """Folha de estilo completa do aplicativo para o tema pedido."""
    c = tokens.palette(theme)
    s, r, d = tokens.SPACE, tokens.RADIUS, tokens.DIMENSION
    fs = tokens.FONT_SIZES
    sans = fonts.resolve_family("sans")
    mono = fonts.resolve_family("mono")
    display = fonts.resolve_family("display")
    serif = fonts.resolve_family("serif")
    on_accent = tokens.ON_ACCENT

    return f"""
/* ── Base ───────────────────────────────────────────────────────── */
QWidget {{
    background: {c['bg']};
    color: {c['ink']};
    font-family: "{sans}";
    font-size: {fs['body']}px;
}}
QWidget:disabled {{ color: {c['ink-faint']}; }}
/* Só os contêineres marcados com [surface=...] pintam fundo; o resto é
   transparente, senão um rótulo apaga a superfície elevada atrás dele. */
QLabel, QCheckBox, QRadioButton, QSplitter, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QToolTip {{
    background: {c['bg-3']};
    color: {c['ink']};
    border: {d['border']}px solid {c['line-strong']};
    padding: {s['3']}px {s['5']}px;
}}

/* ── Superfícies ────────────────────────────────────────────────── */
QWidget[surface="chrome"] {{ background: {c['chrome']}; }}
QWidget[surface="raised"]  {{ background: {c['bg-2']}; }}
QWidget[surface="sunken"]  {{ background: {c['bg-3']}; }}
QWidget[surface="code"]    {{ background: {c['code-bg']}; }}
QWidget[surface="accent-soft"] {{ background: {c['accent-soft']}; }}

/* cartão dos roteiros guiados: fundo próprio, borda e cantos arredondados,
   para destacar-se do escurecido que o cerca */
QWidget[role="tour-card"] {{
    background: {c['bg']};
    border: 1px solid {c['line-strong']};
    border-radius: {r['lg']}px;
}}
/* cada roteiro do cartão de tutorial: um botão do tamanho do cartão, com o
   fundo escuro do herói e a borda acendendo no hover */
QWidget[role="tutorial-entry"] {{
    background: {c['chrome']};
    border: 1px solid {c['hero-line']};
    border-radius: {r['md']}px;
}}
QWidget[role="tutorial-entry"][hovered="true"] {{
    border-color: {c['accent']};
}}
QWidget[role="tutorial-card"] {{
    border: 1px solid {c['hero-line']};
    border-radius: {r['lg']}px;
}}
QLabel[role="tour-code"] {{
    background: {c['code-bg']};
    border: 1px solid {c['line']};
    border-radius: {r['sm']}px;
    font-family: "{mono}";
    font-size: {fs['small']}px;
}}

QFrame[role="hline"] {{
    background: {c['line']};
    max-height: {d['border']}px;
    min-height: {d['border']}px;
    border: none;
}}
QFrame[role="vline"] {{
    background: {c['line']};
    max-width: {d['border']}px;
    min-width: {d['border']}px;
    border: none;
}}
QFrame[role="hline-strong"] {{
    background: {c['line-strong']};
    max-height: {d['border']}px;
    min-height: {d['border']}px;
    border: none;
}}

/* ── Herói da tela inicial ──────────────────────────────────────────
   O herói é escuro nos dois temas. Precisa de regras próprias porque o
   `color` do QSS vence a paleta do widget. */
QWidget[onhero="true"], QWidget[onhero="ink"], QWidget[onhero="dim"] {{
    background: transparent;
}}
QLabel[onhero="ink"]  {{ color: {c['hero-ink']}; }}
QLabel[onhero="dim"]  {{ color: {c['hero-ink-dim']}; }}
QLabel[onhero="true"] {{ color: {c['hero-ink']}; }}
QPushButton[onhero="true"] {{
    color: {c['hero-ink']};
    border-color: {c['hero-border']};
}}
QPushButton[onhero="true"]:hover {{
    background: {c['hero-ink']};
    color: {c['hero-bg']};
    border-color: {c['hero-ink']};
}}
QPushButton[variant="primary"][onhero="true"] {{
    background: {c['accent']};
    color: {on_accent};
    border: none;
}}
QPushButton[variant="primary"][onhero="true"]:hover {{
    background: {c['accent-glow']};
    color: {on_accent};
}}

/* ── Papéis de texto ────────────────────────────────────────────── */
QLabel[role="eyebrow"] {{
    font-family: "{mono}";
    font-size: {fs['micro']}px;
    color: {c['ink-dim']};
}}
QLabel[role="eyebrow-accent"] {{
    font-family: "{mono}";
    font-size: {fs['tiny']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
    color: {c['accent-ink']};
}}
QLabel[role="display"] {{
    font-family: "{display}";
    font-size: {fs['h1']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
    color: {c['ink']};
}}
QLabel[role="title"] {{
    font-family: "{display}";
    font-size: {fs['h3']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}
QLabel[role="metric"] {{
    font-family: "{display}";
    font-size: {fs['display']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}
QLabel[role="serif"] {{
    font-family: "{serif}";
    font-size: {fs['title']}px;
    font-style: italic;
    color: {c['ink-dim']};
}}
QLabel[role="mono"] {{
    font-family: "{mono}";
    font-size: {fs['small']}px;
}}
QLabel[role="dim"]  {{ color: {c['ink-dim']}; font-size: {fs['base']}px; }}
QLabel[role="hint"] {{ color: {c['ink-dim']}; font-size: {fs['small']}px; }}
QLabel[role="error"] {{ color: {c['accent-ink']}; font-size: {fs['small']}px; }}
QLabel[role="unit"] {{ color: {c['ink-dim']}; font-size: {fs['base']}px; }}
QLabel[role="brand"] {{
    font-family: "{display}";
    font-size: {fs['lead']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}

/* ── Botões ─────────────────────────────────────────────────────── */
QPushButton {{
    background: transparent;
    color: {c['ink']};
    border: {d['border']}px solid {c['line-strong']};
    border-radius: {d['button-md'] // 2}px;
    min-height: {d['button-md']}px;
    padding: 0 {s['7']}px;
    font-size: {fs['base']}px;
}}
QPushButton:hover {{ border-color: {c['ink']}; }}
QPushButton:pressed {{ background: {c['bg-3']}; }}
QPushButton:disabled {{
    color: {c['ink-dim']};
    border-color: {c['line']};
}}

QPushButton[variant="primary"] {{
    background: {c['accent']};
    color: {on_accent};
    border: none;
    border-radius: {d['button-lg'] // 2}px;
    min-height: {d['button-lg']}px;
    padding: 0 {s['10']}px;
    font-size: {fs['body']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}
QPushButton[variant="primary"]:hover {{ background: {c['accent-glow']}; }}
QPushButton[variant="primary"]:disabled {{
    background: transparent;
    color: {c['ink-dim']};
    border: {d['border']}px solid {c['line-strong']};
}}

QPushButton[variant="ghost"] {{
    border-radius: {d['button-lg'] // 2}px;
    min-height: {d['button-lg']}px;
    padding: 0 {s['9']}px;
    font-size: {fs['body']}px;
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}
QPushButton[variant="ghost"]:hover {{
    background: {c['ink']};
    color: {c['bg']};
    border-color: {c['ink']};
}}

QPushButton[variant="small"] {{
    min-height: {d['button-sm']}px;
    border-radius: {d['button-sm'] // 2}px;
    padding: 0 {s['6']}px;
    font-size: {fs['small']}px;
}}
QPushButton[variant="danger"] {{
    min-height: {d['button-md']}px;
    border-radius: {d['button-md'] // 2}px;
    padding: 0 {s['7']}px;
}}
QPushButton[variant="danger"]:hover {{
    border-color: {c['accent']};
    color: {c['accent-ink']};
}}
QPushButton[variant="icon"] {{
    min-width: {d['button-md']}px;
    max-width: {d['button-md']}px;
    min-height: {d['button-md']}px;
    border-radius: {d['button-md'] // 2}px;
    padding: 0;
    font-size: {fs['small']}px;
}}

/* segmento (escolha entre valores) */
QPushButton[variant="segment"] {{
    min-height: {d['button-md']}px;
    border-radius: {d['button-md'] // 2}px;
    padding: 0 {s['7']}px;
}}
QPushButton[variant="segment"]:checked {{
    background: {c['ink']};
    color: {c['bg']};
    border-color: {c['ink']};
}}

/* abas da navegação principal */
QPushButton[variant="nav"] {{
    background: transparent;
    border: none;
    border-top: 2px solid transparent;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    min-height: {d['header-height'] - 2}px;
    padding: 0 {s['7']}px;
    color: {c['ink-dim']};
    font-weight: {tokens.FONT_WEIGHTS['medium']};
}}
QPushButton[variant="nav"]:hover {{ color: {c['ink']}; }}
QPushButton[variant="nav"]:checked {{
    color: {c['ink']};
    border-bottom-color: {c['accent']};
}}

/* botão-link (texto sublinhado) */
QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0;
    min-height: 0;
    color: {c['accent-ink']};
    font-size: {fs['small']}px;
    text-align: left;
}}
QPushButton[variant="link"]:hover {{ color: {c['accent']}; }}

/* ── Campos ─────────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {c['bg-2']};
    color: {c['ink']};
    border: {d['border']}px solid {c['line-strong']};
    border-radius: {r['md']}px;
    padding: 0 {s['6']}px;
    min-height: {d['input-height']}px;
    selection-background-color: {c['accent']};
    selection-color: {on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {c['ink']};
}}
QLineEdit[state="invalid"] {{ border-color: {c['accent']}; }}
QLineEdit[role="mono"], QPlainTextEdit[role="mono"] {{
    font-family: "{mono}";
    font-size: {fs['base']}px;
}}
QPlainTextEdit, QTextEdit {{ padding: {s['6']}px; }}

QCheckBox {{ spacing: {s['4']}px; font-size: {fs['base']}px; }}
QCheckBox::indicator {{
    width: {s['8']}px;
    height: {s['8']}px;
    border: {d['border']}px solid {c['line-strong']};
    border-radius: {r['xs']}px;
    background: {c['bg-2']};
}}
QCheckBox::indicator:checked {{
    background: {c['accent']};
    border-color: {c['accent']};
}}
QCheckBox::indicator:hover {{ border-color: {c['ink']}; }}

QComboBox {{
    background: {c['bg-2']};
    border: {d['border']}px solid {c['line-strong']};
    border-radius: {r['md']}px;
    padding: 0 {s['6']}px;
    min-height: {d['field-height-sm']}px;
}}
QComboBox:hover {{ border-color: {c['ink']}; }}
QComboBox::drop-down {{ border: none; width: {s['10']}px; }}
QComboBox QAbstractItemView {{
    background: {c['bg-2']};
    border: {d['border']}px solid {c['line-strong']};
    selection-background-color: {c['bg-4']};
    selection-color: {c['ink']};
    outline: none;
}}

/* ── Listas ─────────────────────────────────────────────────────── */
QListWidget, QTreeWidget, QTableWidget {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: {r['md']}px;
    margin: 0 0 {s['1']}px 0;
    padding: 0;
    color: {c['ink']};
}}
QListWidget::item:selected {{ background: {c['bg-3']}; }}
QListWidget::item:hover {{ background: {c['bg-2']}; }}

/* ── Rolagem ────────────────────────────────────────────────────── */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: {d['scrollbar']}px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['line-strong']};
    border-radius: {r['xs']}px;
    min-height: {s['12']}px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['ink-faint']}; }}
QScrollBar:horizontal {{
    background: transparent;
    height: {d['scrollbar']}px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c['line-strong']};
    border-radius: {r['xs']}px;
    min-width: {s['12']}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0; background: none; border: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ── Divisores ──────────────────────────────────────────────────── */
QSplitter::handle {{ background: {c['line']}; }}
QSplitter::handle:horizontal {{ width: {d['border']}px; }}
QSplitter::handle:vertical {{ height: {d['border']}px; }}

/* ── Menus ──────────────────────────────────────────────────────── */
QMenu {{
    background: {c['bg-2']};
    border: {d['border']}px solid {c['line-strong']};
    padding: {s['2']}px;
}}
QMenu::item {{ padding: {s['4']}px {s['8']}px; border-radius: {r['sm']}px; }}
QMenu::item:selected {{ background: {c['bg-4']}; }}
"""
