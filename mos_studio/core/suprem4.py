"""Orquestração do SUPREM-IV.GS nativo (binário único, 64 bits).

Diferenças de fundo em relação ao :mod:`mos_studio.core.suprem` (SUPREM-III),
que explicam por que esta é uma camada separada e não um parâmetro daquela:

* **Um binário, não três.** Não há ``setup`` → ``genii`` → ``sup3``: o
  ``suprem`` lê o deck e resolve. Os "estágios" que a interface mostra aqui
  são os cartões do deck, extraídos da saída do motor.
* **A saída é a saída padrão.** O SUPREM-III gravava ``OUTPUT.OUT``; o
  SUPREM-IV escreve as tabelas do ``print.1d`` em stdout. Gravamos esse texto
  como ``SAIDA.TXT`` para que a pasta de resultados continue auditável.
* **Os arquivos de dados vêm por ambiente.** ``SUP4KEYFILE``, ``SUP4MODELRC``,
  ``SUP4IMPDATA`` e ``SUP4MANDIR`` sobrepõem os caminhos compilados no
  binário (ver ``main.c``), e é assim que apontamos para ``suprem4-run/data``
  sem recompilar.

Duas precauções que não são óbvias lendo só a documentação do motor:

**HOME aponta para o diretório de trabalho.** O ``main.c`` faz
``do_source("$HOME/.supremrc")`` e ``do_source("./.supremrc")`` antes do deck.
Um ``~/.supremrc`` do usuário mudaria silenciosamente os coeficientes de toda
simulação, e o resultado deixaria de ser reproduzível. Como o diretório de
trabalho é temporário e vazio, redirecionar ``HOME`` para lá neutraliza os
dois. (De quebra evita o ``strcpy`` para um buffer de 80 bytes que o
``main.c`` faz com ``$HOME`` sem medir o tamanho.)

**Código de saída não é diagnóstico.** O ``suprem`` termina com 0 mesmo
quando recusa cartões: os erros vão para stderr e a execução segue. Por isso
:func:`engine_errors` lê a saída em busca das mensagens do parser, em vez de
confiar no ``returncode``.
"""

from __future__ import annotations

import datetime
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import paths
from .deck4 import deck_title, ensure_profile_print, strip_plot
from .parsers import (parse_print_1d_layers, parse_print_1d_oxide,
                      parse_print_1d_profile)

#: Nome do arquivo com a saída do motor dentro da pasta de resultados.
OUTPUT_NAME = "SAIDA.TXT"

#: Nome do deck gravado na pasta de resultados.
INPUT_NAME = "deck.in"

_TIMEOUT = 900

#: Mensagens com que o motor recusa um deck. Ele não altera o código de saída
#: quando isso acontece, então é por aqui que a falha é detectada.
_ERROR_PATTERNS = (
    re.compile(r"errors? detected on command input", re.IGNORECASE),
    re.compile(r"unable to read or open", re.IGNORECASE),
    re.compile(r"where is the unformatted key file", re.IGNORECASE),
    re.compile(r"grammar rule violated", re.IGNORECASE),
    re.compile(r"string not allowed in expression", re.IGNORECASE),
    re.compile(r"\bpanic\b", re.IGNORECASE),
    re.compile(r"mesh i/o error", re.IGNORECASE),
    re.compile(r"parameter \S+ does not exist", re.IGNORECASE),
    # Uma tag de malha errada NÃO emite "errors detected": o motor segue com
    # a região não criada e o resultado sai vazio sem explicação.
    re.compile(r"no such [xyz] tag", re.IGNORECASE),
)

#: Comandos embutidos do shell do motor (``shell/lex.c``), que não são cartões
#: mas são entrada válida.
_BUILTINS = frozenset((
    "quit", "exit", "bye", "logout", "end", "source", "for", "foreach",
    "undef", "define", "set", "unset", "cd", "help",
))

#: Abreviações que os exemplos de fábrica usam e o parser aceita por prefixo.
#: O motor casa cartões por prefixo único; estas são as que aparecem no fonte.
_ALIASES = {
    "bound": "boundary", "struct": "structure", "meth": "method",
    "init": "initialize", "sel": "select", "depo": "deposit",
    "impl": "implant", "diff": "diffuse", "reg": "region",
}


