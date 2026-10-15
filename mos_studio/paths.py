"""Localização de tudo que o MOS-Studio lê e escreve em disco.

Regra única desta camada: *nada* de configuração do usuário fica ao lado do
executável. A configuração mora no diretório de configuração do usuário
(``$XDG_CONFIG_HOME/mos-studio`` no Linux, ``%APPDATA%\\mos-studio`` no
Windows); os motores e as saídas de simulação continuam no repositório,
porque são o pacote do programa e o histórico de execuções, não preferências.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

IS_WIN = platform.system() == "Windows"
#: Sufixo dos executáveis no sistema atual (``.exe`` apenas no Windows).
EXE = ".exe" if IS_WIN else ""

#: Raiz do repositório/instalação: o diretório que contém o pacote.
APP_ROOT = Path(__file__).resolve().parent.parent

#: Saídas de simulação, uma subpasta por execução.
RESULTS_DIR = APP_ROOT / "resultados"

#: Diretórios onde procuramos os binários nativos do SUPREM-III.
SUPREM_RUN_DIRS = (
    APP_ROOT / "suprem-run",
    APP_ROOT / "suprem_native" / "suprem-run",
    APP_ROOT / "native" / "suprem-run",
)

#: Diretórios onde procuramos o SUPREM-IV.GS (bin/suprem + data/suprem.uk),
#: construído por ``build_suprem4.sh``.
SUPREM4_DIRS = (
    APP_ROOT / "suprem4-run",
    APP_ROOT / "suprem4" / "bin",
    APP_ROOT / "native" / "suprem4-run",
)

#: Diretórios onde procuramos o MINIMOS (mm_pl + stack.rul).
MINIMOS_DIRS = (
    APP_ROOT / "minimos-run",
    APP_ROOT / "minimos" / "bin",
    APP_ROOT / "minimoswin6_1" / "bin",
    APP_ROOT / "bin",
)


def config_dir() -> Path:
    """Diretório de configuração do usuário, criado se necessário."""
    if IS_WIN:
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = base / "mos-studio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    """Caminho do ``config.json`` do usuário."""
    return config_dir() / "config.json"


def results_dir() -> Path:
    """Diretório de saídas, criado se necessário."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    return RESULTS_DIR


def curto(caminho: Path | str) -> str:
    """Caminho com a pasta pessoal abreviada como ``~``.

    É o que vai para a tela. Dois motivos: o rodapé e os chips de projeto
    são estreitos, e um caminho completo expulsa o resto; e uma captura de
    tela ou uma sessão compartilhada deixa de mostrar o nome de usuário de
    quem está rodando.
    """
    texto = str(caminho)
    try:
        casa = str(Path.home())
    except (RuntimeError, OSError):
        return texto
    if casa and (texto == casa or texto.startswith(casa + os.sep)):
        return "~" + texto[len(casa):]
    return texto
