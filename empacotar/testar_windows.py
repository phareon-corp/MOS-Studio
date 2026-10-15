#!/usr/bin/env python3
"""Leva o pacote de Windows para a máquina virtual e o testa lá dentro.

Montar o pacote no Linux (``empacotar/montar_windows.py``) não prova nada:
quase todo problema de empacotamento no Windows só aparece na hora — um
plugin do Qt que falta, uma DLL do runtime da Microsoft, um caminho com
barra errada, o motor que não acha o arquivo de chaves. Este script roda os
testes no Windows de verdade, sem precisar de tela: a VM responde pelo
``qemu-guest-agent`` (ver :mod:`vmagente`).

O que é verificado, em ordem:

1. **o Python do pacote sobe** — importa o PySide6 e diz a versão;
2. **o diagnóstico passa** — monta a janela principal inteira, confere os
   motores e encerra sem thread pendente (``--autoteste``);
3. **o plugin nativo do Qt carrega** — a mesma coisa sem
   ``QT_QPA_PLATFORM=offscreen``, que é o que prova que o ``qwindows.dll``
   e as DLLs de que ele depende foram todos embrulhados;
4. **o motor simula pelo programa** — uma receita curta passa por
   ``core.suprem4.run_sync`` e a tabela de perfil volta;
5. **o lançador funciona** — ``MOS-Studio.exe --autoteste``, que é o
   caminho que o usuário usa, e cujo relatório é lido do arquivo.

Uso:
    ./empacotar/testar_windows.py            # usa o pacote já montado
    ./empacotar/testar_windows.py --enviar   # reenvia o pacote antes
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vmagente

RAIZ = Path(__file__).resolve().parent.parent
PACOTE = RAIZ / "windows_build" / "MOS-Studio"

#: Onde o pacote fica dentro da VM. Fora do perfil de usuário de propósito:
#: o guest-agent roda como SYSTEM, e um caminho em C:\ é o mesmo para
#: qualquer conta.
DESTINO = r"C:\mos-pacote"

#: Receita curta que exercita o motor pelo programa: substrato, implante,
#: difusão e a tabela de perfil. Dá menos de um segundo no motor.
DECK = """mode one.dim
line x loc=0 spacing=0.01 tag=topo
line x loc=0.4 spacing=0.02
line x loc=1.5 spacing=0.2 tag=fundo
region silicon xlo=topo xhi=fundo
bound exposed xlo=topo xhi=topo
init boron conc=1e15
implant arsenic dose=2e15 energy=60 pearson
diffuse time=20 temp=1000
select z=doping
print.1d
"""


class Falhou(Exception):
    """Um dos testes não passou."""


def _ps(comando: str, espera: float = 1800.0) -> str:
    return vmagente.powershell(comando, espera=espera)


def _preparar_ambiente(offscreen: bool) -> str:
    """Trecho de PowerShell que prepara as variáveis de ambiente."""
    linhas = [
        f"Set-Location '{DESTINO}'",
        "$env:PYTHONHOME = \"$PWD\\python\"",
        "$env:PYTHONPATH = $null",
        "$env:MOS_DIAGNOSTICO_SILENCIOSO = '1'",
    ]
    linhas.append("$env:QT_QPA_PLATFORM = "
                  + ("'offscreen'" if offscreen else "$null"))
    return "; ".join(linhas)


def teste_python() -> str:
    saida = _ps(_preparar_ambiente(True) + """
& .\\python\\python.exe -c @"
import sys, PySide6
from PySide6.QtCore import qVersion
print('python', sys.version.split()[0])
print('PySide6', PySide6.__version__, 'Qt', qVersion())
"@ 2>&1 | Out-String
"LASTEXITCODE=$LASTEXITCODE"
""")
    if "LASTEXITCODE=0" not in saida or "PySide6" not in saida:
        raise Falhou("o Python do pacote não importa o PySide6:\n" + saida)
    return "\n".join(l for l in saida.splitlines()
                     if l.startswith(("python", "PySide6")))


def teste_diagnostico(offscreen: bool) -> str:
    saida = _ps(_preparar_ambiente(offscreen) + """
& .\\python\\python.exe -m mos_studio --autoteste 2>&1 | Out-String
"LASTEXITCODE=$LASTEXITCODE"
""")
    if "LASTEXITCODE=0" not in saida:
        raise Falhou(("diagnóstico com o plugin nativo do Qt" if not offscreen
                      else "diagnóstico") + " falhou:\n" + saida)
    return saida


def teste_motor() -> str:
    deck = DECK.replace('"', '`"')
    saida = _ps(_preparar_ambiente(True) + f"""
