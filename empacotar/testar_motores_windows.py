#!/usr/bin/env python3
"""Instala o MOS-Studio na VM de Windows e simula nos três motores.

Complementa o ``testar_instalador.py`` (que confere atalhos, registro e
desinstalação): aqui o que importa é que, depois do instalador, cada motor
**simula** no Windows de verdade —

1. instala em silêncio, como o usuário;
2. instala o MINIMOS a partir do zip, pelo mesmo caminho do botão da tela
   de Dispositivo (``mos-studio --instalar-minimos ZIP``);
3. roda ``empacotar/testar_motores.py`` com o Python do pacote: uma
   simulação curta no SUPREM-III, no SUPREM-IV.GS e no MINIMOS;
4. desinstala.

O zip do MINIMOS não vem do repositório (a licença não permite); é passado
pela linha de comando e só vai para dentro da VM de testes.

Uso:
    ./empacotar/testar_motores_windows.py /caminho/minimoswin6.1.zip
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vmagente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
TRABALHO = RAIZ / "windows_build"
REMOTO = r"C:\mos-instalador.exe"
#: Em C:\ pelo mesmo motivo do testar_instalador.py (o agente roda como
#: SYSTEM e o NSIS é 32 bits). O nome é longo de propósito: passa dos 80
#: caracteres do SUPREM-III se o motor usasse o caminho absoluto dos dados.
DESTINO = r"C:\mos-motores\uma pasta com nome bem comprido para testar caminhos\MOS-Studio"
ZIP_REMOTO = r"C:\mos-motores-minimoswin6.1.zip"


def _ps(comando: str, espera: float = 2400.0) -> str:
    return vmagente.powershell(comando, espera=espera)


def main() -> int:
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print(__doc__)
        return 2
    zip_local = Path(sys.argv[1])
    instalador = sorted(TRABALHO.glob("MOS-Studio-*-instalador.exe"))[-1]

    vmagente.ligar()
    print(f">> enviando {instalador.name} e o zip do MINIMOS")
    vmagente.enviar_arquivo(instalador, REMOTO)
    vmagente.enviar_arquivo(zip_local, ZIP_REMOTO)
    vmagente.enviar_arquivo(RAIZ / "empacotar" / "testar_motores.py",
                            r"C:\mos-testar_motores.py")

    print(">> instalando em silêncio")
    print(_ps(f"""
$d = "{DESTINO}"
if (Test-Path $d) {{ Remove-Item -Recurse -Force $d }}
$p = Start-Process -FilePath '{REMOTO}' -ArgumentList '/S', '/D={DESTINO}' -PassThru -Wait
"instalador: $($p.ExitCode)"
""").strip())

    print(">> instalando o MINIMOS a partir do zip (mos-studio --instalar-minimos)")
    print(_ps(f"""
$d = "{DESTINO}"
& "$d\\python\\python.exe" -m mos_studio --instalar-minimos "{ZIP_REMOTO}" 2>&1
"saida: $LASTEXITCODE"
Get-ChildItem "$d\\minimos-run" | Select-Object -ExpandProperty Name
""").strip())

    print(">> simulando nos três motores")
    saida = _ps(f"""
$d = "{DESTINO}"
Copy-Item C:\\mos-testar_motores.py "$d\\testar_motores.py"
Push-Location $d
& "$d\\python\\python.exe" "$d\\testar_motores.py" --exigir-minimos 2>&1
"TESTE=$LASTEXITCODE"
Pop-Location
""")
    print(saida.strip())

    print(">> desinstalando")
    _ps(f"""
$u = "{DESTINO}\\Desinstalar.exe"
if (Test-Path $u) {{ Start-Process -FilePath $u -ArgumentList '/S' -Wait }}
Start-Sleep -Seconds 2
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "C:\\mos-motores"
Remove-Item -Force -ErrorAction SilentlyContinue '{REMOTO}', '{ZIP_REMOTO}', C:\\mos-testar_motores.py
'ok'
""")
    ok = "TESTE=0" in saida
    print("\n>> " + ("TUDO CERTO: os três motores simulam no Windows."
                     if ok else "FALHOU — veja acima."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
