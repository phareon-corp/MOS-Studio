"""Leitura e escrita da configuração do usuário (JSON, no diretório do usuário).

Tolerante a arquivo ausente, vazio ou corrompido: nesses casos vale o padrão,
porque perder uma preferência nunca deve impedir o programa de abrir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import config_file


def load() -> dict[str, Any]:
    """Devolve a configuração salva, ou ``{}`` se não houver nada legível."""
    path = config_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def get(key: str, default: Any = None) -> Any:
    """Lê uma chave da configuração."""
    return load().get(key, default)


def set_many(values: dict[str, Any]) -> None:
    """Grava várias chaves de uma vez, preservando as demais."""
    cfg = load()
    cfg.update(values)
    path = config_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def set(key: str, value: Any) -> None:  # noqa: A001 - espelha a API de dict
    """Grava uma chave da configuração."""
    set_many({key: value})


def migrate_legacy(legacy: Path | None = None) -> bool:
    """Importa um ``config.json`` antigo que vivia ao lado do executável.

    Mantido porque a versão Tkinter gravava a configuração na pasta do
    programa. Só copia as chaves que ainda não existem no destino e nunca
    apaga o arquivo antigo. Devolve ``True`` se algo foi importado.
    """
    from .paths import APP_ROOT

    src = legacy if legacy is not None else APP_ROOT / "config.json"
    if not src.exists() or src.resolve() == config_file().resolve():
        return False
    try:
        old = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(old, dict):
        return False
    cfg = load()
    novo = {k: v for k, v in old.items() if k not in cfg}
    if not novo:
        return False
    set_many(novo)
    return True
