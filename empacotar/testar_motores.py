#!/usr/bin/env python3
"""Roda uma simulação curta em cada motor instalado e confere o resultado.

"Pronto" no diagnóstico quer dizer que os arquivos estão no lugar; este
teste prova que cada motor **simula** — que o binário compilado roda nesta
máquina e devolve a saída que a interface lê. É o que se roda depois do
``instalar.sh`` numa instalação limpa (contêiner, VM ou notebook) e dentro da
VM de Windows.

Uso (com o Python do programa)::

    ~/.local/share/mos-studio/venv/bin/python empacotar/testar_motores.py
    python empacotar/testar_motores.py --exigir-minimos

Sai com 0 se todos os motores encontrados simularam; 1 se algum falhou, ou
se o MINIMOS faltar e ``--exigir-minimos`` foi pedido.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mos_studio.core import minimos, suprem, suprem4  # noqa: E402

#: Substrato tipo p, oxidação úmida e implante de fósforo: exercita o
#: oxidante, o implante e a difusão em menos de um segundo.
DECK_SUPREM3 = """TITLE     Teste de instalacao do MOS-Studio
INITIALIZE  <100> SILICON  BORON CONCENTRATION=1E15 THICKNESS=2 DX=.005
DIFFUSION  TIME=30 TEMPERATURE=1000 WETO2
IMPLANT    PHOSPHORUS DOSE=1E14 ENERGY=60
DIFFUSION  TIME=20 TEMPERATURE=1000 NITROGEN
PRINT      LAYERS
STOP
"""

#: O mesmo deck do teste de Windows (empacotar/testar_windows.py).
DECK_SUPREM4 = """mode one.dim
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

#: Exemplo 1 do manual do MINIMOS (MOSFET de canal n, um ponto de bias).
DECK_MINIMOS = """TRANSISTOR MOS 78
DEVICE CHANNEL=N GATE=NPOLY TINS=20E-7 L=1.04E-4 W=10E-4
PROFILE NB=8E16 ELEM=PH DOSE=8E15 AKEV=50 TOX=20E-7 TEMP=900 TIME=1800
IMPLANT ELEM=B DOSE=7.7E11 AKEV=20 TEMP=900 TIME=1800
INTERFACE NSS=1E11
BIAS UD=10 UG=-1.057 US=0 UB=0
OPTION MODEL=AVAL
OUTPUT NONE=YES
END
"""


def _suprem3() -> str:
    saida = suprem.run_sync(DECK_SUPREM3)
    if "Layer" not in saida and "LAYER" not in saida.upper():
        raise RuntimeError("a saída não traz a tabela de camadas:\n" + saida[-800:])
    return f"{len(saida.splitlines())} linhas de saída, tabela de camadas presente"


def _suprem4() -> str:
    saida = suprem4.run_sync(DECK_SUPREM4)
    numeros = [ln for ln in saida.splitlines()
               if ln.strip()[:1].isdigit() and len(ln.split()) >= 2]
    if len(numeros) < 10:
        raise RuntimeError("o print.1d não devolveu o perfil:\n" + saida[-800:])
    return f"perfil com {len(numeros)} pontos"


def _minimos() -> str:
    mdir = minimos.find_dir()
    pronto = threading.Event()
    caixa: dict = {}
    minimos.run(DECK_MINIMOS, mdir, base="teste",
                callback_done=lambda r: (caixa.update(r), pronto.set()),
                callback_error=lambda e: (caixa.update(erro=e), pronto.set()))
    if not pronto.wait(600):
        raise RuntimeError("o MINIMOS não terminou em 10 minutos")
    if caixa.get("erro"):
        raise RuntimeError(caixa["erro"])
    saida = caixa.get("out") or ""
    if "DRAIN CURRENT" not in saida:
        raise RuntimeError("a saída não traz a corrente de dreno:\n"
                           + (saida[-800:] or str(caixa.get("ref"))[-800:]))
    linha = next(ln for ln in saida.splitlines() if "DRAIN CURRENT" in ln)
    return " ".join(linha.split())


def main() -> int:
    exigir_minimos = "--exigir-minimos" in sys.argv
    motores = [
        ("SUPREM-III", suprem.find_run_dir, suprem.check_engine, _suprem3),
        ("SUPREM-IV.GS", suprem4.find_run_dir, suprem4.check_engine, _suprem4),
        ("MINIMOS 6.1", minimos.find_dir, minimos.check_engine, _minimos),
    ]
    falhas = 0
    for nome, achar, conferir, simular in motores:
        pasta = achar()
        problemas = conferir(pasta) if pasta else ["não instalado"]
        if problemas:
            obrigatorio = nome != "MINIMOS 6.1" or exigir_minimos
            marca = "FALHOU" if obrigatorio else "ausente"
            print(f"{nome:<14} {marca}: {'; '.join(problemas)}")
            falhas += obrigatorio
            continue
        inicio = time.monotonic()
        try:
            resumo = simular()
        except Exception as exc:  # noqa: BLE001 - o relatório é o produto
            print(f"{nome:<14} FALHOU: {exc}")
            falhas += 1
            continue
        print(f"{nome:<14} ok ({time.monotonic() - inicio:.1f} s) — {resumo}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