Set-Content -Encoding ascii teste_motor.in @'
{DECK}'@
& .\\python\\python.exe -c @"
from pathlib import Path
from mos_studio.core import suprem4
pasta = suprem4.find_run_dir()
print('motor:', pasta)
problemas = suprem4.check_engine(pasta)
print('problemas:', problemas or 'nenhum')
saida = suprem4.run_sync(Path('teste_motor.in').read_text())
linhas = [l for l in saida.splitlines() if l.strip()]
print('linhas de saida:', len(linhas))
tabela = [l for l in linhas if l.lstrip()[:1].isdigit()]
print('linhas de tabela:', len(tabela))
print('primeira:', tabela[0].strip() if tabela else 'NENHUMA')
print('ultima:', tabela[-1].strip() if tabela else 'NENHUMA')
assert len(tabela) > 20, 'tabela de perfil curta ou ausente'
"@ 2>&1 | Out-String
"LASTEXITCODE=$LASTEXITCODE"
""")
    del deck
    if "LASTEXITCODE=0" not in saida:
        raise Falhou("o motor não simulou pelo programa:\n" + saida)
    return saida


def teste_lancador() -> str:
    """Roda o MOS-Studio.exe e lê o relatório que ele grava em disco.

    O lançador é compilado como aplicação de janela e não tem saída padrão,
    então o resultado vem pelo ``diagnostico.txt``. É de propósito: é
    exatamente assim que o usuário no Windows vai ler um problema.
    """
    saida = _ps(f"""
Set-Location '{DESTINO}'
Remove-Item -Force -ErrorAction SilentlyContinue diagnostico.txt
$env:MOS_DIAGNOSTICO_SILENCIOSO = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
$p = Start-Process -FilePath '.\\MOS-Studio.exe' -ArgumentList '--autoteste' -PassThru -Wait
"EXITCODE=$($p.ExitCode)"
if (Test-Path diagnostico.txt) {{ Get-Content -Encoding utf8 diagnostico.txt | Out-String }}
else {{ "SEM RELATORIO" }}
""")
    if "EXITCODE=0" not in saida:
        raise Falhou("o MOS-Studio.exe não terminou bem:\n" + saida)
    if "SEM RELATORIO" in saida:
        raise Falhou("o MOS-Studio.exe não gravou o diagnóstico:\n" + saida)
    return saida


def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("--enviar", action="store_true",
                            help="reenvia o pacote para a VM antes de testar")
    argumentos = analisador.parse_args()

    if not (PACOTE / "MOS-Studio.exe").exists():
        raise SystemExit("!! o pacote não está montado — rode antes:\n"
                         "   ./empacotar/montar_windows.py")

    print(">> acordando a máquina virtual")
    vmagente.ligar()

    ja_esta = "True" in _ps(
        f"Test-Path '{DESTINO}\\MOS-Studio.exe'", espera=120)
    if argumentos.enviar or not ja_esta:
        print(f">> enviando o pacote ({sum(f.stat().st_size for f in
                                           PACOTE.rglob('*')
                                           if f.is_file()) / 1e6:.0f} MB)")
        _ps(f"Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "
            f"'{DESTINO}'", espera=300)
        inicio = time.monotonic()
        quantos, bytes_ = vmagente.enviar_pasta(PACOTE, DESTINO)
        print(f"   {quantos} arquivos, {bytes_ / 1e6:.0f} MB em "
              f"{time.monotonic() - inicio:.0f} s")

    testes = (
        ("o Python e o Qt do pacote sobem", teste_python),
        ("o diagnóstico passa (offscreen)", lambda: teste_diagnostico(True)),
        ("o plugin nativo do Qt carrega", lambda: teste_diagnostico(False)),
        ("o motor simula pelo programa", teste_motor),
        ("o MOS-Studio.exe roda", teste_lancador),
    )
    falhas = 0
    for titulo, funcao in testes:
        print(f"\n>> {titulo}")
        try:
            detalhe = funcao()
        except Falhou as erro:
            falhas += 1
            print("   FALHOU")
            print("   " + str(erro).replace("\n", "\n   "))
            continue
        for linha in str(detalhe).strip().splitlines():
            if linha.strip():
                print("   " + linha.rstrip())
        print("   OK")

    print()
    if falhas:
        print(f">> {falhas} de {len(testes)} testes falharam")
        return 1
    print(f">> os {len(testes)} testes passaram no Windows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
