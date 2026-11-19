"""Orquestração dos binários nativos do SUPREM-III (``setup`` → ``genii`` → ``sup3``).

A sequência, as dez variáveis de ambiente dos arquivos de dados e o ``S3prs0``
*relativo* vêm de ``suprem3.py`` sem mudança: o motor não lida bem com caminhos
absolutos para o arquivo de saída, e trocar isso faz a execução falhar de forma
difícil de diagnosticar. O que foi acrescentado é cancelamento — cada binário
roda em ``Popen`` para que a interface possa interromper a execução — e a
camada não conhece Qt.

O caminho DOSBox não foi migrado: os quatro binários são ELF x86-64 nativos
(ver ``docs/adr/0001``).
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
from .deck import ensure_profile_print, deck_title, strip_plot
from .parsers import parse_layers, parse_out_file

#: Nomes lógicos dos arquivos de dados que viram variáveis de ambiente.
DATA_FILES = ("S3cof0", "S3err0", "S3fky0", "S3uky0", "S3ibo0", "S3ibo1",
              "S3ibf0", "S3iph0", "S3ias0", "S3isb0")

#: Binários da cadeia, na ordem em que rodam.
BINARIES = ("setup", "genii", "sup3")

#: Arquivos de dados sem os quais o motor não foi inicializado.
REQUIRED_DATA = ("S3cof0", "S3uky0")

_TIMEOUT = 600


class Cancelled(Exception):
    """Levantada quando o usuário interrompe a execução."""


@dataclass
class RunResult:
    """O que uma execução produziu."""

    deck: str
    files: dict[str, dict] = field(default_factory=dict)
    out_dir: Path | None = None
    elapsed: float = 0.0
    stages: list[str] = field(default_factory=list)

    def profile(self) -> list[tuple[float, float]]:
        """Perfil de dopagem da primeira saída que tiver tabela de concentração."""
        for name in sorted(self.files):
            data = self.files[name].get("data") or []
            if data:
                return data
        return []

    def profile_source(self) -> str:
        """Nome do arquivo de onde veio o perfil."""
        for name in sorted(self.files):
            if self.files[name].get("data"):
                return name
        return ""

    def layers(self) -> list[tuple[str, float]]:
        """Camadas lidas de qualquer saída que traga a tabela de camadas."""
        for name in sorted(self.files):
            camadas = parse_layers(self.files[name].get("raw") or "")
            if camadas:
                return camadas
        return []


def find_run_dir() -> Path | None:
    """Localiza a pasta com os binários nativos do SUPREM-III, se houver."""
    for c in paths.SUPREM_RUN_DIRS:
        if (c / ("sup3" + paths.EXE)).exists() and (c / ("genii" + paths.EXE)).exists():
            return c
    return None


def check_engine(run_dir: Path | None) -> list[str]:
    """Lista os problemas que impedem rodar (vazia = o motor está pronto)."""
    problems: list[str] = []
    if run_dir is None or not Path(run_dir).exists():
        return ["binários nativos do SUPREM-III não encontrados"]
    run_dir = Path(run_dir)
    for b in BINARIES:
        p = run_dir / (b + paths.EXE)
        if not p.exists():
            problems.append(f"binário ausente: {b}{paths.EXE}")
        elif not paths.IS_WIN and not os.access(p, os.X_OK):
            problems.append(f"sem permissão de execução: {b}")
    for f in REQUIRED_DATA:
        if not (run_dir / f).exists():
            problems.append(f"coeficiente ausente: {f} (rode a inicialização)")
    return problems


def _environment(run_dir: Path, work: Path) -> dict[str, str]:
    """Ambiente de execução: os arquivos de dados e o ``S3prs0`` relativo.

    Os arquivos de dados são COPIADOS para a pasta de trabalho e passados pelo
    nome curto. O fonte guarda o nome do arquivo num ``character*80``
    (``opnfl-L.f``): um caminho absoluto mais longo que isso é truncado e o
    motor para com "ERROR # 33 — File system error #2 ... formatted
    specification file". Basta o programa estar numa pasta funda, ou o
    usuário do Windows ter um nome comprido
    (``C:\\Users\\<nome>\\AppData\\Local\\Programs\\MOS-Studio\\suprem-run\\S3fky0``
    já passa de 70 caracteres). São 276 KB por execução, e não vão para
    ``resultados/`` (só ``.OUT``/``.TXT``/``.LST`` vão).
    """
    env = dict(os.environ)
    for name in DATA_FILES:
        fp = run_dir / name
        if fp.exists():
            shutil.copyfile(fp, work / name)
            env[name] = name
    # IMPORTANTE: nome RELATIVO (cwd = pasta de trabalho), igual ao script
    # 'suprem' original. O motor nao lida bem com caminhos absolutos para o
    # arquivo de saida / S3prs0.
    env["S3prs0"] = "S3prs0"
    return env


def _safe_dirname(title: str) -> str:
    """Transforma o título do deck em nome de pasta."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title)[:40].strip("_") or "simulacao"


