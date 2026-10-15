"""Evolução do perfil ao longo do processo, etapa por etapa.

A tela de Resultados do arquivo de design deixa o usuário andar pelas etapas e
ver o perfil depois de cada uma, além de separar as espécies (boro, fósforo) do
líquido. Isso não sai do deck do usuário, que imprime o perfil onde ele mandou.

Sai de um **deck derivado**: :func:`mos_studio.core.deck.build_profile_deck`
insere um PRINT depois de cada etapa de processo e devolve o plano — a lista
ordenada de (etapa, grandeza) que corresponde a cada bloco da saída. Rodamos
esse deck além do deck do usuário (custa poucos milissegundos) e guardamos o
resultado ao lado da execução.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .deck import build_profile_deck
from .parsers import parse_suprem_profiles

ARQUIVO = "evolucao.json"

#: Rótulos em português das grandezas que o deck derivado imprime.
QUANTITY_LABELS = {"Net": "Líquido", "Boron": "Boro", "Phosphorus": "Fósforo",
                   "Arsenic": "Arsênio", "Antimony": "Antimônio"}


@dataclass
class Snapshot:
    """O perfil de uma grandeza depois de uma etapa."""

    step: int                  # 1-based, na ordem das etapas de processo
    step_label: str
    quantity: str              # "Net", "Boron", …
    points: list[tuple[float, float]] = field(default_factory=list)

    @property
    def quantity_label(self) -> str:
        return QUANTITY_LABELS.get(self.quantity, self.quantity)


@dataclass
class Evolution:
    """Todos os instantâneos de uma execução."""

    snapshots: list[Snapshot] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.snapshots)

    def steps(self) -> list[tuple[int, str]]:
        """``(número, rótulo)`` de cada etapa, na ordem, sem repetir."""
        vistos: dict[int, str] = {}
        for s in self.snapshots:
            vistos.setdefault(s.step, s.step_label)
        return sorted(vistos.items())

    def at(self, step: int) -> list[Snapshot]:
        """Instantâneos de uma etapa (líquido primeiro, depois as espécies)."""
        itens = [s for s in self.snapshots if s.step == step]
        itens.sort(key=lambda s: (s.quantity != "Net", s.quantity))
        return itens

    def net_series(self) -> list[Snapshot]:
        """O perfil líquido de cada etapa, para a vista de evolução."""
        return [s for s in self.snapshots if s.quantity == "Net"]

    def last_step(self) -> int:
        passos = self.steps()
        return passos[-1][0] if passos else 0

    # ── disco ─────────────────────────────────────────────────────────────

    def save(self, pasta: Path) -> None:
        try:
            (Path(pasta) / ARQUIVO).write_text(json.dumps({
                "erro": self.error,
                "instantaneos": [
                    {"etapa": s.step, "rotulo": s.step_label,
                     "grandeza": s.quantity,
                     "pontos": [list(p) for p in s.points]}
                    for s in self.snapshots],
            }), encoding="utf-8")
        except OSError:
            pass

    @classmethod
    def load(cls, pasta: Path) -> "Evolution | None":
        arquivo = Path(pasta) / ARQUIVO
        if not arquivo.exists():
            return None
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return cls(
            error=dados.get("erro", ""),
            snapshots=[Snapshot(step=s["etapa"], step_label=s["rotulo"],
                                quantity=s["grandeza"],
                                points=[tuple(p) for p in s["pontos"]])
                       for s in dados.get("instantaneos", [])])


def _parse_step_number(label: str) -> int:
    """``"3. Difusão PHOSPHOR"`` → ``3``."""
    numero = label.split(".", 1)[0].strip()
    return int(numero) if numero.isdigit() else 0


def _pretty(label: str) -> str:
    """Tira o número do rótulo e traduz o ambiente, se houver."""
    from .recipe import AMBIENT_LABELS, DOPANT_LABELS
    corpo = label.split(".", 1)[1].strip() if "." in label else label
    for cru, bonito in {**AMBIENT_LABELS, **DOPANT_LABELS}.items():
        if corpo.endswith(" " + cru):
            limpo = bonito.replace(" (fonte gasosa)", "").replace(" (inerte)", "")
            return corpo[: -len(cru) - 1] + " " + limpo
    return corpo


def _full_resolution(deck: str) -> str:
    """Pede ao motor a tabela inteira numa página só.

    Sem ``LINES/PA``, o SUPREM-III pagina a saída e imprime menos pontos. O
    deck derivado é nosso, então podemos pedir resolução cheia sem mexer no
    gerador — que é compartilhado com o deck do usuário.
    """
    linhas = []
    for linha in deck.replace("\r\n", "\n").split("\n"):
        if linha.upper().startswith("PRINT") and "LINES/PA" not in linha.upper():
            linha = f"{linha} LINES/PA=1000"
        linhas.append(linha)
    return "\r\n".join(linhas)


def _merge_pages(blocos, esperados: int):
    """Remonta tabelas que o motor quebrou em várias páginas.

    O SUPREM-III repete o cabeçalho ``depth concentration`` a cada página, e o
    leitor devolve um bloco por cabeçalho. Uma tabela continuada começa numa
    profundidade **maior** que a última da anterior; uma tabela nova recomeça
    do zero. É esse degrau que usamos para juntar as páginas.

    Se mesmo assim a contagem não bater com o plano, devolvemos os blocos como
    vieram: é melhor um gráfico a menos que um gráfico com o rótulo errado.
    """
    if len(blocos) <= esperados:
        return blocos
    juntados: list[tuple[list[float], list[float]]] = []
    for profundidade, concentracao in blocos:
        if not profundidade:
            continue
        if juntados and profundidade[0] > juntados[-1][0][-1]:
            juntados[-1][0].extend(profundidade)
            juntados[-1][1].extend(concentracao)
        else:
            juntados.append((list(profundidade), list(concentracao)))
    return juntados if len(juntados) == esperados else blocos


def compute(title: str, steps: list[dict], run_dir=None,
            timeout: int = 300) -> Evolution:
    """Roda o deck derivado e devolve a evolução do perfil.

    ``steps`` é a lista de etapas no formato do gerador de deck.
    """
    from .suprem import run_sync

    texto, plano = build_profile_deck(title, steps)
    if not plano:
        return Evolution(error="a receita não tem etapas de processo")
    texto = _full_resolution(texto)
    try:
        saida = run_sync(texto, run_dir=run_dir, timeout=timeout)
    except Exception as exc:                     # noqa: BLE001 - vira recado
        primeira = str(exc).strip().splitlines()
        return Evolution(error=primeira[0] if primeira else "falha ao executar")

    blocos = _merge_pages(parse_suprem_profiles(saida), len(plano))
    instantaneos: list[Snapshot] = []
    for (rotulo, grandeza), (profundidade, concentracao) in zip(plano, blocos):
        pontos = list(zip(profundidade, concentracao))
        if not pontos:
            continue
        instantaneos.append(Snapshot(step=_parse_step_number(rotulo),
                                     step_label=_pretty(rotulo),
                                     quantity=grandeza, points=pontos))
    if not instantaneos:
        return Evolution(error="a saída não trouxe nenhuma tabela de perfil")
    if len(instantaneos) < len(plano):
        return Evolution(snapshots=instantaneos,
                         error="a saída trouxe menos tabelas que o esperado")
    return Evolution(snapshots=instantaneos)
