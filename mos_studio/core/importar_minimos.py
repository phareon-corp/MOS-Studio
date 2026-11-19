"""Instala o MINIMOS 6.1 a partir do ``.zip`` oficial da TU Wien.

POR QUE O USUÁRIO TRAZ O ZIP
----------------------------
O SUPREM-III e o SUPREM-IV têm licença de Stanford que permite copiar e
distribuir; o instalador os baixa e compila sozinho. O MINIMOS não: a TU
Wien só o entrega a usuários registrados (de graça, para ensino e pesquisa),
e a licença proíbe repassá-lo a terceiros. Então o MOS-Studio não o traz
nem o baixa — quem tem o ``minimoswin6.1.zip`` (do portal da TU Wien ou da
disciplina) aponta para ele e o programa faz o resto:

* **Windows** — o zip já traz o ``bin/mm_pl.exe`` compilado em 1999 (só
  depende do KERNEL32). Basta copiá-lo, com o ``stack.rul`` e os exemplos,
  para ``minimos-run/``.
* **Linux** — o ``.exe`` não serve; o fonte (``pl/`` e ``stdalone/``) é
  compilado pelo ``build_minimos.sh`` com o gfortran.

Usado pelo ``instalar.sh``, por ``mos-studio --instalar-minimos ZIP`` e pelo
botão "Instalar MINIMOS…" da tela de Dispositivo.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from .. import paths

#: Para onde o motor vai. É a primeira pasta de ``paths.MINIMOS_DIRS``.
DESTINO = paths.APP_ROOT / "minimos-run"

#: Onde o portal da TU Wien entrega o zip (registro gratuito).
PORTAL = "https://www.iue.tuwien.ac.at/software/download/download-area"

#: Membros que identificam o zip certo, relativos à raiz do pacote.
NECESSARIOS = ("bin/mm_pl.exe", "bin/stack.rul", "pl/driver.F", "stdalone/sol.c")


class ErroMinimos(Exception):
    """O zip não serve, ou a instalação não terminou. A mensagem vai à tela."""


def _prefixo(nomes: list[str]) -> str:
    """Pasta dentro do zip onde o pacote começa (``""`` se for a raiz).

    O zip oficial tem ``bin/`` na raiz, mas um zip refeito à mão costuma
    embrulhar tudo em ``minimoswin6_1/``. Os dois são aceitos.
    """
    for n in nomes:
        if n.replace("\\", "/").lower().endswith("bin/mm_pl.exe"):
            return n[: len(n) - len("bin/mm_pl.exe")]
    raise ErroMinimos("Este zip não tem o bin/mm_pl.exe do MINIMOS 6.1. "
                      "Use o minimoswin6.1.zip da TU Wien.")


def conferir(zip_path: Path | str) -> str:
    """Confere o zip e devolve o prefixo; levanta :class:`ErroMinimos`."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise ErroMinimos(f"Arquivo não encontrado: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path) as z:
            nomes = z.namelist()
    except zipfile.BadZipFile as exc:
        raise ErroMinimos(f"Não é um zip válido: {zip_path.name}") from exc
    prefixo = _prefixo(nomes)
    presentes = {n.replace("\\", "/") for n in nomes}
    faltam = [m for m in NECESSARIOS if prefixo + m not in presentes]
    if faltam:
        raise ErroMinimos("O zip está incompleto — faltam: " + ", ".join(faltam))
    return prefixo


def _extrair(z: zipfile.ZipFile, membros: list[str], destino: Path) -> None:
    """Extrai recusando caminhos que escapem do destino (zip slip)."""
    raiz = destino.resolve()
    for m in membros:
        alvo = (destino / m).resolve()
        if raiz != alvo and raiz not in alvo.parents:
            raise ErroMinimos(f"Caminho suspeito dentro do zip: {m}")
    z.extractall(destino, membros)


def _trocar(nova: Path) -> Path:
    """Põe ``nova`` no lugar de ``minimos-run/`` (a antiga só sai no fim)."""
    velha = DESTINO.with_name(DESTINO.name + ".antigo")
    shutil.rmtree(velha, ignore_errors=True)
    if DESTINO.exists():
        DESTINO.rename(velha)
    shutil.move(str(nova), str(DESTINO))
    shutil.rmtree(velha, ignore_errors=True)
    return DESTINO


def importar(zip_path: Path | str,
             log: Callable[[str], None] | None = None) -> Path:
    """Instala o MINIMOS do zip em ``minimos-run/`` e devolve a pasta."""
    log = log or (lambda _m: None)
    zip_path = Path(zip_path)
    prefixo = conferir(zip_path)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="minimos-zip-",
                                     dir=DESTINO.parent) as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(zip_path) as z:
            nomes = [n for n in z.namelist() if n.startswith(prefixo)]
            log(f"extraindo {zip_path.name}")
            _extrair(z, nomes, tmp / "zip")
        pacote = tmp / "zip" / prefixo
        nova = tmp / "minimos-run"

        if paths.IS_WIN:
            (nova / "examples").mkdir(parents=True)
            shutil.copy2(pacote / "bin" / "mm_pl.exe", nova / "mm_pl.exe")
            shutil.copy2(pacote / "bin" / "stack.rul", nova / "stack.rul")
            for inp in sorted((pacote / "examples").glob("*.inp")):
                shutil.copy2(inp, nova / "examples" / inp.name)
        else:
            script = paths.APP_ROOT / "build_minimos.sh"
            if not script.is_file():
                raise ErroMinimos(f"Falta o {script.name} ao lado do programa.")
            if shutil.which("gfortran") is None:
                raise ErroMinimos(
                    "O MINIMOS é compilado do fonte e precisa do gfortran. "
                    "Rode o ./instalar.sh, que instala o compilador, ou "
                    "instale-o pelo gerenciador de pacotes "
                    "(gcc-gfortran no Fedora, gfortran no Ubuntu/Debian).")
            log("compilando o MINIMOS (cerca de um minuto)")
            # O script escreve em $(pwd)/minimos-run; rodar dentro do tmp
            # deixa a pasta antiga intacta se a compilação falhar.
            r = subprocess.run(["bash", str(script), str(pacote)], cwd=tmp,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors="replace")
            if r.returncode != 0 or not (nova / "mm_pl").is_file():
                cauda = "\n".join(r.stdout.strip().splitlines()[-15:])
                raise ErroMinimos("A compilação do MINIMOS falhou:\n" + cauda)

        if not (nova / "stack.rul").is_file():
            shutil.copy2(pacote / "bin" / "stack.rul", nova / "stack.rul")
        destino = _trocar(nova)

    from .. import config
    if config.get("minimos_dir", ""):
        # Uma pasta escolhida antes passaria na frente da que acabou de
        # ser instalada (ver minimos.find_dir).
        config.set("minimos_dir", "")
    log(f"MINIMOS instalado em {destino}")
    return destino


def procurar_zip() -> Path | None:
    """O zip do MINIMOS nos lugares de sempre, se houver um.

    É o que deixa o ``instalar.sh`` compilar o MINIMOS sem perguntar nada a
    quem já baixou o zip para a pasta de downloads.
    """
    casa = Path.home()
    pastas = [paths.APP_ROOT, casa / "Downloads", casa / "Transferências",
              casa / "Desktop", casa / "Área de Trabalho", casa]
    for pasta in pastas:
        try:
            achados = sorted(pasta.glob("minimos*6*1*.zip"))
        except OSError:
            continue
        for z in achados:
            try:
                conferir(z)
            except ErroMinimos:
                continue
            return z
    return None