def known_cards(run_dir: Path | None = None) -> frozenset[str]:
    """Cartões que este motor aceita, lidos de ``data/suprem.key``.

    Ler do arquivo de chaves em vez de manter uma lista aqui é o que mantém a
    verificação honesta: é exatamente o mesmo arquivo que o motor carrega, de
    modo que a lista não pode divergir do binário instalado.
    """
    rd = Path(run_dir) if run_dir else find_run_dir()
    if rd is None:
        return frozenset()
    chave = rd / "data" / "suprem.key"
    try:
        texto = chave.read_text(encoding="latin1", errors="replace")
    except OSError:
        return frozenset()
    return frozenset(re.findall(r"^card\s+([A-Za-z0-9._]+)\s*;",
                                texto, re.MULTILINE))


def unknown_cards(deck: str, run_dir: Path | None = None) -> list[str]:
    """Cabeçalhos de linha que o motor não reconhece como cartão.

    Existe por um motivo de segurança concreto: o shell do SUPREM-IV entrega
    ao ``/bin/sh`` do sistema qualquer comando que não seja cartão nem
    embutido — é um shell, com ``cd`` e ``source``. Um deck importado de
    fora, ou um erro de digitação, portanto **executa** em vez de falhar. Com
    esta verificação antes de rodar, isso vira uma mensagem de erro.

    Devolve lista vazia quando não há como verificar (motor ausente), para
    não bloquear a execução por falta da tabela.
    """
    cartoes = known_cards(run_dir)
    if not cartoes:
        return []
    validos = cartoes | _BUILTINS
    desconhecidos: list[str] = []
    for linha in deck.splitlines():
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        # O motor separa comandos por ';' e '&'; o '+' é continuação de linha.
        for pedaco in re.split(r"[;&]", s):
            pedaco = pedaco.strip()
            if not pedaco or pedaco.startswith(("#", "+")):
                continue
            # O '%' é descartado pelo lexer ("nobody wants to see percent
            # signs", shell/lex.c): serve para marcar comandos dentro de uma
            # string multilinha, como no movie= do exam3.
            cabeca = re.split(r"[\s=]", pedaco.lstrip("%"), maxsplit=1)[0].lower()
            cabeca = _ALIASES.get(cabeca, cabeca)
            if cabeca in validos:
                continue
            # Casamento por prefixo, como o parser do motor faz.
            if any(c.startswith(cabeca) for c in validos):
                continue
            if cabeca not in desconhecidos:
                desconhecidos.append(cabeca)
    return desconhecidos


class Cancelled(Exception):
    """Levantada quando o usuário interrompe a execução."""


@dataclass
class RunResult:
    """O que uma execução produziu.

    Mantém a forma do :class:`mos_studio.core.suprem.RunResult` de propósito —
    a interface e :mod:`mos_studio.core.workspace` consomem os dois sem saber
    qual motor rodou.
    """

    deck: str
    files: dict[str, dict] = field(default_factory=dict)
    out_dir: Path | None = None
    elapsed: float = 0.0
    stages: list[str] = field(default_factory=list)
    engine: str = "SUPREM-IV.GS"

    def raw(self) -> str:
        """Texto cru da saída do motor."""
        return (self.files.get(OUTPUT_NAME) or {}).get("raw") or ""

    def profile(self) -> list[tuple[float, float]]:
        """Perfil ``(profundidade_µm, concentração)`` no silício."""
        dados = (self.files.get(OUTPUT_NAME) or {}).get("data")
        return dados or []

    def profile_source(self) -> str:
        return OUTPUT_NAME if self.profile() else ""

    def layers(self) -> list[tuple[str, float]]:
        """Camadas, se o deck pediu ``print.1d layers``."""
        return parse_print_1d_layers(self.raw())

    def oxide_thickness(self) -> float | None:
        """Espessura total de óxido em µm, ou ``None`` se o deck não listou."""
        return parse_print_1d_oxide(self.raw())


def find_run_dir() -> Path | None:
    """Localiza a pasta do SUPREM-IV construída por ``build_suprem4.sh``."""
    for c in paths.SUPREM4_DIRS:
        if (c / "bin" / ("suprem" + paths.EXE)).exists():
            return c
    return None


def check_engine(run_dir: Path | None) -> list[str]:
    """Lista os problemas que impedem rodar (vazia = o motor está pronto)."""
    problems: list[str] = []
    if run_dir is None or not Path(run_dir).exists():
        return ["SUPREM-IV não encontrado (rode ./build_suprem4.sh)"]
    run_dir = Path(run_dir)
    binario = run_dir / "bin" / ("suprem" + paths.EXE)
    if not binario.exists():
        problems.append("binário ausente: bin/suprem")
    elif not paths.IS_WIN and not os.access(binario, os.X_OK):
        problems.append("sem permissão de execução: bin/suprem")
    for nome in ("suprem.uk", "modelrc", "sup4gs.imp"):
        arquivo = run_dir / "data" / nome
        if not arquivo.exists():
            problems.append(f"arquivo de dados ausente: data/{nome}")
        elif arquivo.stat().st_size == 0:
            problems.append(f"arquivo de dados vazio: data/{nome}")
    return problems


