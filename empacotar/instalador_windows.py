#!/usr/bin/env python3
"""Compila o instalador de Windows do MOS-Studio, rodando no Linux.

Resultado: ``windows_build/MOS-Studio-<versão>-instalador.exe``, um arquivo
só que a pessoa baixa, clica duas vezes e usa. Instala no perfil do usuário,
sem pedir senha de administrador, e aparece em "Aplicativos instalados" do
Windows com desinstalador próprio.

COMO ISSO É COMPILADO SEM UM WINDOWS
------------------------------------
O compilador do NSIS (``makensis.exe``) é um programa de Windows, mas roda
sem problema sob o wine — é como quase todo projeto livre gera instalador de
Windows a partir do Linux. O wine aqui não executa nada do MOS-Studio: só o
compilador, que lê o script e escreve o .exe. O instalador resultante é
testado no Windows de verdade, na máquina virtual
(``empacotar/testar_instalador.py``).

O NSIS não precisa estar instalado no sistema: a distribuição .zip oficial é
baixada para ``windows_build/cache`` e usada de lá, com o hash conferido.

Uso:
    ./empacotar/instalador_windows.py
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EMPACOTAR = RAIZ / "empacotar"
TRABALHO = RAIZ / "windows_build"
CACHE = TRABALHO / "cache"
PACOTE = TRABALHO / "MOS-Studio"

NSIS_VERSAO = "3.11"
NSIS_ZIP = f"nsis-{NSIS_VERSAO}.zip"
NSIS_URL = (f"https://downloads.sourceforge.net/project/nsis/"
            f"NSIS%203/{NSIS_VERSAO}/{NSIS_ZIP}")
NSIS_SHA = "c7d27f780ddb6cffb4730138cd1591e841f4b7edb155856901cdf5f214394fa1"


def passo(texto: str) -> None:
    print(f">> {texto}", flush=True)


def versao_do_projeto() -> str:
    for linha in (RAIZ / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        if linha.startswith("version"):
            return linha.split("=", 1)[1].strip().strip('"')
    return "2.0.0"


def preparar_nsis() -> Path:
    """Garante o NSIS no cache e devolve a pasta onde ele ficou."""
    destino = CACHE / f"nsis-{NSIS_VERSAO}"
    if (destino / "makensis.exe").exists():
        return destino

    CACHE.mkdir(parents=True, exist_ok=True)
    arquivo = CACHE / NSIS_ZIP
    if not arquivo.exists():
        passo(f"baixando o NSIS {NSIS_VERSAO}")
        with urllib.request.urlopen(NSIS_URL, timeout=180) as resposta:
            arquivo.write_bytes(resposta.read())

    obtido = hashlib.sha256(arquivo.read_bytes()).hexdigest()
    if obtido != NSIS_SHA:
        raise SystemExit(f"!! o hash do {NSIS_ZIP} não confere\n"
                         f"   esperado {NSIS_SHA}\n   obtido   {obtido}")

    import zipfile
    with zipfile.ZipFile(arquivo) as z:
        z.extractall(CACHE)
    if not (destino / "makensis.exe").exists():
        raise SystemExit(f"!! o .zip do NSIS não trouxe o makensis.exe "
                         f"em {destino}")
    passo(f"NSIS {NSIS_VERSAO} pronto em {destino.relative_to(RAIZ)}")
    return destino


def para_windows(caminho: Path) -> str:
    """Converte um caminho do Linux para a forma que o wine entende."""
    saida = subprocess.run(["winepath", "-w", str(caminho)],
                           capture_output=True, text=True, check=True)
    return saida.stdout.strip()


def main() -> int:
    if not (PACOTE / "MOS-Studio.exe").exists():
        raise SystemExit("!! o pacote não está montado — rode antes:\n"
                         "   ./empacotar/montar_windows.py")
    if shutil.which("wine") is None:
        raise SystemExit("!! falta o wine, que é quem roda o compilador do "
                         "NSIS (sudo dnf install wine)")

    nsis = preparar_nsis()
    versao = versao_do_projeto()
    saida = TRABALHO / f"MOS-Studio-{versao}-instalador.exe"
    icone = TRABALHO / "lancador" / "mos-studio.ico"
    if not icone.exists():
        raise SystemExit(f"!! falta o ícone {icone} — rode o montar_windows.py")
    if saida.exists():
        saida.unlink()

    passo(f"compilando o instalador (versão {versao})")
    comando = [
        "wine", str(nsis / "makensis.exe"),
        "/V2",
        f"/DVERSAO={versao}",
        f"/DPACOTE={para_windows(PACOTE)}",
        f"/DICONE={para_windows(icone)}",
        f"/DSAIDA={para_windows(saida)}",
        para_windows(EMPACOTAR / "instalador.nsi"),
    ]
    ambiente = {"WINEDEBUG": "-all"}
    import os
    processo = subprocess.run(comando, text=True, capture_output=True,
                              env={**os.environ, **ambiente})
    if processo.stdout.strip():
        print(processo.stdout.rstrip())
    if processo.returncode != 0:
        print(processo.stderr.rstrip(), file=sys.stderr)
        raise SystemExit("!! o makensis falhou")
    if not saida.exists():
        raise SystemExit("!! o makensis terminou bem mas não gerou o arquivo")

    pacote_bytes = sum(f.stat().st_size for f in PACOTE.rglob("*")
                       if f.is_file())
    print()
    passo(f"instalador pronto: {saida}")
    print(f"   {saida.stat().st_size / 1e6:.0f} MB "
          f"(de {pacote_bytes / 1e6:.0f} MB instalados)")
    print("   verifique com: ./empacotar/testar_instalador.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
