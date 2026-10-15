#!/usr/bin/env python3
"""Monta o pacote de Windows do MOS-Studio, rodando no Linux.

Resultado: ``windows_build/MOS-Studio/``, uma pasta que roda no Windows
sem instalar nada — Python próprio, Qt próprio, motor próprio. É o que o
instalador (``empacotar/instalador.nsi``) empacota.

POR QUE NÃO PyInstaller
-----------------------
O PyInstaller precisa rodar *dentro* do Windows: ele embute o interpretador
da máquina onde roda. Aqui a montagem é feita no Linux de propósito — é o
mesmo lugar onde o motor é compilado, onde os testes rodam e onde o
histórico do projeto vive. Então o pacote é montado à mão a partir de
peças oficiais:

  * a distribuição "embeddable" do python.org (um .zip, sem instalador);
  * as rodas (wheels) ``win_amd64`` do PySide6 e do shiboken6 do PyPI;
  * o ``suprem4-run-win/`` que o ``build_suprem4_windows.sh`` compila.

Nada é recompilado para Windows aqui além do lançador, que é um .c de cem
linhas. Tudo mais são binários oficiais, baixados com hash conferido.

VERIFICAÇÃO
-----------
Montar não prova que funciona. Depois de montar, rode
``empacotar/testar_windows.py``, que leva o pacote para a máquina virtual e
executa o autoteste da interface lá dentro.

Uso:
    ./empacotar/montar_windows.py            # monta
    ./empacotar/montar_windows.py --limpar   # apaga e monta de novo
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
EMPACOTAR = RAIZ / "empacotar"
TRABALHO = RAIZ / "windows_build"
CACHE = TRABALHO / "cache"
PACOTE = TRABALHO / "MOS-Studio"

#: Versão do Python embutida. Mudar aqui exige atualizar o hash e o nome do
#: ``._pth`` (que carrega o número da versão, ex. ``python313._pth``).
PYTHON = "3.13.16"
PYTHON_TAG = "313"

#: Versão do PySide6. Mantida igual à do Linux de desenvolvimento, para que
#: o que foi testado aqui seja o que roda lá.
PYSIDE = "6.11.1"

#: Hashes conferidos na primeira baixada. São a única defesa contra um
#: download trocado no caminho: as rodas do PyPI e o .zip do python.org vêm
#: por HTTPS, mas o pacote que sai daqui é assinado pelo projeto, não por
#: eles, e vale saber exatamente o que foi embrulhado.
ARQUIVOS = {
    f"python-{PYTHON}-embed-amd64.zip": (
        f"https://www.python.org/ftp/python/{PYTHON}/"
        f"python-{PYTHON}-embed-amd64.zip",
        "97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297"),
    f"pyside6_essentials-{PYSIDE}-cp310-abi3-win_amd64.whl": (
        None,
        "63311bd48e32c584599ab04b9ef7c324082374cd2c9fa533f978fb893bb47e40"),
    f"shiboken6-{PYSIDE}-cp310-abi3-win_amd64.whl": (
        None,
        "c2c6863aa80ec18c0f82cea3417837b279cdc60024ac17123461dc9042577df7"),
}

#: Módulos Qt que a interface usa. Conferido com
#: ``grep -r "from PySide6" mos_studio/``: são só estes três.
MODULOS_QT = ("QtCore", "QtGui", "QtWidgets")

#: Plugins do Qt que ficam. O ``platforms`` é obrigatório — sem o
#: ``qwindows.dll`` o Qt não abre janela nenhuma e morre com "could not find
#: or load the Qt platform plugin". O ``styles`` é o visual nativo do
#: Windows 11; sem ele o programa cai no estilo Fusion e fica com cara de
#: outro sistema. Os demais (qml, multimídia, rede, impressão) não têm uso
#: aqui.
PLUGINS_QT = ("platforms", "styles", "imageformats", "iconengines")

#: O que do pacote de desenvolvimento NÃO vai para o pacote do usuário.
IGNORAR = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache")


# ---------------------------------------------------------------- utilidades

def passo(texto: str) -> None:
    print(f">> {texto}", flush=True)


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar() -> None:
    """Garante as peças oficiais no cache, conferindo o hash de cada uma."""
    CACHE.mkdir(parents=True, exist_ok=True)
    faltam_rodas = [n for n in ARQUIVOS
                    if n.endswith(".whl") and not (CACHE / n).exists()]
    if faltam_rodas:
        passo("baixando as rodas do PySide6 (pip, plataforma win_amd64)")
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "--quiet",
             "--dest", str(CACHE), "--no-deps", "--only-binary", ":all:",
             "--platform", "win_amd64", "--python-version", PYTHON_TAG,
             "--implementation", "cp", "--abi", "abi3",
             f"PySide6-Essentials=={PYSIDE}", f"shiboken6=={PYSIDE}"],
            check=True)

    for nome, (url, esperado) in ARQUIVOS.items():
        destino = CACHE / nome
        if not destino.exists():
            if url is None:
                raise SystemExit(f"o pip não trouxe {nome}")
            passo(f"baixando {nome}")
            with urllib.request.urlopen(url, timeout=120) as resposta:
                destino.write_bytes(resposta.read())
        obtido = sha256(destino)
        if obtido != esperado:
            raise SystemExit(
                f"!! o hash de {nome} não confere\n"
                f"   esperado {esperado}\n"
                f"   obtido   {obtido}\n"
                "   Se a versão foi trocada de propósito, atualize ARQUIVOS "
                "neste script.")
    passo(f"{len(ARQUIVOS)} peças no cache, hashes conferidos")


# ------------------------------------------------------------------- Python

def montar_python() -> None:
    """Instala a distribuição embeddable em ``python/`` e ajusta o sys.path."""
    alvo = PACOTE / "python"
    alvo.mkdir(parents=True)
    with zipfile.ZipFile(CACHE / f"python-{PYTHON}-embed-amd64.zip") as z:
        z.extractall(alvo)

    # O ``._pth`` substitui o mecanismo normal de sys.path na distribuição
    # embeddable. Os caminhos são relativos à pasta do python313.dll, daí os
    # ".." : a raiz do pacote (onde está mos_studio/) e o lib/ (onde estão o
    # PySide6 e o shiboken6).
    #
    # "import site" fica ligado porque o PySide6 depende do módulo ``site``
    # para o ``os.add_dll_directory`` que aponta as DLLs do Qt; sem ele o
    # import de QtCore falha com "DLL load failed".
    (alvo / f"python{PYTHON_TAG}._pth").write_text(
        f"python{PYTHON_TAG}.zip\n"
        ".\n"
        "..\n"
        "..\\lib\n"
        "import site\n", encoding="ascii")
    passo(f"Python {PYTHON} em python/")


# ------------------------------------------------------------------- PySide6

def _dependencias(dll: Path) -> set[str]:
    """Nomes das DLLs que um PE importa (uma camada, não recursivo)."""
    saida = subprocess.run(
        ["x86_64-w64-mingw32-objdump", "-p", str(dll)],
        capture_output=True, text=True)
    nomes = set()
    for linha in saida.stdout.splitlines():
        linha = linha.strip()
        if linha.startswith("DLL Name:"):
            nomes.add(linha.split(":", 1)[1].strip().lower())
    return nomes


def _fechamento(pasta: Path, sementes: list[Path]) -> set[str]:
    """Fecho transitivo das DLLs de ``pasta`` que as sementes precisam.

    Em vez de manter uma lista à mão do que o Qt usa — que envelhece a cada
    versão do PySide6 —, lemos a tabela de importação de cada binário e
    seguimos as dependências que existem dentro do próprio pacote. O que
    sobra de fora (kernel32, user32...) é do Windows.
    """
    disponiveis = {p.name.lower(): p for p in pasta.iterdir()
                   if p.suffix.lower() == ".dll"}
    pendentes = list(sementes)
    guardar: set[str] = set()
    while pendentes:
        atual = pendentes.pop()
        for nome in _dependencias(atual):
            if nome in disponiveis and nome not in guardar:
                guardar.add(nome)
                pendentes.append(disponiveis[nome])
    return guardar


def montar_pyside() -> None:
    """Extrai as rodas em ``lib/`` e poda o Qt para os módulos usados."""
    lib = PACOTE / "lib"
    lib.mkdir(parents=True)
    for nome in ARQUIVOS:
        if nome.endswith(".whl"):
            with zipfile.ZipFile(CACHE / nome) as z:
                z.extractall(lib)

    ps = lib / "PySide6"
    antes = sum(f.stat().st_size for f in ps.rglob("*") if f.is_file())

    # 1. fora as pastas que só servem para desenvolver ou para QML.
    for sobra in ("qml", "include", "typesystems", "glue", "doc",
                  "scripts", "examples", "lib", "metatypes",
                  "Qt6Designer", "designer"):
        caminho = ps / sobra
        if caminho.is_dir():
            shutil.rmtree(caminho)
        elif caminho.exists():
            caminho.unlink()

    # 2. fora os módulos Python do Qt que a interface não importa.
    for pyd in list(ps.glob("Qt*.pyd")):
        if pyd.stem not in MODULOS_QT:
            pyd.unlink()
    for pyi in list(ps.glob("Qt*.pyi")):
        if pyi.stem not in MODULOS_QT:
            pyi.unlink()

    # 3. fora as DLLs do Qt que ninguém mais alcança. A conta é feita a
    #    partir do que sobrou: os .pyd dos três módulos, os plugins que
    #    ficam, e as DLLs de cola do próprio PySide6.
    sementes = [ps / f"{m}.pyd" for m in MODULOS_QT]
    sementes += [p for p in ps.glob("pyside6*.dll")]
    sementes += [p for p in (lib / "shiboken6").glob("*.dll")]
    for grupo in PLUGINS_QT:
        pasta = ps / "plugins" / grupo
        if pasta.is_dir():
            sementes += [p for p in pasta.glob("*.dll")]
    # Os plugins são carregados por nome, não por tabela de importação, e as
    # DLLs do runtime da Microsoft também: entram sempre.
    sempre = {p.name.lower() for p in ps.glob("msvcp*.dll")}
    sempre |= {p.name.lower() for p in ps.glob("vcruntime*.dll")}
    sempre |= {p.name.lower() for p in ps.glob("concrt*.dll")}

    manter = _fechamento(ps, [s for s in sementes if s.exists()]) | sempre
    manter |= {s.name.lower() for s in sementes if s.exists()}
    removidas = 0
    for dll in list(ps.glob("*.dll")):
        if dll.name.lower() not in manter:
            dll.unlink()
            removidas += 1

    # 4. fora os plugins de grupos inteiros que não usamos.
    plugins = ps / "plugins"
    if plugins.is_dir():
        for grupo in list(plugins.iterdir()):
            if grupo.is_dir() and grupo.name not in PLUGINS_QT:
                shutil.rmtree(grupo)

    # 5. traduções: só as do português, que dão os botões padrão dos
    #    diálogos do Qt ("Cancelar", "Aplicar") no idioma da interface.
    trad = ps / "translations"
    if trad.is_dir():
        for arquivo in list(trad.rglob("*")):
            if arquivo.is_file() and "pt" not in arquivo.stem.split("_")[-1:]:
                arquivo.unlink()
        for vazia in sorted((p for p in trad.rglob("*") if p.is_dir()),
                            reverse=True):
            if not any(vazia.iterdir()):
                vazia.rmdir()

    for lixo in list(lib.glob("*.dist-info")):
        shutil.rmtree(lixo)

    depois = sum(f.stat().st_size for f in ps.rglob("*") if f.is_file())
    passo(f"PySide6 {PYSIDE} em lib/ — {antes / 1e6:.0f} MB podados para "
          f"{depois / 1e6:.0f} MB ({removidas} DLLs do Qt fora)")


# ------------------------------------------------------- programa e motores

def montar_programa() -> None:
    """Copia o pacote Python do MOS-Studio, os dados e o motor de Windows."""
    shutil.copytree(RAIZ / "mos_studio", PACOTE / "mos_studio", ignore=IGNORAR)
    shutil.copytree(RAIZ / "data", PACOTE / "data", ignore=IGNORAR)

    motor = RAIZ / "suprem4-run-win"
    if not (motor / "bin" / "suprem.exe").exists():
        raise SystemExit("!! falta o motor de Windows — rode antes:\n"
                         "   ./build_suprem4_windows.sh")
    # Vai com o nome que o mos_studio/paths.py procura ao lado do pacote.
    shutil.copytree(motor, PACOTE / "suprem4-run", ignore=IGNORAR)

    (PACOTE / "resultados").mkdir(exist_ok=True)
    passo("programa, dados e motor copiados")


def montar_lancador() -> None:
    """Compila o MOS-Studio.exe com o ícone e a ficha de versão."""
    versao = "2.0.0"
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    for linha in texto.splitlines():
        if linha.startswith("version"):
            versao = linha.split("=", 1)[1].strip().strip('"')
            break
    # A ficha de versão do Windows são quatro números; "2.0.0.dev0" vira
    # 2,0,0,0 ali e continua escrito por extenso no campo de texto.
    numeros = [p for p in versao.replace("-", ".").split(".")
               if p.isdigit()][:4]
    while len(numeros) < 4:
        numeros.append("0")

    obj = TRABALHO / "lancador"
    obj.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(EMPACOTAR / "icone_windows.py"),
                    str(RAIZ / "data" / "io.syncfield.MosStudio.svg"),
                    str(obj / "mos-studio.ico")], check=True)
    subprocess.run(
        ["x86_64-w64-mingw32-windres",
         f"-DVERSAO_NUM={','.join(numeros)}",
         f"-DVERSAO_TEXTO=\\\"{versao}\\\"",
         "-I", str(obj),
         str(EMPACOTAR / "lancador_windows.rc"),
         "-o", str(obj / "recursos.o")], check=True)
    subprocess.run(
        ["x86_64-w64-mingw32-gcc", "-O2", "-municode", "-mwindows",
         str(EMPACOTAR / "lancador_windows.c"), str(obj / "recursos.o"),
         "-lshlwapi", "-o", str(PACOTE / "MOS-Studio.exe")], check=True)
    passo(f"MOS-Studio.exe compilado (versão {versao})")


def escrever_leiame() -> None:
    (PACOTE / "LEIA-ME.txt").write_text(
        "MOS-Studio\n"
        "==========\n\n"
        "Clique em MOS-Studio.exe para abrir o programa.\n\n"
        "Esta pasta é autossuficiente: traz o próprio Python, a própria\n"
        "biblioteca gráfica e o próprio simulador. Não precisa instalar\n"
        "mais nada, e não interfere em nenhum Python que você já tenha.\n\n"
        "O que vem dentro\n"
        "----------------\n"
        "  MOS-Studio.exe   o programa\n"
        "  suprem4-run\\     o SUPREM-IV.GS, o simulador de processo 2-D\n"
        "  resultados\\      cada simulação que você roda fica aqui\n"
        "  python\\, lib\\    o Python e o Qt que o programa usa\n\n"
        "Limitação desta versão\n"
        "----------------------\n"
        "Só o SUPREM-IV (2-D) acompanha o pacote de Windows. O SUPREM-III\n"
        "(1-D) e o MINIMOS 6.1 (dispositivo) ainda não têm versão de\n"
        "Windows porque o código-fonte deles não está disponível aqui — as\n"
        "telas que dependem deles avisam que o motor não foi encontrado.\n"
        "No Linux os três funcionam.\n\n"
        "SyncField Corporation\n",
        encoding="utf-8")


# ---------------------------------------------------------------------- main

def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--limpar", action="store_true",
                            help="apaga o pacote e o cache antes de montar")
    argumentos = analisador.parse_args()

    if shutil.which("x86_64-w64-mingw32-gcc") is None:
        raise SystemExit("!! falta o x86_64-w64-mingw32-gcc "
                         "(sudo dnf install mingw64-gcc)")

    if argumentos.limpar and TRABALHO.exists():
        shutil.rmtree(TRABALHO)
    if PACOTE.exists():
        shutil.rmtree(PACOTE)
    PACOTE.mkdir(parents=True)

    baixar()
    montar_python()
    montar_pyside()
    montar_programa()
    montar_lancador()
    escrever_leiame()

    total = sum(f.stat().st_size for f in PACOTE.rglob("*") if f.is_file())
    quantos = sum(1 for f in PACOTE.rglob("*") if f.is_file())
    print()
    passo(f"pacote pronto: {PACOTE}")
    print(f"   {quantos} arquivos, {total / 1e6:.0f} MB")
    print("   verifique com: ./empacotar/testar_windows.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