def available() -> bool:
    """``True`` se o SUPREM-IV está instalado e utilizável."""
    return not check_engine(find_run_dir())


def engine_errors(output: str) -> list[str]:
    """Mensagens de recusa encontradas na saída do motor.

    O ``suprem`` sai com 0 mesmo recusando cartões, então é esta função — e
    não o código de saída — que decide se a execução vale.
    """
    achados: list[str] = []
    for linha in (output or "").splitlines():
        s = linha.strip()
        if not s:
            continue
        if any(p.search(s) for p in _ERROR_PATTERNS) and s not in achados:
            achados.append(s)
    return achados


def _environment(run_dir: Path, work: Path) -> dict[str, str]:
    """Ambiente de execução: arquivos de dados e HOME isolado.

    Ver a nota sobre ``.supremrc`` no topo do módulo: o ``HOME`` apontando
    para o diretório de trabalho é o que torna a execução reproduzível.
    """
    env = dict(os.environ)
    data = run_dir / "data"
    env["SUP4KEYFILE"] = str(data / "suprem.uk")
    env["SUP4MODELRC"] = str(data / "modelrc")
    env["SUP4IMPDATA"] = str(data / "sup4gs.imp")
    env["SUP4MANDIR"] = str(run_dir / "help")
    env["HOME"] = str(work)
    return env


