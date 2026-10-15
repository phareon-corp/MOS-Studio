"""Carrega funções do ``suprem3.py`` original para os testes de paridade.

O arquivo antigo importa Tkinter e monta a janela ao ser executado inteiro;
aqui extraímos apenas os trechos de código das funções de backend e os
executamos num namespace isolado. É o que permite afirmar, com teste, que a
migração moveu as funções sem mudar o comportamento.
"""

from __future__ import annotations

import re
from pathlib import Path

LEGACY = Path(__file__).resolve().parent.parent / "suprem3.py"

_TRECHOS = (
    ("def step_to_code", "_SUPREM_DOPANTS"),
    ("def _dopants_in_steps", "def _detect_junctions"),
    ("def build_profile_deck", "def parse_suprem_profiles"),
    ("def parse_suprem_profiles", "def parse_in_file"),
    ("def parse_in_file", "def parse_out_file"),
    ("def parse_out_file", "def check_exe_integrity"),
    ("def ensure_profile_print", "def run_suprem("),
    ("def parse_oxide_thickness", "def deal_grove_fit"),
    ("def deal_grove_fit", "class SupremApp"),
    ("def _detect_junctions", "def build_profile_deck"),
    ("def build_minimos_deck", "def parse_minimos_pif"),
    ("def parse_minimos_pif", "AMBIENTS ="),
)


def available() -> bool:
    """``True`` se o arquivo antigo ainda está no repositório."""
    return LEGACY.exists()


def namespace() -> dict:
    """Namespace com as funções de backend da versão Tkinter."""
    src = LEGACY.read_text(encoding="utf-8")
    ns: dict = {
        "re": re,
        "AMBIENTS": ["DRYO2", "WETO2", "NITROGEN", "BORON", "PHOSPHOR",
                     "ARSENIC", "ANTIMONY"],
        "DOPANTS": ["BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY", "BF2"],
        "MATERIALS": ["SILICON", "OXIDE", "NITRIDE", "ALUMINUM", "POLYSILI"],
        "_SUPREM_DOPANTS": ["Boron", "Phosphorus", "Arsenic", "Antimony"],
    }
    for inicio, fim in _TRECHOS:
        i, j = src.index(inicio), src.index(fim)
        exec(src[i:j], ns)  # noqa: S102 - é o próprio código do repositório
    return ns