class SupremRunner:
    """Executa um deck no SUPREM-III nativo, com cancelamento.

    Uso típico (fora da thread da interface)::

        runner = SupremRunner(deck)
        result = runner.execute(on_stage=print)

    ``cancel()`` pode ser chamado de outra thread; o binário em curso é
    encerrado e :class:`Cancelled` é levantada em ``execute()``.
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

    def _spawn(self, work: Path, env: dict[str, str], binary: str,
               args: list[str]) -> subprocess.CompletedProcess:
        """Roda um binário da cadeia, registrando o processo para cancelamento."""
        self._check_cancelled()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.IS_WIN else 0
        proc = subprocess.Popen(
            [str(self.run_dir / (binary + paths.EXE))] + args,
            cwd=str(work), env=env,
            stdin=subprocess.DEVNULL,       # headless: nunca espera teclado
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=creationflags)
        with self._lock:
            self._proc = proc
        try:
            out, _ = proc.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            raise
        finally:
            with self._lock:
                self._proc = None
        self._check_cancelled()
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, b"")

    def execute(self, on_stage: Callable[[str], None] | None = None) -> RunResult:
        """Roda a cadeia completa e devolve o resultado já lido.

        Levanta :class:`RuntimeError` quando o motor recusa o deck (com o
        trecho final da mensagem do binário) e :class:`Cancelled` quando o
        usuário interrompe.
        """
        problems = check_engine(self.run_dir)
        if problems:
            raise RuntimeError("Motor nativo indisponível:\n  - "
                               + "\n  - ".join(problems))
        assert self.run_dir is not None
        run_dir = self.run_dir.resolve()

        deck = ensure_profile_print(strip_plot(self.deck_original))
        started = time.monotonic()
        work = Path(tempfile.mkdtemp(prefix="suprem_nat_"))
        log: list[str] = [f"run_dir: {run_dir}"]
        stages: list[str] = []
        try:
            (work / "INPUT.IN").write_text(deck, encoding="ascii", errors="replace")
            env = _environment(run_dir, work)
            out_name, inf_name = "OUTPUT.OUT", "RUNINFO.TXT"

            if on_stage:
                on_stage("setup")
            self._spawn(work, env, "setup", ["INPUT.IN", out_name])
            stages.append("setup")

            if on_stage:
                on_stage("genii")
            g = self._spawn(work, env, "genii", ["INPUT.IN", out_name, inf_name])
            if g.returncode != 0:
                raise RuntimeError("Erro no genii (leitor do deck):\n"
                                   + g.stdout.decode("latin1", "replace")[-1500:])
            stages.append("genii")

            if on_stage:
                on_stage("sup3")
            s = self._spawn(work, env, "sup3", [out_name, inf_name])
            if s.returncode != 0:
                raise RuntimeError("Erro no sup3 (simulador):\n"
                                   + s.stdout.decode("latin1", "replace")[-1500:])
            stages.append("sup3")

            dest = self._prepare_dest(deck)
            files: dict[str, dict] = {}
            for f in sorted(work.iterdir()):
                up = f.name.upper()
                if up in ("INPUT.IN", inf_name.upper()) or up.startswith("S3PRS0"):
                    continue
                if (up.endswith(".OUT") or up.endswith(".TXT") or up.endswith(".LST")) \
                        and f.is_file() and f.stat().st_size > 10:
                    raw = f.read_text(encoding="latin1", errors="replace")
                    saved = None
                    if dest is not None:
                        try:
                            shutil.copy2(str(f), str(dest / f.name))
                            saved = str(dest / f.name)
                        except OSError as exc:
                            log.append(f"falha ao salvar {f.name}: {exc}")
                    files[f.name] = {"data": parse_out_file(raw), "raw": raw,
                                     "path": saved}
            if dest is not None:
                log.append(f"saída: {dest}")
                try:
                    (dest / "execucao.log").write_text("\n".join(log), encoding="utf-8")
                except OSError:
                    pass
            return RunResult(deck=deck, files=files, out_dir=dest,
                             elapsed=time.monotonic() - started, stages=stages)
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
            (dest / "INPUT.IN").write_text(deck, encoding="ascii", errors="replace")
        except OSError:
            return None
        return dest


def run_sync(deck: str, run_dir: Path | None = None, timeout: int = 300) -> str:
    """Roda ``setup`` → ``genii`` → ``sup3`` e devolve o texto do OUTPUT.

    Variante síncrona e enxuta, sem persistir em ``resultados/`` — é o que a
    análise de oxidação usa para varrer muitos tempos. Levanta
    :class:`RuntimeError` em caso de falha.
    """
    rd = Path(run_dir).resolve() if run_dir else find_run_dir()
    problems = check_engine(rd)
    if problems:
        raise RuntimeError("Motor nativo indisponível: " + "; ".join(problems))
    assert rd is not None
    work = Path(tempfile.mkdtemp(prefix="suprem_ox_"))
    try:
        (work / "INPUT.IN").write_text(strip_plot(deck), encoding="ascii",
                                       errors="replace")
        env = _environment(rd, work)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.IS_WIN else 0

        def run(binary: str, args: list[str]):
            return subprocess.run([str(rd / (binary + paths.EXE))] + args,
                                  cwd=str(work), env=env,
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout,
                                  creationflags=creationflags)

        run("setup", ["INPUT.IN", "O.OUT"])
        g = run("genii", ["INPUT.IN", "O.OUT", "I.TXT"])
        if g.returncode != 0:
            raise RuntimeError("genii: " + g.stdout.decode("latin1", "replace")[-300:])
        s = run("sup3", ["O.OUT", "I.TXT"])
        if s.returncode != 0:
            raise RuntimeError("sup3: " + s.stdout.decode("latin1", "replace")[-300:])
        return (work / "O.OUT").read_text(encoding="latin1", errors="replace")
    finally:
        shutil.rmtree(work, ignore_errors=True)
