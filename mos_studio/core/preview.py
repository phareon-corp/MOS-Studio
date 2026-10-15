"""Pré-visualização das receitas da biblioteca: perfil real, não ilustração.

A tela inicial mostra o perfil de dopagem de cada receita embutida. Esses
perfis não são desenhados à mão: cada receita é executada no SUPREM-III de
verdade (leva poucos milissegundos) e o resultado fica em cache no diretório
de configuração, para que as aberturas seguintes sejam instantâneas.

Se o motor não estiver disponível, a pré-visualização simplesmente não existe
e a interface diz isso — em vez de exibir uma curva inventada.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from . import deck as deck_mod
from . import suprem
from .library import Recipe
from .parsers import detect_junctions, junction_threshold

CACHE_VERSION = 2


@dataclass
class Preview:
    """O que a tela inicial precisa saber de uma receita."""

    key: str
    points: list[tuple[float, float]] = field(default_factory=list)
    junctions: list[float] = field(default_factory=list)
    surface: float = 0.0
    layers: list[tuple[str, float]] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.points)

    @property
    def junction(self) -> float | None:
        return self.junctions[0] if self.junctions else None


def cache_dir() -> Path:
    d = paths.config_dir() / "previas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_file(key: str) -> Path:
    return cache_dir() / f"{key}.json"


def load_cached(key: str) -> Preview | None:
    """Pré-visualização já calculada, se houver."""
    arquivo = _cache_file(key)
    if not arquivo.exists():
        return None
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if dados.get("versao") != CACHE_VERSION:
        return None
    return Preview(key=key,
                   points=[tuple(p) for p in dados.get("pontos", [])],
                   junctions=list(dados.get("juncoes", [])),
                   surface=float(dados.get("superficie", 0.0)),
                   layers=[tuple(c) for c in dados.get("camadas", [])],
                   error=dados.get("erro", ""))


def _store(p: Preview) -> None:
    try:
        _cache_file(p.key).write_text(json.dumps({
            "versao": CACHE_VERSION,
            "pontos": [list(x) for x in p.points],
            "juncoes": p.junctions,
            "superficie": p.surface,
            "camadas": [list(c) for c in p.layers],
            "erro": p.error,
        }), encoding="utf-8")
    except OSError:
        pass


def compute(recipe: Recipe, *, use_cache: bool = True) -> Preview:
    """Calcula (ou recupera do cache) a pré-visualização de uma receita."""
    if use_cache:
        guardado = load_cached(recipe.key)
        if guardado is not None:
            return guardado

    texto = deck_mod.build_in_file(recipe.title,
                                   [s.as_dict() for s in recipe.build()])
    with tempfile.TemporaryDirectory(prefix="mos_previa_") as tmp:
        try:
            resultado = suprem.SupremRunner(texto, results_dir=Path(tmp)).execute()
        except Exception as exc:                 # noqa: BLE001 - vira recado
            p = Preview(key=recipe.key, error=str(exc).strip().splitlines()[0]
                        if str(exc).strip() else "falha ao executar")
            _store(p)
            return p

    pontos = resultado.profile()
    # Amostra: a tela inicial desenha um traço pequeno; 160 pontos bastam e
    # mantêm o cache leve.
    if len(pontos) > 160:
        passo = len(pontos) / 160
        pontos = [pontos[int(i * passo)] for i in range(160)]
    p = Preview(
        key=recipe.key,
        points=pontos,
        junctions=detect_junctions(pontos, min_mag=junction_threshold(pontos))
        if pontos else [],
        surface=abs(pontos[0][1]) if pontos else 0.0,
        layers=resultado.layers(),
    )
    _store(p)
    return p


def compute_all(recipes, *, use_cache: bool = True) -> dict[str, Preview]:
    """Pré-visualização de várias receitas, na ordem."""
    return {r.key: compute(r, use_cache=use_cache) for r in recipes}


def clear_cache() -> None:
    """Esquece as pré-visualizações (usado quando o motor muda)."""
    for f in cache_dir().glob("*.json"):
        try:
            f.unlink()
        except OSError:
            pass
