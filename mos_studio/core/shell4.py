"""Sessão interativa do SUPREM-IV, para a tela de Console.

O motor é um shell: lê cartões da entrada padrão e guarda estado entre eles —
variáveis do ``define``, a malha, a estrutura e as soluções. Um processo por
comando perderia tudo isso, então o Console mantém **um** processo vivo e
conversa com ele.

O problema é saber quando um comando terminou: o motor não emite prompt
(o ``modelrc`` começa com ``unset interactive``) e nada marca o fim da saída.
A solução é enquadrar cada comando com uma sentinela — manda-se o comando,
manda-se ``echo <sentinela>``, e lê-se até a sentinela aparecer.

Duas armadilhas conferidas contra o binário, e que explicam as escolhas aqui:

* **a sentinela tem de ser texto, não número.** ``echo 987654321`` imprime
  ``9.87654e+08``: o ``echo`` avalia o argumento como float e formata em
  ``%g``. Com uma sentinela numérica a leitura nunca casa e trava.
* **o ``echo`` reclama depois de imprimir.** Qualquer argumento que não seja
  um único token numérico faz sair ``string not allowed in expression`` ou
  ``grammar rule violated in expression`` *depois* do texto — inclusive para
  a sentinela. O texto saiu certo; a mensagem é espúria. Como ela vem depois
  da sentinela, cai no quadro do comando seguinte, e é por isso que cada
  resposta é limpa pela frente (:data:`NOISE`).
"""

from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .. import paths
from .suprem4 import (INPUT_NAME, _environment, check_engine,
                      find_run_dir, unknown_cards)

#: Token que fecha cada comando. Texto, e improvável num deck de verdade.
SENTINEL = "MOSSTUDIOFIMDOCOMANDO"

#: Mensagens que o ``echo`` emite depois de imprimir certo. Não são erro do
#: comando do usuário, e mostrá-las faria toda linha de ``echo`` parecer ter
#: falhado.
NOISE = (
    "string not allowed in expression",
    "grammar rule violated in expression",
)

#: Linhas do banner, que só interessam na primeira resposta.
BANNER = ("SUPREM-IV.GS", "Stanford University", "University of Florida",
          "Reading Models...")

#: Segundos de espera por uma resposta antes de desistir. Um ``diffuse`` numa
#: malha grande leva minutos; o Console mostra o progresso enquanto espera.
DEFAULT_TIMEOUT = 600.0

#: Comandos que encerram o motor. Mandá-los pela sessão deixaria o processo
#: morto e o Console mudo, então o :class:`Shell4` os trata como "reiniciar".
QUIT_COMMANDS = ("quit", "exit", "stop")


def is_quit(command: str) -> bool:
    """``True`` se o comando encerraria o motor."""
    primeiro = command.strip().split()[0].lower() if command.strip() else ""
    return any(primeiro and c.startswith(primeiro) and len(primeiro) >= 3
               for c in QUIT_COMMANDS)


def clean(text: str) -> str:
    """Remove banner e o ruído do ``echo`` de uma resposta."""
    linhas = []
    for linha in text.splitlines():
        s = linha.strip()
        if not s and (not linhas or not linhas[-1].strip()):
            continue                    # colapsa as linhas vazias do ruído
        if any(n in s for n in NOISE) or any(b in s for b in BANNER):
            continue
        linhas.append(linha.rstrip())
    while linhas and not linhas[-1].strip():
        linhas.pop()
    return "\n".join(linhas)


@dataclass
class Reply:
    """A resposta a um comando."""

    command: str
    text: str = ""
    #: Mensagens que são erro de verdade, já separadas do ruído.
    errors: list[str] = field(default_factory=list)
    #: ``True`` quando o motor morreu durante o comando.
    crashed: bool = False
    #: ``True`` quando a espera estourou e a resposta pode estar incompleta.
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors and not self.crashed and not self.timed_out


