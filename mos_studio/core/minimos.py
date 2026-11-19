"""Execução do MINIMOS 6.1 e geração/leitura dos seus arquivos.

Movido de ``suprem3.py`` sem mudança de lógica. O ponto delicado é o
**mecanismo duplo** de nomes de arquivo, que mantém o mesmo código funcionando
com qualquer binário:

* ``gfortran`` abre as unidades sem ``FILE=`` e usa os nomes padrão ``fort.NN``
  (15 entrada, 16 saída, 31 stack, 61 I-V; unidade 6 = stdout);
* Compaq Visual Fortran usa variáveis de ambiente ``FORTnn`` → ``base.ext``.

Preparamos os dois (``fort.NN`` no diretório **e** as variáveis ``FORTnn``) e
copiamos o ``stack.rul`` para ``fort.31``. A interface do MINIMOS é de uma
etapa posterior; aqui fica só o motor.
"""

from __future__ import annotations

import datetime
import math
import os
import shutil
import struct
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from .. import paths

#: Viés de dreno mínimo aceito pelo MODEL=2-D (em volts); ver ``build_deck``.
UD_MINIMO = 0.1

#: Mapa de unidades FORTRAN → extensão de arquivo, idêntico ao ``bin/minimos.bat``.
UNIT_EXT = {
    1: "i3d", 2: "bin", 15: "inp", 16: "out", 30: "asciipif",
    40: "mtv", 41: "mcm", 61: "iv", 71: "gch", 72: "pvd", 73: "etp",
    74: "hci", 75: "hci", 76: "hco", 77: "hcd", 80: "uai", 82: "tra",
    84: "tgr", 85: "tpp", 86: "grx", 87: "bbt", 88: "csh", 89: "lpf",
}


