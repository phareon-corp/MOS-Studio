#!/usr/bin/env python3
"""Instala, usa e desinstala o MOS-Studio na máquina virtual de Windows.

O instalador é a peça que mais depende do sistema de verdade: cria atalhos,
escreve no registro, aparece (ou não) na lista de aplicativos, e tem de
desfazer tudo isso na desinstalação. Nada disso se testa no Linux.

Este script faz o ciclo inteiro, sem tela, pelo ``qemu-guest-agent``:

1. instala em silêncio (``/S``), como quem clica "próximo" até o fim;
2. confere o que ficou no disco — o programa, o motor, o desinstalador;
3. confere o atalho no menu Iniciar e a entrada em "Aplicativos
   instalados" do Windows;
4. roda o programa instalado e lê o relatório de diagnóstico dele;
5. deixa um arquivo em ``resultados\\`` e desinstala em silêncio, para
   verificar que o desinstalador limpa o programa e **preserva** o trabalho
   do usuário (é o que a desinstalação silenciosa promete fazer).

Uso:
    ./empacotar/testar_instalador.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vmagente

RAIZ = Path(__file__).resolve().parent.parent
TRABALHO = RAIZ / "windows_build"

#: Onde o instalador é deixado dentro da VM.
REMOTO = r"C:\mos-instalador.exe"

#: O destino é dito à mão, com o ``/D=`` do NSIS, em vez de deixar o padrão
#: (``%LOCALAPPDATA%\Programs\MOS-Studio``).
#:
#: O motivo é uma armadilha do ambiente de teste, não do instalador: o
#: guest-agent roda como SYSTEM, cujo perfil fica dentro de
#: ``C:\Windows\System32``, e o compilador do NSIS gera um executável de 32
#: bits. Para um processo de 32 bits o Windows redireciona
#: ``System32`` para ``SysWOW64``, então o instalador gravava em
#: ``SysWOW64\config\systemprofile\...`` enquanto o PowerShell de 64 bits
#: olhava em ``System32\config\systemprofile\...`` e não achava nada. Com
#: um caminho em ``C:\`` não há redirecionamento e o teste mede o que
#: interessa. Para um usuário de verdade, cujo perfil está em ``C:\Users``,
#: a questão não existe.
DESTINO = r"C:\mos-instalado"

CHAVE = (r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall"
         r"\MOS-Studio")


class Falhou(Exception):
    """Um dos passos não passou."""


def _ps(comando: str, espera: float = 2400.0) -> str:
    return vmagente.powershell(comando, espera=espera)


def achar_instalador() -> Path:
    candidatos = sorted(TRABALHO.glob("MOS-Studio-*-instalador.exe"))
    if not candidatos:
        raise SystemExit("!! nenhum instalador em windows_build/ — rode "
                         "antes:\n   ./empacotar/instalador_windows.py")
    return candidatos[-1]


def limpar() -> None:
    """Remove instalação, atalhos e registro de uma rodada anterior."""
    _ps(f"""
$d = "{DESTINO}"
if (Test-Path $d) {{
  $u = Join-Path $d 'Desinstalar.exe'
  if (Test-Path $u) {{ Start-Process -FilePath $u -ArgumentList '/S' -Wait }}
  Start-Sleep -Seconds 2
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $d
}}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "{CHAVE}"
# Sobras de uma instalação feita no caminho padrão (ver a nota em DESTINO).
foreach ($raiz in @("$env:LOCALAPPDATA\\Programs\\MOS-Studio",
                    "C:\\WINDOWS\\SysWOW64\\config\\systemprofile\\AppData\\Local\\Programs\\MOS-Studio")) {{
  if (Test-Path $raiz) {{
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $raiz
  }}
}}
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
  "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\MOS-Studio"
'limpo'
""")


def passo_instalar() -> str:
    # O "/D=" do NSIS tem de ser o último argumento e vai sem aspas.
    saida = _ps(f"""