def _safe_dirname(title: str) -> str:
    """Transforma o título do deck em nome de pasta."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title)[:40].strip("_") or "simulacao"


def _stages_from(deck: str) -> list[str]:
    """Rótulos de progresso a partir dos cartões do deck.

    Como o motor é um processo só, o que a interface pode mostrar é o avanço
    pelos cartões — e é o próprio deck que os enumera.
    """
    nomes = {"init": "substrato", "diffuse": "difusão", "implant": "implante",
             "deposit": "deposição", "etch": "corrosão", "print.1d": "tabela",
             "structure": "estrutura"}
    saida: list[str] = []
    for linha in deck.splitlines():
        cabeca = linha.strip().split(" ")[0].lower()
        rotulo = nomes.get(cabeca)
        if rotulo:
            saida.append(rotulo)
    return saida


class Suprem4Runner:
    """Executa um deck no SUPREM-IV nativo, com cancelamento.

    Mesma interface do :class:`mos_studio.core.suprem.SupremRunner`::

        runner = Suprem4Runner(deck)
        result = runner.execute(on_stage=print)

    ``cancel()`` pode ser chamado de outra thread.
    """

    def __init__(self, deck: str, run_dir: Path | None = None,
                 results_dir: Path | None = None, timeout: int = _TIMEOUT) -> None:
        self.deck_original = deck
        self.run_dir = Path(run_dir) if run_dir else find_run_dir()
        self.results_dir = Path(results_dir) if results_dir else None
        self.timeout = timeout
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._cancelled = False

    # ── cancelamento ──────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Interrompe a execução (seguro de chamar de outra thread)."""
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def _check_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled()

    # ── execução ──────────────────────────────────────────────────────────

    def execute(self, on_stage: Callable[[str], None] | None = None) -> RunResult:
        """Roda o deck e devolve o resultado já lido.

        Levanta :class:`RuntimeError` quando o motor recusa o deck e
        :class:`Cancelled` quando o usuário interrompe.
        """
        problems = check_engine(self.run_dir)
        if problems:
            raise RuntimeError("SUPREM-IV indisponível:\n  - " + "\n  - ".join(problems))
        assert self.run_dir is not None
        run_dir = self.run_dir.resolve()
        binario = run_dir / "bin" / ("suprem" + paths.EXE)

        deck = ensure_profile_print(strip_plot(self.deck_original))
        # Antes de rodar: um cabeçalho desconhecido não falha no motor, vai
        # para o shell do sistema e executa. Ver unknown_cards().
        estranhos = unknown_cards(deck, run_dir)
        if estranhos:
            raise RuntimeError(
                "O deck tem comandos que não são cartões do SUPREM-IV: "
                + ", ".join(estranhos[:6])
                + ".\nO motor entregaria essas linhas ao shell do sistema em "
                  "vez de recusá-las, então a execução foi interrompida aqui.")
        etapas = _stages_from(deck)
        started = time.monotonic()
        work = Path(tempfile.mkdtemp(prefix="suprem4_"))
        log = [f"motor: {binario}"]
        try:
            self._check_cancelled()
            (work / INPUT_NAME).write_text(deck, encoding="ascii", errors="replace")
            env = _environment(run_dir, work)
            if on_stage:
                on_stage(etapas[0] if etapas else "simulando")

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.IS_WIN else 0
            proc = subprocess.Popen(
                [str(binario), INPUT_NAME],
                cwd=str(work), env=env,
                stdin=subprocess.DEVNULL,       # headless: nunca espera teclado
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=creationflags)
            with self._lock:
                self._proc = proc
            try:
                bruto, _ = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                bruto, _ = proc.communicate()
                raise
            finally:
                with self._lock:
                    self._proc = None
            self._check_cancelled()

            saida = bruto.decode("latin1", "replace")
            erros = engine_errors(saida)
            if erros:
                raise RuntimeError("O SUPREM-IV recusou o deck:\n  - "
                                   + "\n  - ".join(erros[:6]))
            if proc.returncode < 0:
                # O motor é C de 1993 e aceita sequências que o deixam ler
                # fora da estrutura: um ``etch done`` sem o ``etch start``
                # correspondente, por exemplo, termina em falha de
                # segmentação. Dizer isso é mais útil que mostrar o sinal.
                raise RuntimeError(
                    f"O SUPREM-IV abortou (sinal {-proc.returncode}). "
                    "Em geral é um cartão fora de sequência — uma corrosão "
                    "por coordenadas sem início, ou uma etapa antes da "
                    "malha estar definida.\n" + saida[-1200:])
            if proc.returncode != 0:
                raise RuntimeError(f"O SUPREM-IV terminou com código "
                                   f"{proc.returncode}:\n{saida[-1500:]}")

            if on_stage:
                on_stage(etapas[-1] if etapas else "lendo saída")

            dest = self._prepare_dest(deck)
            caminho = None
            if dest is not None:
                try:
                    (dest / OUTPUT_NAME).write_text(saida, encoding="utf-8",
                                                    errors="replace")
                    caminho = str(dest / OUTPUT_NAME)
                except OSError as exc:
                    log.append(f"falha ao salvar a saída: {exc}")
                # Arquivos que o deck tenha gravado (structure out=..., etc.).
                for f in sorted(work.iterdir()):
                    if f.name in (INPUT_NAME,) or not f.is_file():
                        continue
                    try:
                        shutil.copy2(str(f), str(dest / f.name))
                    except OSError:
                        pass
                log.append(f"saída: {dest}")
                try:
                    (dest / "execucao.log").write_text("\n".join(log), encoding="utf-8")
                except OSError:
                    pass

            files = {OUTPUT_NAME: {"data": parse_print_1d_profile(saida),
                                   "raw": saida, "path": caminho}}
            return RunResult(deck=deck, files=files, out_dir=dest,
                             elapsed=time.monotonic() - started, stages=etapas)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _prepare_dest(self, deck: str) -> Path | None:
        """Cria a pasta de destino ``resultados/<titulo>_<data-hora>``."""
        if self.results_dir is not None:
            base = self.results_dir
        else:
            from .workspace import runs_dir
            base = runs_dir()
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = base / f"{_safe_dirname(deck_title(deck))}_{stamp}"
        try:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / INPUT_NAME).write_text(deck, encoding="ascii", errors="replace")
        except OSError:
            return None
        return dest


def run_sync(deck: str, run_dir: Path | None = None, timeout: int = 600) -> str:
    """Roda um deck e devolve a saída crua, sem persistir em ``resultados/``.

    Variante enxuta para varreduras (a análise de oxidação roda dezenas de
    decks). Levanta :class:`RuntimeError` em caso de falha.
    """
    rd = Path(run_dir).resolve() if run_dir else find_run_dir()
    problems = check_engine(rd)
    if problems:
        raise RuntimeError("SUPREM-IV indisponível: " + "; ".join(problems))
    assert rd is not None
    work = Path(tempfile.mkdtemp(prefix="suprem4_ox_"))
    try:
        (work / INPUT_NAME).write_text(strip_plot(deck), encoding="ascii",
                                       errors="replace")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.IS_WIN else 0
        p = subprocess.run([str(rd / "bin" / ("suprem" + paths.EXE)), INPUT_NAME],
                           cwd=str(work), env=_environment(rd, work),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout,
                           creationflags=creationflags)
        saida = p.stdout.decode("latin1", "replace")
        erros = engine_errors(saida)
        if erros:
            raise RuntimeError("suprem4: " + "; ".join(erros[:3]))
        if p.returncode != 0:
            raise RuntimeError(f"suprem4 (código {p.returncode}): {saida[-300:]}")
        return saida
    finally:
        shutil.rmtree(work, ignore_errors=True)