def is_pe_executable(path: Path) -> bool:
    """``True`` se o arquivo é um executável Windows PE (assinatura ``MZ``)."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except OSError:
        return False


def find_dir() -> Path | None:
    """Pasta do MINIMOS (``mm_pl`` + ``stack.rul``): config salva, depois padrões."""
    from .. import config

    saved = config.get("minimos_dir", "")
    if saved and (Path(saved) / ("mm_pl" + paths.EXE)).exists():
        return Path(saved)
    candidates = list(paths.MINIMOS_DIRS)
    if paths.IS_WIN:
        candidates += [Path(r"C:\minimos\bin"), Path(r"C:\minimoswin6_1\bin")]
    for c in candidates:
        if (c / ("mm_pl" + paths.EXE)).exists():
            return c
    return None


def check_engine(mdir: Path | None) -> list[str]:
    """Lista de problemas que impedem rodar o MINIMOS (vazia = ok)."""
    problems: list[str] = []
    if mdir is None:
        return ["pasta do MINIMOS não definida"]
    mdir = Path(mdir)
    exe = mdir / ("mm_pl" + paths.EXE)
    if not exe.exists():
        problems.append(f"mm_pl{paths.EXE} não encontrado em {mdir}")
    elif not paths.IS_WIN and not os.access(exe, os.X_OK):
        problems.append("sem permissão de execução: mm_pl")
    if not (mdir / "stack.rul").exists():
        problems.append("stack.rul não encontrado (regra de empilhamento obrigatória)")
    # binário Win32 (Compaq) só roda no Windows; nativo (gfortran) roda no SO atual
    if not paths.IS_WIN and exe.exists() and is_pe_executable(exe):
        problems.append("o mm_pl encontrado é Win32 (.exe Compaq) — recompile com "
                        "build_minimos.sh para rodar no Linux")
    return problems


def run(inp_text: str, mdir: Path, base: str = "mm_run", screen: str = "o",
        dopfile: str | Path | None = None,
        callback_done: Callable[[dict], None] | None = None,
        callback_error: Callable[[str], None] | None = None) -> threading.Thread:
    """Roda o MINIMOS em background (Linux gfortran e Windows Compaq/gfortran).

    Devolve a thread iniciada. A referência (unidade 6) é capturada do stdout.
    """
    mdir = Path(mdir)

    def _run():
        work = None
        try:
            exe = mdir / ("mm_pl" + paths.EXE)
            if not exe.exists():
                raise RuntimeError(f"mm_pl{paths.EXE} não encontrado em {mdir}")
            if not (mdir / "stack.rul").exists():
                raise RuntimeError("stack.rul não encontrado")
            if not paths.IS_WIN and is_pe_executable(exe):
                raise RuntimeError("mm_pl é Win32 (.exe) — recompile com "
                                   "build_minimos.sh para Linux")
            work = Path(tempfile.mkdtemp(prefix="minimos_"))
            # --- convenção gfortran: fort.NN no diretório de trabalho ---
            (work / "fort.15").write_text(inp_text, encoding="ascii", errors="replace")
            shutil.copy2(mdir / "stack.rul", work / "fort.31")
            if dopfile and Path(dopfile).exists():
                shutil.copy2(dopfile, work / "fort.20")
            # --- convenção Compaq: nomes base.ext + variáveis FORTnn ---
            (work / f"{base}.inp").write_text(inp_text, encoding="ascii",
                                              errors="replace")
            env = dict(os.environ)
            for unit, ext in UNIT_EXT.items():
                env[f"FORT{unit}"] = f"{base}.{ext}"
            env["FORT20"] = str(dopfile) if dopfile else "NUL"
            env["FORT31"] = str((mdir / "stack.rul").resolve())
            creat = getattr(subprocess, "CREATE_NO_WINDOW", 0) if paths.IS_WIN else 0
            ref_path = work / f"{base}.ref"
            if is_pe_executable(exe):
                # O runtime do Compaq Visual Fortran escreve a unidade 6 no
                # CONOUT$, não no stdout herdado. Sem console (o programa roda
                # com CREATE_NO_WINDOW), a primeira escrita aborta com
                # "forrtl: severe (38)" e nenhuma simulação sai. Com FORT6 a
                # unidade 6 vira um arquivo comum, como as demais.
                env["FORT6"] = ref_path.name
                rc = subprocess.run([str(exe.resolve())], cwd=str(work), env=env,
                                    stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=1800,
                                    creationflags=creat).returncode
            else:
                with open(ref_path, "w") as reff:
                    rc = subprocess.run([str(exe.resolve())], cwd=str(work), env=env,
                                        stdin=subprocess.DEVNULL,
                                        stdout=(reff if screen != "y" else None),
                                        stderr=subprocess.STDOUT, timeout=1800,
                                        creationflags=creat).returncode

            def rd(*names):
                for n in names:
                    f = work / n
                    if f.exists() and f.stat().st_size > 0:
                        return f.read_text(encoding="latin1", errors="replace")
                return None

            result: dict[str, Any] = {
                "out": rd("fort.16", f"{base}.out"),
                "ref": rd(f"{base}.ref"),
                "iv": rd("fort.61", f"{base}.iv"),
                "mtv": rd("fort.40", f"{base}.mtv"),
                "pif": rd("fort.30", f"{base}.asciipif"),
                "returncode": rc, "stages": ["mm_pl (planar)"],
                "files": sorted(p.name for p in work.iterdir() if p.is_file()),
            }
            # persiste na pasta de execuções com nomes amigáveis
            try:
                from .workspace import runs_dir
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = runs_dir() / f"minimos_{base}_{stamp}"
                dest.mkdir(parents=True, exist_ok=True)
                inv = {f"fort.{u}": ext for u, ext in UNIT_EXT.items()}
                for p in work.iterdir():
                    if not p.is_file():
                        continue
                    name = f"{base}.{inv[p.name]}" if p.name in inv else p.name
                    shutil.copy2(p, dest / name)
                result["__dir__"] = str(dest)
            except OSError:
                result["__dir__"] = None
            if callback_done:
                callback_done(result)
        except Exception as e:  # noqa: BLE001 - erro vai para a interface
            if callback_error:
                callback_error(str(e))
        finally:
            if work and work.exists():
                shutil.rmtree(work, ignore_errors=True)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


def build_deck(p: dict[str, Any]) -> str:
    """Gera o texto de um deck MINIMOS a partir de um dicionário de parâmetros.

    Unidades de entrada amigáveis: TOX/profundidades em nm, W/L em µm; converte
    para cm no deck. Cobre NMOS (perfil analítico) e PMOS (``PROFILE FILE=2-D``
    — o perfil 2-D é gerado à parte). Modos: ``vth`` (MODEL=THRES), ``op``
    (ponto de operação 2-D, com mapas) e ``iv`` (varredura STEP).
    """
    def f(key, default):
        return p.get(key, default)

    ch = (f("channel", "N") or "N").upper()[:1]
    ch = "P" if ch == "P" else "N"
    gate = f("gate", "NPOLY" if ch == "N" else "PPOLY")
    tox_nm = float(f("tox_nm", 15))
    w_um = float(f("w_um", 1.0))
    l_um = float(f("l_um", 0.85))
    mode = f("mode", "iv")
    title = f("title", "Deck gerado pelo construtor MINIMOS")
    L = [f"* {title}",
         f"DEVICE     CHANNEL={ch}  GATE={gate}  TOX={tox_nm*1e-7:.3E}  "
         f"W={w_um*1e-4:.3E}  L={l_um*1e-4:.3E}"]
    # polarização
    sgn = 1.0 if ch == "N" else -1.0
    ud = float(f("ud", 0.1)) * (sgn if f("auto_sign", True) else 1.0)
    # O MODEL=2-D desta compilação segfalha com dreno em exatamente zero; um
    # viés mínimo mantém a solução bem posta sem mudar a curva de forma visível.
    if mode != "vth" and abs(ud) < UD_MINIMO:
        ud = UD_MINIMO * (sgn if f("auto_sign", True) else 1.0)
    bias = f"BIAS       UD={ud:g}"
    # UG é obrigatório: sem ele o MODEL=2-D desta compilação morre com SIGSEGV
    # depois de montar a malha (ver docs/adr/0001, decisão sobre a ponte).
    ug = p.get("ug", None)
    bias += f"  UG={float(ug) if ug not in (None, '') else 0.0:g}"
    for k, key in (("US", "us"), ("UB", "ub")):
        v = p.get(key, None)
        if v not in (None, ""):
            bias += f"  {k}={float(v):g}"
    L.append(bias)
    # varredura (curva I-V)
    if mode == "iv":
        var = f("step_var", "DD")            # DD varre VD, DG varre VG
        ncount = "ND" if var == "DD" else "NG"
        stepv = float(f("step", 0.5)) * (sgn if f("auto_sign", True) else 1.0)
        L.append(f"STEP       {var}={stepv:g}  {ncount}={int(f('nstep', 8))}")
    # perfil — sempre o card analítico. O caminho ``PROFILE FILE=2-D`` existe em
    # ``write_2d_profile`` mas aborta dentro do motor nesta compilação; a ponte
    # com o SUPREM passa pelos parâmetros deste card (ver core/bridge.py).
    if f("dopfile", False):
        L.append("PROFILE    FILE=2-D")
    else:
        nb = float(f("nb", 5.2e16))
        elem = f("sd_elem", "AS" if ch == "N" else "B")
        dose = float(f("sd_dose", 2e15))
        sd_tox_nm = float(f("sd_tox_nm", 50))
        akev = float(f("sd_akev", 160))
        tmp = float(f("anneal_c", 1050))
        # TIME do card PROFILE é em SEGUNDOS (os exemplos do motor usam 2700,
        # ou seja 45 min). O app antigo rotulava este campo como "recoz. min:",
        # o que era engano de rótulo; ``anneal_min`` segue aceito como alias.
        tim = float(f("anneal_s", p.get("anneal_min", 2700)))
        L.append(f"PROFILE    NB={nb:.2E}  ELEM={elem}  DOSE={dose:.2E}  "
                 f"TOX={sd_tox_nm*1e-7:.3E}  AKEV={akev:g}.")
        L.append(f"+          TEMP={tmp:g}.  TIME={tim:g}")
    # implante de ajuste de Vt
    if f("vt_dose", 0) and float(f("vt_dose", 0)) > 0:
        L.append(f"IMPLANT    ELEM={f('vt_elem','B')}  "
                 f"DOSE={float(f('vt_dose', 0)):.2E}  "
                 f"AKEV={float(f('vt_akev',50)):g}  TEMP=940  TIME=1000")
    nss = p.get("nss", None)
    if nss not in (None, ""):
        L.append(f"INTERFACE  NSS={float(nss):.3E}")
    model = "THRES" if mode == "vth" else "2-D"
    L.append(f"OPTION     MODEL={model}")
    if mode == "op" or f("maps", False):
        out = "ALL=YES PIF=YES"
    elif mode == "iv":
        out = "ALL=YES"
    else:
        out = "NONE=YES"
    L.append(f"OUTPUT     {out}")
    L.append("END")
    return "\n".join(L) + "\n"


def write_2d_profile(path: str | Path, nd_sub: float = 2.5e13,
                     sd_peak: float = 1.0e20, sd_depth: float = 0.25,
                     vt_dose: float = 0.0, vt_type: str = "B",
                     vt_rp: float = 0.07, vt_drp: float = 0.04,
                     nl: int = 24, nv: int = 24, pl_min: float = -4.0,
                     pl_max: float = 1.0, pv_max: float = 2.0) -> str | Path:
    """Gera um arquivo de perfil de dopagem 2D no formato ``FILE=2-D`` do MINIMOS.

    Formato (REAL*8, Fortran não-formatado, fonte/dreno simétricos, sem
    derivadas)::

        NPIECE(=-1) | NL,NV | PL[NL] | PV[NV] | doador[NV][NL] | aceitador[NV][NL]

    Geometria validada: ``PL`` é a posição lateral medida da borda da porta (0),
    NEGATIVA em direção ao contato da fonte — é o que faz o motor localizar a
    junção e a subdifusão da fonte (senão aborta com ``SOURCE ... NOT FOUND``).
    """
    pl_um = [pl_min + i * ((pl_max - pl_min) / (nl - 1)) for i in range(nl)]
    pv_um = [i * (pv_max / (nv - 1)) for i in range(nv)]
    pl = [p * 1e-4 for p in pl_um]   # µm -> cm
    pv = [p * 1e-4 for p in pv_um]

    def sd_boron(y):
        return sd_peak * math.exp(-(y / sd_depth) ** 2)

    def lateral(plv):
        return 1.0 if plv <= 0 else math.exp(-(plv / 0.3) ** 2)

    def vt(y):
        if vt_dose <= 0:
            return 0.0
        return vt_dose / (math.sqrt(2 * math.pi) * vt_drp * 1e-4) * \
            math.exp(-((y - vt_rp) / vt_drp) ** 2)

    donor = [[nd_sub + (vt(pv_um[v]) if vt_type.upper().startswith("P") else 0.0)
              for _ in range(nl)] for v in range(nv)]
    accep = [[sd_boron(pv_um[v]) * lateral(pl_um[l]) +
              (vt(pv_um[v]) if vt_type.upper().startswith("B") else 0.0)
              for l in range(nl)] for v in range(nv)]

    def reci(*xs):
        b = b"".join(struct.pack("<i", v) for v in xs)
        return struct.pack("<i", len(b)) + b + struct.pack("<i", len(b))

    def recd(xs):
        b = b"".join(struct.pack("<d", v) for v in xs)
        return struct.pack("<i", len(b)) + b + struct.pack("<i", len(b))

    with open(path, "wb") as f:
        f.write(reci(-1))
        f.write(reci(nl, nv))
        f.write(recd(pl))
        f.write(recd(pv))
        for v in range(nv):
            f.write(recd(donor[v]))
        for v in range(nv):
            f.write(recd(accep[v]))
    return path