$p = Start-Process -FilePath '{REMOTO}' `
  -ArgumentList '/S', '/D={DESTINO}' -PassThru -Wait
"EXITCODE=$($p.ExitCode)"
$d = "{DESTINO}"
"DESTINO=$d"
"EXISTE=$(Test-Path $d)"
""")
    if "EXITCODE=0" not in saida:
        raise Falhou("o instalador não terminou bem:\n" + saida)
    if "EXISTE=True" not in saida:
        raise Falhou("o instalador terminou mas não criou a pasta:\n" + saida)
    return saida


def passo_conteudo() -> str:
    saida = _ps(f"""
$d = "{DESTINO}"
foreach ($f in @('MOS-Studio.exe','Desinstalar.exe','LEIA-ME.txt',
                 'python\\python.exe','lib\\PySide6\\QtWidgets.pyd',
                 'mos_studio\\app.py','suprem4-run\\bin\\suprem.exe',
                 'suprem4-run\\data\\suprem.uk',
                 'suprem-run\\sup3.exe','suprem-run\\S3cof0')) {{
  $c = Join-Path $d $f
  if (Test-Path $c) {{ "OK      $f" }} else {{ "FALTA   $f" }}
}}
$n = (Get-ChildItem -Recurse -File $d | Measure-Object).Count
$t = (Get-ChildItem -Recurse -File $d | Measure-Object -Sum Length).Sum
"arquivos instalados: $n"
"tamanho: $([math]::Round($t/1MB,0)) MB"
""")
    if "FALTA" in saida:
        raise Falhou("a instalação está incompleta:\n" + saida)
    return saida


#: Onde procurar o menu Iniciar. O primeiro é o caminho normal; o segundo é
#: o mesmo visto de um processo de 32 bits, que é o que o instalador é (ver a
#: nota em DESTINO). Rodando como SYSTEM, o atalho acaba no segundo.
MENUS = (r"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\MOS-Studio",
         r"C:\WINDOWS\SysWOW64\config\systemprofile\AppData\Roaming"
         r"\Microsoft\Windows\Start Menu\Programs\MOS-Studio")


def passo_integracao() -> str:
    candidatos = ",".join(f'"{m}"' for m in MENUS)
    saida = _ps(f"""
$menu = @({candidatos}) | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
if ($menu) {{
  "menu: $menu"
  Get-ChildItem $menu -Filter *.lnk | ForEach-Object {{ "atalho: $($_.Name)" }}
}} else {{ "SEM MENU" }}
if (Test-Path "{CHAVE}") {{
  $r = Get-ItemProperty "{CHAVE}"
  "registro: $($r.DisplayName) $($r.DisplayVersion) - $($r.Publisher)"
  "desinstalar: $($r.UninstallString)"
  "local: $($r.InstallLocation)"
  "tamanho declarado: $([math]::Round($r.EstimatedSize/1024,0)) MB"
}} else {{ "SEM REGISTRO" }}
""")
    if "SEM MENU" in saida or "SEM REGISTRO" in saida:
        raise Falhou("o instalador não se integrou ao Windows:\n" + saida)
    if "MOS-Studio.lnk" not in saida:
        raise Falhou("falta o atalho principal no menu Iniciar:\n" + saida)
    return saida


def passo_rodar() -> str:
    saida = _ps(f"""
$d = "{DESTINO}"
Set-Location $d
Remove-Item -Force -ErrorAction SilentlyContinue diagnostico.txt
$env:MOS_DIAGNOSTICO_SILENCIOSO = '1'
$p = Start-Process -FilePath "$d\\MOS-Studio.exe" `
  -ArgumentList '--diagnostico' -PassThru -Wait
"EXITCODE=$($p.ExitCode)"
if (Test-Path diagnostico.txt) {{
  Get-Content -Encoding utf8 diagnostico.txt | Out-String
}} else {{ "SEM RELATORIO" }}
""")
    if "EXITCODE=0" not in saida or "SEM RELATORIO" in saida:
        raise Falhou("o programa instalado não rodou:\n" + saida)
    if "Nenhum problema encontrado" not in saida:
        raise Falhou("o diagnóstico do programa instalado achou problemas:\n"
                     + saida)
    return saida


def passo_desinstalar() -> str:
    menus = ",".join(f'"{m}"' for m in MENUS)
    saida = _ps(f"""
$d = "{DESTINO}"
New-Item -ItemType Directory -Force -Path "$d\\resultados" | Out-Null
Set-Content -Encoding ascii "$d\\resultados\\simulacao-do-usuario.txt" `
  'isto representa o trabalho de quem usa o programa'
$p = Start-Process -FilePath "$d\\Desinstalar.exe" -ArgumentList '/S' `
  -PassThru -Wait
"EXITCODE=$($p.ExitCode)"
Start-Sleep -Seconds 3
"programa removido: $(-not (Test-Path "$d\\MOS-Studio.exe"))"
"python removido: $(-not (Test-Path "$d\\python"))"
"motor removido: $(-not (Test-Path "$d\\suprem4-run"))"
"registro removido: $(-not (Test-Path "{CHAVE}"))"
$menus = @({menus}) | Where-Object {{ Test-Path $_ }}
"menu removido: $($menus.Count -eq 0)"
"trabalho do usuario preservado: $(Test-Path "$d\\resultados\\simulacao-do-usuario.txt")"
""")
    problemas = [l for l in saida.splitlines() if l.endswith("False")]
    if "EXITCODE=0" not in saida or problemas:
        raise Falhou("a desinstalação não ficou como deveria:\n" + saida)
    return saida


def main() -> int:
    instalador = achar_instalador()
    print(f">> instalador: {instalador.name} "
          f"({instalador.stat().st_size / 1e6:.0f} MB)")

    print(">> acordando a máquina virtual")
    vmagente.ligar()

    print(">> limpando instalação anterior, se houver")
    limpar()

    print(">> enviando o instalador para a VM")
    enviados = vmagente.enviar_arquivo(instalador, REMOTO)
    print(f"   {enviados / 1e6:.0f} MB em {REMOTO}")

    passos = (
        ("instala em silêncio", passo_instalar),
        ("os arquivos chegaram todos", passo_conteudo),
        ("atalho e registro do Windows", passo_integracao),
        ("o programa instalado roda", passo_rodar),
        ("desinstala e preserva as simulações", passo_desinstalar),
    )
    falhas = 0
    for titulo, funcao in passos:
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
    _ps(f"Remove-Item -Force -ErrorAction SilentlyContinue '{REMOTO}'")
    if falhas:
        print(f">> {falhas} de {len(passos)} passos falharam")
        return 1
    print(f">> o ciclo completo passou no Windows "
          f"({len(passos)} passos)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