class Shell4:
    """Um processo do SUPREM-IV vivo, alimentado comando por comando.

    A pasta de trabalho é temporária e é onde o motor grava estruturas e lê
    arquivos do ``source``. Fechar a sessão encerra o processo; a pasta fica,
    para o usuário poder abrir o que gravou.
    """

    def __init__(self, run_dir: Path | None = None,
                 work_dir: Path | None = None):
        self.run_dir = Path(run_dir).resolve() if run_dir else find_run_dir()
        problemas = check_engine(self.run_dir)
        if problemas:
            raise RuntimeError("SUPREM-IV indisponível: "
                               + "; ".join(problemas))
        assert self.run_dir is not None
        self.work_dir = (Path(work_dir) if work_dir
                         else Path(tempfile.mkdtemp(prefix="suprem4_shell_")))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._proc: subprocess.Popen | None = None
        self._fila: queue.Queue[bytes | None] = queue.Queue()
        self._leitor: threading.Thread | None = None
        #: Histórico do que foi aceito, para reconstruir a sessão num reinício.
        self.history: list[str] = []

    # ── ciclo de vida ────────────────────────────────────────────────────

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> Reply:
        """Sobe o processo e devolve o banner como primeira resposta."""
        self.close()
        assert self.run_dir is not None
        exe = self.run_dir / "bin" / ("suprem" + paths.EXE)
        creationflags = (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                         if paths.IS_WIN else 0)
        self._proc = subprocess.Popen(
            [str(exe)], cwd=str(self.work_dir),
            env=_environment(self.run_dir, self.work_dir),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=0, creationflags=creationflags)
        self._fila = queue.Queue()
        self._leitor = threading.Thread(target=self._ler, daemon=True)
        self._leitor.start()
        # Um echo sozinho serve de sincronização: a resposta traz o banner.
        return self._trocar("", timeout=30.0)

    def close(self) -> None:
        """Encerra o processo, sem esperar resposta."""
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin is not None:
                proc.stdin.write(b"quit\n")
                proc.stdin.flush()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        except OSError:
            pass
        for canal in (proc.stdin, proc.stdout):
            try:
                if canal is not None:
                    canal.close()
            except OSError:
                pass

    def restart(self, replay: bool = False) -> Reply:
        """Sobe o motor de novo, opcionalmente repetindo o histórico aceito."""
        anterior = list(self.history)
        self.history.clear()
        r = self.start()
        if replay:
            for cmd in anterior:
                self.send(cmd)
        return r

    # ── conversa ─────────────────────────────────────────────────────────

    def send(self, command: str,
             timeout: float = DEFAULT_TIMEOUT) -> Reply:
        """Manda um comando e espera a resposta.

        ``quit`` e companhia não são repassados: encerrariam o motor e
        deixariam o Console mudo. A resposta explica como reiniciar.
        """
        cmd = command.strip()
        if not cmd:
            return Reply(command=command)
        if is_quit(cmd):
            return Reply(command=command,
                         text="O motor continua aberto nesta sessão. Para "
                              "zerar o estado, reinicie a sessão do Console.")
        # O shell do SUPREM-IV entrega ao /bin/sh o que não reconhece como
        # cartão nem embutido. Conferido nesta compilação: um
        # ``cartao.que.nao.existe`` digitado no Console vira "comando não
        # encontrado" do bash — ou seja, um deck colado de fora **executa**.
        # Barrar aqui transforma isso em mensagem de erro.
        desconhecidos = unknown_cards(cmd, self.run_dir)
        if desconhecidos:
            return Reply(
                command=command,
                errors=[f"“{d}” não é um cartão do SUPREM-IV"
                        for d in desconhecidos],
                text="O shell do motor entregaria esta linha ao sistema "
                     "operacional em vez de recusá-la, então o Console não a "
                     "manda. Use “help” para ver os cartões.")
        if not self.alive:
            r = self.start()
            if not self.alive:
                r.crashed = True
                return r
        r = self._trocar(cmd, timeout=timeout)
        if r.ok:
            self.history.append(cmd)
        return r

    def _trocar(self, cmd: str, timeout: float) -> Reply:
        """Escreve o comando com a sentinela e lê até ela aparecer."""
        from .suprem4 import engine_errors

        assert self._proc is not None and self._proc.stdin is not None
        bloco = (cmd + "\n" if cmd else "") + f"echo {SENTINEL}\n"
        try:
            self._proc.stdin.write(bloco.encode("ascii", "replace"))
            self._proc.stdin.flush()
        except OSError:
            return Reply(command=cmd, crashed=True,
                         text="O motor não aceitou mais entrada.")
        bruto = ""
        morreu = estourou = False
        while SENTINEL not in bruto:
            try:
                pedaco = self._fila.get(timeout=timeout)
            except queue.Empty:
                estourou = True
                break
            if pedaco is None:
                morreu = True
                break
            bruto += pedaco.decode("latin1", "replace")
        texto = clean(bruto.split(SENTINEL)[0])
        return Reply(command=cmd, text=texto, errors=engine_errors(texto),
                     crashed=morreu, timed_out=estourou)

    def _ler(self) -> None:
        """Fio que drena a saída do motor para a fila."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while True:
                pedaco = proc.stdout.read(1)
                if not pedaco:
                    break
                self._fila.put(pedaco)
        except (OSError, ValueError):
            pass
        finally:
            self._fila.put(None)

    # ── apoio à tela ─────────────────────────────────────────────────────

    def source(self, deck: str,
               timeout: float = DEFAULT_TIMEOUT) -> Reply:
        """Grava um deck na pasta de trabalho e manda o motor lê-lo.

        É como o Console roda a receita inteira sem perder a sessão: o
        ``source`` é o próprio mecanismo do motor para isso.
        """
        arquivo = self.work_dir / INPUT_NAME
        arquivo.write_text(deck, encoding="ascii", errors="replace")
        return self.send(f"source {arquivo.name}", timeout=timeout)

    def help(self, card: str, timeout: float = 30.0) -> Reply:
        """Saída do ``help`` do motor para um cartão.

        É a documentação de dentro do binário: lista cada parâmetro com tipo,
        valor atual e unidade. Vale lembrar que ela repete a mentira do
        ``suprem.key`` e diz "degrees Kelvin" para o ``temp`` do ``diffuse``,
        que é em Celsius (``diffuse.c`` soma 273).
        """
        from . import keyfile

        nome = keyfile.resolve(card) or card.strip()
        return self.send(f"help {nome}", timeout=timeout)

    def __enter__(self) -> "Shell4":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
