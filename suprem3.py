#!/usr/bin/env python3
"""
SUPREM-III Studio — SyncField Corporation
GUI para simulação de processos semicondutores usando SUPREM-III via DOSBox.
O DOSBox roda em background — o usuário não precisa interagir com ele.

Requisitos: Python 3.8+, matplotlib, DOSBox instalado no sistema.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import subprocess, tempfile, shutil, platform, os, re, sys, json, threading
from pathlib import Path

# ── Tenta importar matplotlib (instalado pelo installer) ──
try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.ticker as ticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ═══════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════════

APP_NAME = "SUPREM-III Studio"
APP_VERSION = "1.0.0"
IS_WIN = platform.system() == "Windows"

# Pasta base: ao lado deste script
BASE_DIR = Path(__file__).parent.resolve()
SUPREM_DIR = BASE_DIR / "suprem_engine"
CONFIG_FILE = BASE_DIR / "config.json"
EXE = ".exe" if IS_WIN else ""
# Pasta onde os arquivos .out de cada simulação ficam salvos (para relatórios)
RESULTS_DIR = BASE_DIR / "resultados"
# Pasta com os binários NATIVOS (setup/genii/sup3) compilados do fonte Stanford.
# Quando presente e inicializada, é usada no lugar do DOSBox (Linux e Windows).
SUPREM_NATIVE_DIRS = [
    BASE_DIR / "suprem-run",
    BASE_DIR / "suprem_native" / "suprem-run",
    BASE_DIR / "native" / "suprem-run",
]
# Nomes lógicos dos arquivos de dados que viram variáveis de ambiente
_NATIVE_ENV_FILES = ["S3cof0", "S3err0", "S3fky0", "S3uky0",
                     "S3ibo0", "S3ibo1", "S3ibf0", "S3iph0", "S3ias0", "S3isb0"]

# Cores SyncField
COL = {
    "bg": "#1a1410", "bg2": "#221d17", "bg3": "#2e261e",
    "fg": "#e8dcc8", "dim": "#8a7a68", "accent": "#c43c2c",
    "warm": "#d4a574", "border": "#3a3228",
    "entry_bg": "#161210", "entry_fg": "#e8dcc8",
    "btn": "#c43c2c", "btn_fg": "#ffffff",
}

# ═══════════════════════════════════════════════════════════════
# DETECÇÃO DO DOSBOX
# ═══════════════════════════════════════════════════════════════

def find_dosbox():
    """Procura o executável do DOSBox no sistema."""
    # 1) Config salva
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            p = cfg.get("dosbox_path", "")
            if p and Path(p).exists():
                return p
        except:
            pass
    # 2) PATH
    for name in ["dosbox", "dosbox-x", "dosbox-staging"]:
        path = shutil.which(name)
        if path:
            return path
    # 3) Caminhos comuns (Windows)
    if IS_WIN:
        for p in [
            r"C:\Program Files (x86)\DOSBox-0.74-3\DOSBox.exe",
            r"C:\Program Files\DOSBox-0.74-3\DOSBox.exe",
            r"C:\Program Files (x86)\DOSBox-0.74\DOSBox.exe",
            r"C:\Program Files\DOSBox\DOSBox.exe",
            r"C:\DOSBox\DOSBox.exe",
        ]:
            if Path(p).exists():
                return p
    return None

def save_dosbox_path(path):
    cfg = {}
    if CONFIG_FILE.exists():
        try: cfg = json.loads(CONFIG_FILE.read_text())
        except: pass
    cfg["dosbox_path"] = str(path)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

def find_minimos_dir():
    """Pasta do MINIMOS (com mm_pl[.exe] + stack.rul). Config salva > empacotada > comuns."""
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text())
            p = cfg.get("minimos_dir", "")
            if p and (Path(p) / ("mm_pl" + EXE)).exists():
                return Path(p)
        except Exception:
            pass
    cands = [BASE_DIR / "minimos-run",                       # motor empacotado (build nativo)
             BASE_DIR / "minimos" / "bin", BASE_DIR / "minimoswin6_1" / "bin",
             BASE_DIR / "bin"]
    if IS_WIN:
        cands += [Path(r"C:\minimos\bin"), Path(r"C:\minimoswin6_1\bin")]
    for c in cands:
        if (c / ("mm_pl" + EXE)).exists():
            return c
    return None

def save_minimos_dir(path):
    cfg = {}
    if CONFIG_FILE.exists():
        try: cfg = json.loads(CONFIG_FILE.read_text())
        except Exception: pass
    cfg["minimos_dir"] = str(path)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# Mapa de unidades FORTRAN -> extensão de arquivo, idêntico ao bin/minimos.bat
# (Compaq Visual Fortran usa variáveis de ambiente FORTnn para nomear as unidades)
MINIMOS_UNIT_EXT = {
    1: "i3d", 2: "bin", 15: "inp", 16: "out", 30: "asciipif",
    40: "mtv", 41: "mcm", 61: "iv", 71: "gch", 72: "pvd", 73: "etp",
    74: "hci", 75: "hci", 76: "hco", 77: "hcd", 80: "uai", 82: "tra",
    84: "tgr", 85: "tpp", 86: "grx", 87: "bbt", 88: "csh", 89: "lpf",
}

def check_minimos(mdir):
    """Lista de problemas que impedem rodar o MINIMOS (vazia = ok)."""
    problems = []
    if mdir is None:
        return ["pasta do MINIMOS não definida"]
    mdir = Path(mdir)
    exe = mdir / ("mm_pl" + EXE)
    if not exe.exists():
        problems.append(f"mm_pl{EXE} não encontrado em {mdir}")
    if not (mdir / "stack.rul").exists():
        problems.append("stack.rul não encontrado (regra de empilhamento obrigatória)")
    # binário Win32 (Compaq) só roda no Windows; binário nativo (gfortran) roda no SO atual
    if not IS_WIN and exe.exists() and _is_pe_executable(exe):
        problems.append("o mm_pl encontrado é Win32 (.exe Compaq) — recompile com build_minimos.sh para rodar no Linux")
    return problems

def _is_pe_executable(path):
    """True se o arquivo é um executável Windows PE (assinatura 'MZ')."""
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"MZ"
    except Exception:
        return False

def run_minimos(inp_text, mdir, base="mm_run", screen="o", dopfile=None,
                callback_done=None, callback_error=None):
    """Roda o MINIMOS de forma portável (Linux gfortran e Windows Compaq/gfortran).

    Mecanismo duplo de arquivos, para funcionar com qualquer binário:
      • gfortran abre as unidades sem FILE= -> usa nomes padrão fort.NN
        (fort.15 entrada, fort.16 saída, fort.31 stack, fort.61 I-V, un.6 = stdout)
      • Compaq Visual Fortran usa variáveis de ambiente FORTnn -> base.ext
    Preparamos os dois (fort.NN no diretório + variáveis FORTnn), então o
    mesmo código serve para ambos. A referência (unidade 6) é capturada do stdout.
    """
    mdir = Path(mdir)
    def _run():
        work = None
        try:
            exe = mdir / ("mm_pl" + EXE)
            if not exe.exists():
                raise RuntimeError(f"mm_pl{EXE} não encontrado em {mdir}")
            if not (mdir / "stack.rul").exists():
                raise RuntimeError("stack.rul não encontrado")
            if not IS_WIN and _is_pe_executable(exe):
                raise RuntimeError("mm_pl é Win32 (.exe) — recompile com build_minimos.sh para Linux")
            work = Path(tempfile.mkdtemp(prefix="minimos_"))
            # --- convenção gfortran: fort.NN no diretório de trabalho ---
            (work / "fort.15").write_text(inp_text, encoding="ascii", errors="replace")
            shutil.copy2(mdir / "stack.rul", work / "fort.31")
            if dopfile and Path(dopfile).exists():
                shutil.copy2(dopfile, work / "fort.20")
            # --- convenção Compaq: nomes base.ext + variáveis FORTnn ---
            (work / f"{base}.inp").write_text(inp_text, encoding="ascii", errors="replace")
            env = dict(os.environ)
            for unit, ext in MINIMOS_UNIT_EXT.items():
                env[f"FORT{unit}"] = f"{base}.{ext}"
            env["FORT20"] = str(dopfile) if dopfile else "NUL"
            env["FORT31"] = str((mdir / "stack.rul").resolve())
            creat = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
            # roda; stdout = referência (unidade 6)
            ref_path = work / f"{base}.ref"
            with open(ref_path, "w") as reff:
                rc = subprocess.run([str(exe.resolve())], cwd=str(work), env=env,
                                    stdout=(reff if screen != "y" else None),
                                    stderr=subprocess.STDOUT, timeout=1800,
                                    creationflags=creat).returncode
            def rd(*names):
                for n in names:
                    f = work / n
                    if f.exists() and f.stat().st_size > 0:
                        return f.read_text(encoding="latin1", errors="replace")
                return None
            result = {
                "out": rd("fort.16", f"{base}.out"),
                "ref": rd(f"{base}.ref"),
                "iv":  rd("fort.61", f"{base}.iv"),
                "mtv": rd("fort.40", f"{base}.mtv"),
                "pif": rd("fort.30", f"{base}.asciipif"),
                "returncode": rc, "stages": ["mm_pl (planar)"],
                "files": sorted(p.name for p in work.iterdir() if p.is_file()),
            }
            # persiste em resultados/ com nomes amigáveis
            try:
                stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = RESULTS_DIR / f"minimos_{base}_{stamp}"
                dest.mkdir(parents=True, exist_ok=True)
                # mapeia fort.NN -> extensão amigável ao salvar
                inv = {f"fort.{u}": ext for u, ext in MINIMOS_UNIT_EXT.items()}
                for p in work.iterdir():
                    if not p.is_file():
                        continue
                    name = f"{base}.{inv[p.name]}" if p.name in inv else p.name
                    shutil.copy2(p, dest / name)
                result["__dir__"] = str(dest)
            except Exception:
                result["__dir__"] = None
            if callback_done:
                callback_done(result)
        except Exception as e:
            if callback_error:
                callback_error(str(e))
        finally:
            if work and work.exists():
                shutil.rmtree(work, ignore_errors=True)
    threading.Thread(target=_run, daemon=True).start()

def write_minimos_2d_profile(path, nd_sub=2.5e13, sd_peak=1.0e20, sd_depth=0.25,
                             vt_dose=0.0, vt_type="B", vt_rp=0.07, vt_drp=0.04,
                             nl=24, nv=24, pl_min=-4.0, pl_max=1.0, pv_max=2.0):
    """Gera um arquivo de perfil de dopagem 2D no formato FILE=2-D do MINIMOS,
    para um MOSFET (PMOS: substrato N + fonte/dreno boro).

    Formato (REAL*8, Fortran não-formatado, fonte/dreno simétricos, sem derivadas):
        NPIECE(=-1) | NL,NV | PL[NL] | PV[NV] | doador[NV][NL] | aceitador[NV][NL]
    Geometria validada: PL é a posição lateral medida da borda da porta (0),
    NEGATIVA em direção ao contato da fonte — é o que faz o motor localizar a
    junção e a subdifusão da fonte (senão aborta com 'SOURCE ... NOT FOUND').
    """
    import struct, math
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

def build_minimos_deck(p):
    """Gera o texto de um deck MINIMOS a partir de um dicionário de parâmetros
    (usado pelo construtor visual). Unidades de entrada amigáveis: TOX/profundidades
    em nm, W/L em µm; converte para cm no deck. Cobre NMOS (perfil analítico) e
    PMOS (PROFILE FILE=2-D — o perfil 2-D é gerado à parte pelo painel PMOS).
    Modos: 'vth' (MODEL=THRES), 'op' (ponto de operação 2-D, com mapas p/ 3D),
    'iv' (varredura STEP para curva I-V)."""
    def f(key, default): return p.get(key, default)
    ch = (f("channel", "N") or "N").upper()[:1]
    ch = "P" if ch == "P" else "N"
    gate = f("gate", "NPOLY" if ch == "N" else "PPOLY")
    tox_nm = float(f("tox_nm", 15))
    w_um = float(f("w_um", 1.0)); l_um = float(f("l_um", 0.85))
    mode = f("mode", "iv")
    title = f("title", "Deck gerado pelo construtor MINIMOS")
    L = [f"* {title}",
         f"DEVICE     CHANNEL={ch}  GATE={gate}  TOX={tox_nm*1e-7:.3E}  "
         f"W={w_um*1e-4:.3E}  L={l_um*1e-4:.3E}"]
    # polarização
    sgn = 1.0 if ch == "N" else -1.0
    ud = float(f("ud", 0.1)) * (sgn if f("auto_sign", True) else 1.0)
    bias = f"BIAS       UD={ud:g}"
    for k, key in (("UG", "ug"), ("US", "us"), ("UB", "ub")):
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
    # perfil
    if ch == "P":
        L.append("PROFILE    FILE=2-D")
    else:
        nb = float(f("nb", 5.2e16)); elem = f("sd_elem", "AS")
        dose = float(f("sd_dose", 2e15)); sd_tox_nm = float(f("sd_tox_nm", 50))
        akev = float(f("sd_akev", 160)); tmp = float(f("anneal_c", 1050)); tim = float(f("anneal_min", 2700))
        L.append(f"PROFILE    NB={nb:.2E}  ELEM={elem}  DOSE={dose:.2E}  "
                 f"TOX={sd_tox_nm*1e-7:.3E}  AKEV={akev:g}.")
        L.append(f"+          TEMP={tmp:g}.  TIME={tim:g}")
    # implante de ajuste de Vt (opcional, só faz sentido no caminho analítico/N)
    if ch == "N" and f("vt_dose", 0) and float(f("vt_dose", 0)) > 0:
        L.append(f"IMPLANT    ELEM={f('vt_elem','B')}  DOSE={float(f('vt_dose', 0)):.2E}  "
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

def parse_minimos_pif(pif_text):
    """Lê o arquivo PIF (fort.30) do MINIMOS e extrai a grade estruturada e os
    campos físicos definidos sobre ela. Retorna (lat, vert, campos) onde lat/vert
    são as posições (µm) dos eixos e campos é {rótulo: matriz[nv][nl]}.

    É a 'ressurreição' do gráfico 3D: o MINIMOS gera estes dados, mas o
    visualizador antigo (plotmtv) não existe mais — aqui lemos direto o arquivo.
    Identificamos cada campo pelo NOME do atributo (o attributeType às vezes vem
    rotulado de forma inconsistente) e só expomos os campos da grade completa.
    """
    if not pif_text:
        return [], [], {}
    import re as _re
    fnum = _re.compile(r'[-+]?\d+\.\d+E[-+]?\d+')

    def floats_before_semicolon(block):
        out = []
        for line in block.splitlines():
            for m in fnum.findall(line.split(";")[0]):
                out.append(float(m))
        return out

    lat, vert = [], []
    if "(axes" in pif_text:
        ax = pif_text.split("(axes", 1)[1]
        parts = ax.split("(valueList")
        if len(parts) >= 3:
            vert = floats_before_semicolon(parts[1][:parts[1].find(")")])
            lat = floats_before_semicolon(parts[2][:parts[2].find(")")])
    nl, nv = len(lat), len(vert)
    n = nl * nv
    campos = {}
    if n == 0:
        return lat, vert, campos
    # nome do atributo no PIF -> rótulo amigável (só campos escalares na grade cheia)
    alvos = [
        ("ElectrostaticPotential", "Potencial (V)"),
        ("SpaceChargeConcentration", "Carga espacial (cm⁻³)"),
        ("ElectricField_", "Campo elétrico |E| (V/cm)"),
        ("ElectricFieldLateral", "Campo elétrico lateral (V/cm)"),
        ("ElectricFieldVertical", "Campo elétrico vertical (V/cm)"),
    ]
    for nome, rotulo in alvos:
        i = pif_text.find("(attribute " + nome)
        if i < 0:
            continue
        blk = pif_text[i:]
        if "(valueList" not in blk:
            continue
        vlist = blk.split("(valueList", 1)[1]
        end = vlist.find("))")
        vals = floats_before_semicolon(vlist[:end if end > 0 else len(vlist)])
        if len(vals) == n:                      # só a grade completa (nv x nl)
            campos[rotulo] = vals
    return lat, vert, campos

def parse_minimos_iv(iv_text):
    """Lê o arquivo .iv (fort.61) do MINIMOS. Formato real:
        ##  UB (V)  UD (V)  UG (V)  US (V)  IB (A)  ID (A)  IG (A)  IS (A)
        <linhas numéricas>
    Devolve (headers, rows). headers são nomes curtos (UB, UD, ..., IS)."""
    if not iv_text:
        return [], []
    headers, rows = [], []
    for ln in iv_text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("##") or (not headers and re.search(r"[A-Za-z]", s) and "(" in s):
            # cabeçalho: pega os rótulos antes dos parênteses (UB, UD, ...)
            headers = re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*\(", s)
            continue
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eEdD][-+]?\d+)?", s)
        if len(nums) >= 2:
            try:
                rows.append(tuple(float(x.replace("D", "E").replace("d", "e")) for x in nums))
            except ValueError:
                pass
    if rows:
        from collections import Counter
        ncol = Counter(len(r) for r in rows).most_common(1)[0][0]
        rows = [r for r in rows if len(r) == ncol]
        if headers and len(headers) != ncol:
            headers = []  # cabeçalho não casa com os dados; ignora
    return headers, rows

# ═══════════════════════════════════════════════════════════════
# GERADOR E PARSER DE .IN
# ═══════════════════════════════════════════════════════════════

AMBIENTS = ["DRYO2","WETO2","NITROGEN","BORON","PHOSPHOR","ARSENIC","ANTIMONY"]
DOPANTS = ["BORON","PHOSPHOR","ARSENIC","ANTIMONY","BF2"]
MATERIALS = ["SILICON","OXIDE","NITRIDE","ALUMINUM","POLYSILI"]

def step_to_code(step):
    t, p = step["type"], step["params"]
    if t == "INITIALIZE":
        s = f"INITIALIZE SILICON <{p.get('orientation','100')}>"
        if p.get("dopant"): s += f" {p['dopant']} CONCENTR={p.get('concentration','1E15')}"
        s += f" DX={p.get('dx','5E-3')}\n+ THICKNES={p.get('thickness','0.5')}"
        return s
    if t == "DIFFUSION":
        s = f"DIFFUSION {p['ambient']} TEMPERAT={p['temperature']} TIME={p['time']}"
        if p.get("gasConc"): s += f" GAS.CONC={p['gasConc']}"
        if p.get("solidSol"): s += " SOLIDSOL"
        if p.get("tRate"): s += f" T.RATE={p['tRate']}"
        return s
    if t == "DEPOSITION":
        s = f"DEPOSITION {p['material']} THICKNES={p['thickness']}"
        if p.get("dopant"): s += f" {p['dopant']}"
        if p.get("concentration"): s += f" CONCENTR={p['concentration']}"
        if p.get("temperature"): s += f" TEMPERAT={p['temperature']}"
        return s
    if t == "ETCH":
        return f"ETCH {p['material']}" + ("" if p.get("all") else f" THICKNES={p.get('thickness','')}")
    if t == "IMPLANTI":
        s = f"IMPLANTI {p['dopant']} ENERGY={p['energy']} DOSE={p['dose']}"
        if p.get("distribution"): s += f" {p['distribution']}"
        return s
    if t == "EPITAXY":
        s = f"EPITAXY {p['dopant']} THICKNES={p['thickness']} CONCENTR={p['concentration']}"
        s += f"\n+TEMPERAT={p['temperature']} GROWTH.R={p.get('growthRate','0.5')}"
        return s
    if t == "PRINT":
        s = f"PRINT {p.get('what','NET')}"
        if p.get("curve"): s += f" {p['curve']}"
        if p.get("extra"): s += f" {p['extra']}"
        if p.get("filename"): s += f" FILENAME={p['filename']}"
        if p.get("linespa"): s += f" LINES/PA={p['linespa']}"
        return s
    if t == "PLOT":
        s = f"PLOT {p.get('what','NET')} {p.get('curve','ACTIVE')}"
        if p.get("xmax"): s += f" XMAX={p['xmax']}"
        if p.get("cmin"): s += f" CMIN={p['cmin']}"
        if p.get("cmax"): s += f" CMAX={p['cmax']}"
        return s
    return ""

def build_in_file(title, steps):
    lines = [f"TITLE {title}"]
    for step in steps:
        c = step_to_code(step)
        if c: lines.append(c)
    lines.append("STOP")
    text = "\r\n".join(lines) + "\r\n"
    # Normalizar: qualquer \n sozinho vira \r\n (corrige continuações multi-linha)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text

_SUPREM_DOPANTS = ["Boron", "Phosphorus", "Arsenic", "Antimony"]

def _dopants_in_steps(steps):
    """Detecta quais dopantes aparecem no processo (para imprimir o perfil deles)."""
    found = []
    blob = " ".join(str(v) for s in steps for v in (s.get("params", {}) or {}).values()).upper()
    for d in _SUPREM_DOPANTS:
        if d.upper()[:5] in blob or d.upper() in blob:
            found.append(d)
    return found

def _detect_junctions(data, min_pts=3, min_mag=1e16):
    """Detecta junções reais num perfil net (lista de (prof, net_com_sinal)).
    Uma troca de sinal só conta como junção se, dos DOIS lados, o tipo persistir
    por pelo menos `min_pts` pontos e a magnitude atingir `min_mag` — assim
    ignoramos o artefato da superfície (óxido→Si) e slivers numéricos finos."""
    juncs = []
    n = len(data)
    for i in range(1, n):
        a, b = data[i - 1][1], data[i][1]
        if a * b >= 0:
            continue
        left = [data[j][1] for j in range(max(0, i - min_pts), i)]
        right = [data[j][1] for j in range(i, min(n, i + min_pts))]
        if len(left) < min_pts or len(right) < min_pts:
            continue
        if not (all(v * a > 0 for v in left) and all(v * b > 0 for v in right)):
            continue
        if max(abs(v) for v in left) < min_mag or max(abs(v) for v in right) < min_mag:
            continue
        xj = data[i - 1][0] + (data[i][0] - data[i - 1][0]) * abs(a) / (abs(a) + abs(b))
        juncs.append(xj)
    return juncs

def build_profile_deck(title, steps):
    """Monta um deck do SUPREM inserindo PRINT após CADA etapa de processo, para
    capturar a evolução do perfil. Retorna (texto_do_deck, plano) onde plano é a
    lista ordenada de (rótulo_da_etapa, quantidade) correspondente a cada bloco
    'depth concentration' que sairá no OUTPUT — na mesma ordem."""
    dopants = _dopants_in_steps(steps) or ["Boron", "Phosphorus"]
    proc = {"INITIALIZE", "DIFFUSION", "IMPLANTI", "DEPOSITION", "ETCH", "EPITAXY"}
    lines = [f"TITLE {title}"]
    plan = []
    n = 0
    nice = {"INITIALIZE": "Substrato", "DIFFUSION": "Difusão", "IMPLANTI": "Implante",
            "DEPOSITION": "Deposição", "ETCH": "Corrosão", "EPITAXY": "Epitaxia"}
    for step in steps:
        t = (step.get("type") or "").upper()
        if t in ("PRINT", "PLOT", "STOP"):
            continue                              # ignoramos prints do usuário aqui
        code = step_to_code(step)
        if not code:
            continue
        lines.append(code)
        if t in proc:
            n += 1
            pr = step.get("params", {}) or {}
            extra = ""
            if t == "DIFFUSION" and pr.get("ambient"):
                extra = f" {pr['ambient']}"
            elif t == "IMPLANTI" and pr.get("dopant"):
                extra = f" {pr['dopant']}"
            label = f"{n}. {nice.get(t, t.capitalize())}{extra}"
            lines.append("PRINT Net Active Concentration")
            plan.append((label, "Net"))
            for d in dopants:
                lines.append(f"PRINT {d} Chemical Concentration")
                plan.append((label, d))
    lines.append("STOP")
    text = "\r\n".join(lines).replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    return text, plan

def parse_suprem_profiles(out_text):
    """Extrai todos os blocos 'depth concentration' do OUTPUT.OUT, em ordem.
    Retorna lista de (depth[], conc[]) — profundidade em µm, concentração em cm^-3
    (o 'net' vem com sinal: + tipo N, - tipo P)."""
    if not out_text:
        return []
    txt = out_text.replace("\f", "")
    blocks = []
    lines = txt.split("\n")
    i = 0
    while i < len(lines):
        if "depth" in lines[i].lower() and "concentration" in lines[i].lower():
            depth, conc = [], []
            i += 1
            while i < len(lines):
                m = re.findall(r'[-+]?\d*\.\d+(?:E[-+]?\d+)?', lines[i])
                if len(m) >= 2:
                    try:
                        depth.append(float(m[0])); conc.append(float(m[1]))
                    except ValueError:
                        break
                    i += 1
                else:
                    break
            if depth:
                blocks.append((depth, conc))
        else:
            i += 1
    return blocks

def parse_in_file(text):
    steps, title = [], "SIMULACAO"
    raw = text.replace("\r\n","\n").replace("\r","\n").split("\n")
    joined = []
    for line in raw:
        t = line.strip()
        if not t or t.startswith("$") or t.upper().startswith("COMMENT"): continue
        if t.startswith("+"):
            if joined: joined[-1] += " " + t[1:].strip()
        else: joined.append(t)

    def gp(tokens, key):
        # casa KEY=valor aceitando abreviacao nos DOIS sentidos
        # (CONCENTRATION= casa com CONCENTR, e vice-versa). Minimo 4 chars.
        K = key.upper()
        for t in tokens:
            if "=" not in t:
                continue
            k, _, v = t.partition("=")
            ku = k.upper()
            n = min(len(ku), len(K))
            if n >= 4 and (ku.startswith(K[:n]) and K.startswith(ku[:n])):
                return v
        return ""
    def has(tokens, key): return any(t.upper()==key.upper() for t in tokens)
    def _alias(tok, name):
        # prefixo em qualquer sentido, minimo 3 chars (BF2 tem 3)
        a, b = tok.upper(), name.upper()
        n = min(len(a), len(b))
        return n >= 3 and a[:n] == b[:n]
    def fin(tokens, lst):
        for t in tokens:
            for x in lst:
                if _alias(t, x):
                    return x.upper()
        return ""
    def ori(tokens):
        for t in tokens:
            m = re.match(r"<(\d+)>", t)
            if m: return m.group(1)
        return "100"

    # aliases de comando: dialeto Stanford -> tipo interno do Studio
    CMD_ALIAS = {"DEPOSIT": "DEPOSITION", "DEPOSITION": "DEPOSITION",
                 "IMPLANT": "IMPLANTI", "IMPLANTI": "IMPLANTI",
                 "INITIALIZE": "INITIALIZE", "DIFFUSION": "DIFFUSION",
                 "ETCH": "ETCH", "EPITAXY": "EPITAXY", "EPITAXI": "EPITAXY",
                 "PRINT": "PRINT", "PLOT": "PLOT", "TITLE": "TITLE", "STOP": "STOP"}

    for line in joined:
        tokens = line.split()
        if not tokens: continue
        raw_cmd = tokens[0].upper()
        cmd = CMD_ALIAS.get(raw_cmd, raw_cmd)
        rest = tokens[1:]
        if cmd == "TITLE": title = " ".join(rest)
        elif cmd == "INITIALIZE":
            steps.append({"type":"INITIALIZE","params":{"orientation":ori(rest),"dopant":fin(rest,DOPANTS),
                "concentration":gp(rest,"CONCENTRATION") or "1E15","dx":gp(rest,"DX") or "5E-3","thickness":gp(rest,"THICKNESS") or "0.5"}})
        elif cmd == "DIFFUSION":
            gc = gp(rest,"GAS.CONC") or gp(rest,"GAS.CON")
            steps.append({"type":"DIFFUSION","params":{"ambient":fin(rest,AMBIENTS),"temperature":gp(rest,"TEMPERATURE") or "1000",
                "time":gp(rest,"TIME") or "15","gasConc":gc,"solidSol":has(rest,"SOLIDSOL") or has(rest,"SOLIDSOLUBILITY"),"tRate":gp(rest,"T.RATE")}})
        elif cmd == "DEPOSITION":
            steps.append({"type":"DEPOSITION","params":{"material":fin(rest,MATERIALS) or "OXIDE","thickness":gp(rest,"THICKNESS") or "0.1",
                "dopant":fin(rest,DOPANTS),"concentration":gp(rest,"CONCENTRATION"),"temperature":gp(rest,"TEMPERATURE")}})
        elif cmd == "ETCH":
            steps.append({"type":"ETCH","params":{"material":fin(rest,MATERIALS) or "OXIDE","all":has(rest,"ALL") or not gp(rest,"THICKNESS"),"thickness":gp(rest,"THICKNESS")}})
        elif cmd == "IMPLANTI":
            steps.append({"type":"IMPLANTI","params":{"dopant":fin(rest,DOPANTS) or "BORON","energy":gp(rest,"ENERGY") or "45",
                "dose":gp(rest,"DOSE") or "1E13","distribution":fin(rest,["GAUSSIAN","PEARSON","BOLTZMAN","2-GAUSSI"])}})
        elif cmd == "EPITAXY":
            steps.append({"type":"EPITAXY","params":{"dopant":fin(rest,DOPANTS) or "PHOSPHOR","thickness":gp(rest,"THICKNESS") or "1.0",
                "concentration":gp(rest,"CONCENTRATION") or "5E15","temperature":gp(rest,"TEMPERATURE") or "1000","growthRate":gp(rest,"GROWTH.R") or "0.5"}})
        elif cmd == "PRINT":
            steps.append({"type":"PRINT","params":{"what":fin(rest,["NET","BORON","PHOSPHOR","ARSENIC","ANTIMONY","ALL","OXIDE"]) or "NET",
                "curve":fin(rest,["ACTIVE","CHEMICAL"]),"extra":fin(rest,["CONCENTR","LAYER","IMPURITY","MATERIAL","OXIDATIO"]),
                "filename":gp(rest,"FILENAME") or "OUTPUT.OUT","linespa":gp(rest,"LINES/PA")}})
        elif cmd == "PLOT":
            steps.append({"type":"PLOT","params":{"what":fin(rest,["NET","BORON","PHOSPHOR","ARSENIC","ANTIMONY","TOTAL"]) or "NET",
                "curve":fin(rest,["ACTIVE","CHEMICAL"]) or "ACTIVE","xmax":gp(rest,"XMAX"),"cmin":gp(rest,"CMIN"),"cmax":gp(rest,"CMAX")}})
        elif cmd == "STOP": break
    return title, steps

def parse_out_file(text):
    """Extrai o perfil profundidade x concentração da tabela gerada por
    'PRINT ... CONCENTRATION'. A tabela vem em 3 pares (depth, concentration)
    por linha e pode ocupar várias páginas. A concentração é NET (com sinal:
    + = tipo n, - = tipo p). Retorna lista [(profundidade_um, concentracao), ...]
    ordenada por profundidade. Se não houver tabela de perfil, retorna []."""
    lines = text.replace("\r", "").split("\n")
    pts = []
    in_profile = False
    num_re = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
    for raw in lines:
        low = raw.lower()
        # cabeçalho da tabela de perfil: "depth   concentration ..."
        if "depth" in low and "concentration" in low:
            in_profile = True
            continue
        if not in_profile:
            continue
        s = raw.strip()
        if not s:
            continue
        # sai do modo perfil ao encontrar texto que não seja dado numérico
        if re.search(r"[A-Za-z]", s) and "e" not in low.replace("net", "").replace("chemical", ""):
            # linhas como "Net Chemical" (cabeçalho de página) — continuar
            if low.strip() in ("net chemical", "net active", "net", "chemical", "active"):
                continue
        nums = num_re.findall(s)
        if len(nums) < 2:
            continue
        try:
            vals = [float(x) for x in nums]
        except ValueError:
            continue
        # processa em pares (profundidade, concentração)
        ok = False
        for i in range(0, len(vals) - 1, 2):
            d, c = vals[i], vals[i + 1]
            if 0.0 <= d < 1e4 and abs(c) > 1e9:
                pts.append((d, c))
                ok = True
        # se a linha não rendeu nenhum par válido e tem letras, encerra a tabela
        if not ok and re.search(r"[A-Za-z]", s) and low.strip() not in (
                "net chemical", "net active", "net", "chemical", "active"):
            in_profile = False
    pts.sort(key=lambda p: p[0])
    return pts

# ═══════════════════════════════════════════════════════════════
# VERIFICAÇÃO DE INTEGRIDADE DOS BINÁRIOS
# ═══════════════════════════════════════════════════════════════

def check_exe_integrity(path):
    """Verifica se um EXE MS-DOS está íntegro (cabeçalho MZ, sem setores
    zerados internos, entry point com código). Retorna (ok, mensagem)."""
    import struct
    try:
        d = path.read_bytes()
    except Exception as e:
        return False, f"não foi possível ler: {e}"
    n = len(d)
    if n < 32 or d[:2] != b"MZ":
        return False, "não é um executável MS-DOS válido (sem assinatura MZ)"
    last_page = struct.unpack("<H", d[2:4])[0]
    pages     = struct.unpack("<H", d[4:6])[0]
    ip        = struct.unpack("<H", d[20:22])[0]
    cs        = struct.unpack("<H", d[22:24])[0]
    hdr       = struct.unpack("<H", d[8:10])[0] * 16
    declared  = (pages - 1) * 512 + (last_page if last_page else 512)
    if declared != n:
        return False, f"truncado: cabeçalho declara {declared} bytes, arquivo tem {n}"
    entry = hdr + cs * 16 + ip
    if entry + 16 <= n and all(b == 0 for b in d[entry:entry + 16]):
        return False, "entry point preenchido com zeros (setores perdidos do disquete)"
    # buracos de zeros >= 512 bytes dentro da imagem de carga
    holes = 0
    i = 0
    while i < declared - 32:
        if d[i] == 0:
            j = i
            while j < declared and d[j] == 0:
                j += 1
            if j - i >= 512:
                holes += (j - i)
            i = j
        else:
            i += 1
    if holes >= 1024:
        return False, f"{holes} bytes zerados internamente (binário danificado)"
    return True, "íntegro"

def check_engine(engine_dir):
    """Verifica os executáveis essenciais. Retorna lista de problemas (vazia = OK)."""
    problems = []
    for name in ("S3GEN.EXE", "SUPREM3.EXE"):
        p = engine_dir / name
        if not p.exists():
            problems.append(f"{name}: ausente")
            continue
        ok, msg = check_exe_integrity(p)
        if not ok:
            problems.append(f"{name}: {msg}")
    return problems

# ═══════════════════════════════════════════════════════════════
# MOTOR DOSBOX (roda em background)
# ═══════════════════════════════════════════════════════════════

def ensure_profile_print(deck):
    """Garante que o deck produza a tabela de perfil (profundidade x concentração)
    para alimentar o gráfico. Se nenhum PRINT com CONCENTRATION existir, injeta
    'Print Net Chemical Concentration' antes do STOP. O PRINT do usuário (ex.:
    Print Layer, com as junções) é preservado — apenas se acrescenta o perfil."""
    lines = deck.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    has_conc = False
    for ln in lines:
        u = ln.upper()
        if u.lstrip().startswith("PRINT") and ("CONCENTR" in u):
            has_conc = True
            break
    if has_conc:
        return deck
    out, inserted = [], False
    for ln in lines:
        if not inserted and ln.strip().upper().startswith("STOP"):
            out.append("Print Net Chemical Concentration")
            inserted = True
        out.append(ln)
    if not inserted:
        out.append("Print Net Chemical Concentration")
        out.append("Stop")
    return "\n".join(out)

def strip_plot(in_content):
    """Remove comandos PLOT (e suas continuações '+') do deck.
    PLOT abre modo gráfico interativo e TRAVA o DOSBox em execução headless.
    A visualização é feita pela aba de Resultados a partir dos .OUT."""
    out_lines = []
    skipping = False
    for raw in in_content.replace("\r\n", "\n").split("\n"):
        stripped = raw.strip()
        if skipping and stripped.startswith("+"):
            continue  # continuação de um PLOT removido
        skipping = stripped.upper().startswith("PLOT")
        if skipping:
            continue
        out_lines.append(raw)
    text = "\n".join(out_lines)
    return text.replace("\n", "\r\n")

def run_suprem(in_content, dosbox_path, callback_done, callback_error):
    """Executa SUPREM-III via DOSBox em background."""
    def _run():
        work = None
        proc = None
        log = []  # debug log
        try:
            import time
            work = Path(tempfile.mkdtemp(prefix="suprem_"))
            log.append(f"work_dir: {work}")
            log.append(f"dosbox: {dosbox_path}")
            log.append(f"engine_dir: {SUPREM_DIR} exists={SUPREM_DIR.exists()}")

            # Copiar engine
            engine_files = []
            if SUPREM_DIR.exists():
                for f in SUPREM_DIR.iterdir():
                    if f.is_file():
                        shutil.copy2(f, work / f.name)
                        engine_files.append(f.name)
            log.append(f"engine_files: {len(engine_files)} copied")
            log.append(f"  has S3GEN.EXE: {'S3GEN.EXE' in engine_files}")
            log.append(f"  has SUPREM3.EXE: {'SUPREM3.EXE' in engine_files}")

            # Verificar integridade dos binários ANTES de tentar rodar
            problems = check_engine(work)
            if problems:
                msg = "Binários do SUPREM-III corrompidos ou ausentes:\n  - " + "\n  - ".join(problems)
                msg += ("\n\nSubstitua os arquivos em 'suprem_engine/' por cópias íntegras "
                        "extraídas do disquete original (drive.flp).")
                log.append(f"INTEGRITY FAIL: {problems}")
                (BASE_DIR / "debug_log.txt").write_text("\n".join(log))
                shutil.rmtree(work, ignore_errors=True)
                callback_error(msg)
                return

            # Remover PLOT (trava o DOSBox em modo headless) e escrever o .IN
            clean_in = strip_plot(in_content)
            (work / "INPUT.IN").write_text(clean_in, encoding="ascii", errors="replace")
            log.append(f"INPUT.IN: {len(clean_in)} bytes written (PLOT removido)")

            # Detectar .OUT esperados
            expected_outs = set()
            for line in clean_in.split("\n"):
                m = re.search(r"FILENAME=(\S+)", line, re.IGNORECASE)
                if m:
                    expected_outs.add(m.group(1).upper())
            # SAIDA.LST é a listagem geral; os perfis vão para os FILENAME= de cada PRINT
            expected_outs.add("SAIDA.LST")
            log.append(f"expected_outs: {expected_outs}")

            # DOSBox config - NÃO usar aspas no mount path no Linux
            conf = work / "_run.conf"
            mount_path = str(work).replace("\\", "/")
            conf_text = f"""[sdl]
fullscreen=false
output=surface

[dosbox]
machine=vgaonly
memsize=16

[cpu]
core=normal
cputype=386
cycles=max

[autoexec]
mount c {mount_path}
c:
if exist s3inicio.tmp del s3inicio.tmp
echo INPUT.IN>>s3inicio.tmp
echo SAIDA.LST>>s3inicio.tmp
s3gen
if exist s3inicio.tmp del s3inicio.tmp
echo SAIDA.LST>>s3inicio.tmp
suprem3
if exist s3prs0 del s3prs0
exit
"""
            conf.write_text(conf_text)
            log.append(f"conf written: {conf}")
            log.append(f"mount path: {mount_path}")

            # Iniciar DOSBox
            cmd = [dosbox_path, "-conf", str(conf)]
            if IS_WIN:
                cmd.append("-noconsole")
            log.append(f"cmd: {cmd}")

            startupinfo = None
            if IS_WIN:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 6

            proc = subprocess.Popen(cmd, cwd=str(work),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    startupinfo=startupinfo if IS_WIN else None)
            log.append(f"DOSBox started, pid={proc.pid}")

            # Poll para .OUT
            max_wait = 90
            elapsed = 0.0
            last_files = ""

            while elapsed < max_wait:
                time.sleep(1.0)
                elapsed += 1.0

                # Listar TODOS os arquivos na pasta
                all_files = {}
                try:
                    for f in work.iterdir():
                        all_files[f.name] = f.stat().st_size
                except:
                    pass

                files_str = str(all_files)
                if files_str != last_files:
                    log.append(f"  t={elapsed:.0f}s files: {all_files}")
                    last_files = files_str

                # Verificar .OUT
                found = set()
                for fname, size in all_files.items():
                    up = fname.upper()
                    if (up.endswith(".OUT") or up.endswith(".TXT") or up.endswith(".LST")) and up != "INPUT.IN" and size > 10:
                        found.add(up)

                if found:
                    log.append(f"  FOUND .OUT files: {found}")

                if expected_outs.issubset(found):
                    log.append(f"  ALL expected .OUT found at t={elapsed:.0f}s!")
                    time.sleep(1.5)
                    break

                # DOSBox saiu?
                ret = proc.poll()
                if ret is not None:
                    log.append(f"  DOSBox exited with code {ret} at t={elapsed:.0f}s")
                    break

            # Matar DOSBox se ainda roda
            if proc.poll() is None:
                log.append(f"Killing DOSBox at t={elapsed:.0f}s")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)

            # DOSBox stderr/stdout
            try:
                stdout = proc.stdout.read().decode(errors="replace")[:500]
                stderr = proc.stderr.read().decode(errors="replace")[:500]
                if stdout.strip(): log.append(f"stdout: {stdout.strip()}")
                if stderr.strip(): log.append(f"stderr: {stderr.strip()}")
            except:
                pass

            # Listar arquivos finais
            final_files = {}
            try:
                for f in work.iterdir():
                    final_files[f.name] = f.stat().st_size
            except:
                pass
            log.append(f"final files: {final_files}")

            # Coletar resultados
            results = {}
            for f in work.iterdir():
                up = f.name.upper()
                if (up.endswith(".OUT") or up.endswith(".TXT") or up.endswith(".LST")) and up != "INPUT.IN":
                    try:
                        raw = f.read_text(encoding="ascii", errors="replace")
                        data = parse_out_file(raw)
                        if data:
                            results[f.name] = {"data": data, "raw": raw}
                            log.append(f"  parsed {f.name}: {len(data)} points")
                        else:
                            log.append(f"  {f.name}: no numeric data (layer info?)")
                            # Include raw text even without numeric data
                            results[f.name] = {"data": [], "raw": raw}
                    except Exception as ex:
                        log.append(f"  {f.name}: read error: {ex}")

            log.append(f"results: {len(results)} files")

            # Salvar debug log
            try:
                (BASE_DIR / "debug_log.txt").write_text("\n".join(log))
            except:
                pass

            # Limpar
            try:
                shutil.rmtree(work)
            except:
                pass

            callback_done(results)

        except Exception as e:
            log.append(f"EXCEPTION: {e}")
            import traceback
            log.append(traceback.format_exc())
            try:
                (BASE_DIR / "debug_log.txt").write_text("\n".join(log))
            except:
                pass
            if proc and proc.poll() is None:
                try:
                    proc.kill()
                except:
                    pass
            if work:
                try:
                    shutil.rmtree(work)
                except:
                    pass
            callback_error(f"{e}\n\nVeja debug_log.txt para detalhes.")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

# ═══════════════════════════════════════════════════════════════
# MOTOR NATIVO (sem DOSBox) — Linux e Windows
# Usa os binários setup/genii/sup3 compilados do fonte Stanford.
# ═══════════════════════════════════════════════════════════════

def find_native_dir():
    """Localiza a pasta com os binários nativos do SUPREM-III, se houver."""
    for c in SUPREM_NATIVE_DIRS:
        if (c / ("sup3" + EXE)).exists() and (c / ("genii" + EXE)).exists():
            return c
    return None

def check_native(run_dir):
    """Confere se o motor nativo está completo e inicializado. Lista problemas."""
    problems = []
    if run_dir is None or not run_dir.exists():
        return ["binários nativos do SUPREM-III não encontrados"]
    for b in ("setup", "genii", "sup3"):
        p = run_dir / (b + EXE)
        if not p.exists():
            problems.append(f"binário ausente: {b}{EXE}")
        elif not IS_WIN and not os.access(p, os.X_OK):
            problems.append(f"sem permissão de execução: {b}")
    for f in ("S3cof0", "S3uky0"):
        if not (run_dir / f).exists():
            problems.append(f"coeficiente ausente: {f} (rode a inicialização)")
    return problems

def run_suprem_native(in_content, run_dir, callback_done, callback_error):
    """Executa setup → genii → sup3 nativamente, em background.
    Entrega callback_done(results) no mesmo formato do backend DOSBox:
        { nome_arquivo: {"data": [(x,y),...], "raw": texto} }"""
    def _run():
        work = None
        log = []
        try:
            rd = Path(run_dir).resolve()
            log.append(f"native run_dir: {rd}")
            problems = check_native(rd)
            if problems:
                callback_error("Motor nativo indisponível:\n  - " + "\n  - ".join(problems))
                return

            work = Path(tempfile.mkdtemp(prefix="suprem_nat_"))
            deck = strip_plot(in_content)
            deck = ensure_profile_print(deck)
            (work / "INPUT.IN").write_text(deck, encoding="ascii", errors="replace")

            env = dict(os.environ)
            for name in _NATIVE_ENV_FILES:
                fp = rd / name
                if fp.exists():
                    env[name] = str(fp)
            # IMPORTANTE: usar nomes RELATIVOS (cwd = pasta de trabalho), igual ao
            # script 'suprem' original. O motor nao lida bem com caminhos absolutos
            # para o arquivo de saida / S3prs0.
            env["S3prs0"] = "S3prs0"

            out_name = "OUTPUT.OUT"
            inf_name = "RUNINFO.TXT"
            out_file = work / out_name

            def run(bin_name, args):
                creat = 0
                if IS_WIN:
                    creat = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                return subprocess.run(
                    [str(rd / (bin_name + EXE))] + args,
                    cwd=str(work), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    timeout=600, creationflags=creat)

            run("setup", ["INPUT.IN", out_name])
            g = run("genii", ["INPUT.IN", out_name, inf_name])
            if g.returncode != 0:
                callback_error("Erro no genii (parser do deck):\n"
                               + g.stdout.decode("latin1", "replace")[-1500:])
                return
            s = run("sup3", [out_name, inf_name])
            if s.returncode != 0:
                callback_error("Erro no sup3 (simulador):\n"
                               + s.stdout.decode("latin1", "replace")[-1500:])
                return

            # Pasta de destino para guardar os .out (nome = título + data/hora)
            import datetime, re as _re
            titulo = "simulacao"
            for line in deck.split("\n"):
                lt = line.strip()
                if lt.lower().startswith("title"):
                    t = lt[5:].strip()
                    if t:
                        titulo = _re.sub(r"[^A-Za-z0-9._-]+", "_", t)[:40].strip("_") or "simulacao"
                    break
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = RESULTS_DIR / f"{titulo}_{stamp}"
            try:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "INPUT.IN").write_text(deck, encoding="ascii", errors="replace")
            except Exception:
                dest = None

            results = {}
            saved_dir = None
            for f in sorted(work.iterdir()):
                up = f.name.upper()
                if up in ("INPUT.IN", inf_name.upper()) or up.startswith("S3PRS0"):
                    continue
                if (up.endswith(".OUT") or up.endswith(".TXT") or up.endswith(".LST")) \
                        and f.is_file() and f.stat().st_size > 10:
                    raw = f.read_text(encoding="latin1", errors="replace")
                    saved_path = None
                    if dest is not None:
                        try:
                            saved_path = dest / f.name
                            shutil.copy2(str(f), str(saved_path))
                            saved_dir = dest
                            saved_path = str(saved_path)
                        except Exception:
                            saved_path = None
                    results[f.name] = {"data": parse_out_file(raw), "raw": raw,
                                       "path": saved_path}
            if saved_dir is not None:
                # marcador para a interface mostrar onde foi salvo
                results["__dir__"] = str(saved_dir)

            try:
                (BASE_DIR / "debug_log.txt").write_text("\n".join(log))
            except Exception:
                pass
            callback_done(results)

        except subprocess.TimeoutExpired:
            callback_error("Tempo esgotado ao executar o SUPREM-III nativo.")
        except Exception as e:
            callback_error(f"Falha no motor nativo: {e}")
        finally:
            if work and work.exists():
                shutil.rmtree(work, ignore_errors=True)

    threading.Thread(target=_run, daemon=True).start()

# ═══════════════════════════════════════════════════════════════
# OXIDAÇÃO — motor síncrono, leitura de espessura e ajuste Deal-Grove
# ═══════════════════════════════════════════════════════════════

def run_native_sync(deck_text, run_dir, timeout=300):
    """Roda setup→genii→sup3 de forma síncrona e devolve o texto do OUTPUT.OUT.
    Lança RuntimeError em caso de falha."""
    rd = Path(run_dir).resolve()
    problems = check_native(rd)
    if problems:
        raise RuntimeError("Motor nativo indisponível: " + "; ".join(problems))
    work = Path(tempfile.mkdtemp(prefix="suprem_ox_"))
    try:
        (work / "INPUT.IN").write_text(strip_plot(deck_text), encoding="ascii", errors="replace")
        env = dict(os.environ)
        for name in _NATIVE_ENV_FILES:
            if (rd / name).exists():
                env[name] = str(rd / name)
        env["S3prs0"] = "S3prs0"
        creat = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
        def run(b, a):
            return subprocess.run([str(rd / (b + EXE))] + a, cwd=str(work), env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=timeout, creationflags=creat)
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

def parse_oxide_thickness(raw):
    """Lê a espessura (µm) da camada de ÓXIDO na tabela 'layer ... material ...'."""
    for line in raw.split("\n"):
        if re.search(r"\bOXIDE\b", line, re.IGNORECASE):
            nums = re.findall(r"\d*\.\d+", line)
            if nums:
                try:
                    return float(nums[0])
                except ValueError:
                    pass
    return None

def deal_grove_fit(times_min, xo_list):
    """Ajuste linear de t/Xo = (1/B)·Xo + A/B (Deal-Grove, τ=0).
    Retorna dict com A (µm), B (µm²/min e µm²/h), B/A (µm/h), R²."""
    xs = list(xo_list)                      # x = Xo
    ys = [t / x for t, x in zip(times_min, xo_list)]   # y = t/Xo
    n = len(xs)
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs); sxy = sum(x * y for x, y in zip(xs, ys))
    den = (n * sxx - sx * sx)
    m = (n * sxy - sx * sy) / den           # 1/B
    c = (sy - m * sx) / n                    # A/B
    ybar = sy / n
    ss_tot = sum((y - ybar) ** 2 for y in ys)
    ss_res = sum((y - (m * x + c)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 1.0
    B_min = 1.0 / m
    A = c * B_min
    B_h = B_min * 60.0
    return {"m": m, "c": c, "B_min": B_min, "B_h": B_h, "A": A,
            "BA_h": B_h / A if A else float("nan"), "r2": r2}

def deal_grove_xo(t_min, A, B_min):
    import math
    return (-A + math.sqrt(A * A + 4 * B_min * t_min)) / 2.0

# ═══════════════════════════════════════════════════════════════
# GUI PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class SupremApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x750")
        self.configure(bg=COL["bg"])
        self.minsize(900, 600)

        self.steps = []
        self.title_var = tk.StringVar(value="SIMULACAO SUPREM-III")
        self.dosbox_path = find_dosbox()
        self.results = {}

        self._build_style()
        self._build_ui()
        self._load_preset_diode()

    def _build_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=COL["bg"], foreground=COL["fg"], fieldbackground=COL["entry_bg"])
        s.configure("TFrame", background=COL["bg"])
        s.configure("TLabel", background=COL["bg"], foreground=COL["fg"])
        s.configure("TButton", background=COL["bg3"], foreground=COL["fg"], padding=6)
        s.map("TButton", background=[("active", COL["accent"])])
        s.configure("Accent.TButton", background=COL["accent"], foreground=COL["btn_fg"], padding=8)
        s.map("Accent.TButton", background=[("active", "#e04830")])
        s.configure("TNotebook", background=COL["bg"])
        s.configure("TNotebook.Tab", background=COL["bg2"], foreground=COL["dim"], padding=[12,6])
        s.map("TNotebook.Tab", background=[("selected", COL["accent"])], foreground=[("selected", "#fff")])
        s.configure("TCombobox", fieldbackground=COL["entry_bg"], foreground=COL["entry_fg"])
        s.configure("TEntry", fieldbackground=COL["entry_bg"], foreground=COL["entry_fg"])
        s.configure("Treeview", background=COL["bg2"], foreground=COL["fg"], fieldbackground=COL["bg2"])
        s.configure("Treeview.Heading", background=COL["bg3"], foreground=COL["warm"])

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=COL["bg2"], height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="SUPREM—III", font=("Consolas",16,"bold"), bg=COL["bg2"], fg=COL["warm"]).pack(side="left", padx=15)
        tk.Label(hdr, text="Studio • SyncField Corporation", font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left")

        # Status DOSBox
        self.status_lbl = tk.Label(hdr, font=("Consolas",9), bg=COL["bg2"])
        self.status_lbl.pack(side="right", padx=15)
        self._update_dosbox_status()

        btn_cfg = tk.Button(hdr, text="⚙ DOSBox", font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"],
                            bd=0, command=self._configure_dosbox, cursor="hand2")
        btn_cfg.pack(side="right", padx=5)

        # Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(8,0))

        self.tab_process = ttk.Frame(self.notebook)
        self.tab_code = ttk.Frame(self.notebook)
        self.tab_results = ttk.Frame(self.notebook)
        self.tab_profile = ttk.Frame(self.notebook)
        self.tab_oxid = ttk.Frame(self.notebook)
        self.tab_minimos = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_process, text=" ⬡ Processo ")
        self.notebook.add(self.tab_code, text=" </> Código .IN ")
        self.notebook.add(self.tab_results, text=" 📊 Resultados ")
        self.notebook.add(self.tab_profile, text=" 📉 Perfil ")
        self.notebook.add(self.tab_oxid, text=" 🔥 Oxidação ")
        self.notebook.add(self.tab_minimos, text=" ⚙ MINIMOS ")

        self._build_process_tab()
        self._build_code_tab()
        self._build_results_tab()
        self._build_profile_tab()
        self._build_oxidation_tab()
        self._build_minimos_tab()

        # Footer
        ftr = tk.Frame(self, bg=COL["border"], height=28)
        ftr.pack(fill="x", side="bottom")
        ftr.pack_propagate(False)
        tk.Label(ftr, text=f"{APP_NAME} v{APP_VERSION} — Resultados do SUPREM-III original de Stanford",
                 font=("Consolas",8), bg=COL["border"], fg=COL["dim"]).pack(side="left", padx=10)

    # ── Process Tab ──
    def _build_process_tab(self):
        top = tk.Frame(self.tab_process, bg=COL["bg"])
        top.pack(fill="x", padx=10, pady=(10,5))

        tk.Label(top, text="TITLE:", font=("Consolas",10), bg=COL["bg"], fg=COL["dim"]).pack(side="left")
        tk.Entry(top, textvariable=self.title_var, font=("Consolas",10), bg=COL["entry_bg"],
                 fg=COL["entry_fg"], insertbackground=COL["fg"], bd=1, relief="solid").pack(side="left", fill="x", expand=True, padx=(5,10))

        # Buttons
        bar = tk.Frame(self.tab_process, bg=COL["bg"])
        bar.pack(fill="x", padx=10, pady=5)
        for text, cmd in [("📂 Importar .IN", self._import_in), ("💾 Exportar .IN", self._export_in),
                          ("🔄 Limpar", self._clear_steps), ("📋 Diodo PN", self._load_preset_diode)]:
            tk.Button(bar, text=text, font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"], bd=0,
                      command=cmd, cursor="hand2", padx=8, pady=3).pack(side="left", padx=2)
        # Presets das tarefas (menu)
        tk.Label(bar, text="  Presets:", font=("Consolas",9), bg=COL["bg"], fg=COL["dim"]).pack(side="left")
        mb = tk.Menubutton(bar, text="📑 Tarefas ▾", font=("Consolas",9), bg=COL["accent"], fg="#fff",
                           bd=0, cursor="hand2", padx=8, pady=3, relief="flat")
        menu = tk.Menu(mb, tearoff=0, bg=COL["bg3"], fg=COL["fg"], activebackground=COL["accent"],
                       activeforeground="#fff", bd=0)
        menu.add_command(label="Tarefa 1 — S/D NMOS (etapa 11)", command=self._load_preset_t1)
        menu.add_command(label="Tarefa 1 — S/D PMOS ajustado (etapa 9)", command=self._load_preset_t1_pmos)
        menu.add_command(label="Tarefa 2 — Oxidação úmida (item A)", command=self._load_preset_t2)
        menu.add_command(label="Tarefa 3 — S/D PMOS (etapa 8)", command=self._load_preset_t3)
        mb.configure(menu=menu)
        mb.pack(side="left", padx=2)

        # Main area: steps list + add panel
        main = tk.PanedWindow(self.tab_process, orient="horizontal", bg=COL["bg"], sashwidth=4)
        main.pack(fill="both", expand=True, padx=10, pady=5)

        # Steps list
        left = tk.Frame(main, bg=COL["bg"])
        main.add(left, width=550)

        self.steps_frame = tk.Frame(left, bg=COL["bg"])
        # Scrollable
        canvas = tk.Canvas(left, bg=COL["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self.steps_frame = tk.Frame(canvas, bg=COL["bg"])
        self.steps_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=self.steps_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        # Mouse wheel
        def _on_mouse(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mouse)

        # Right panel: add command + simulate
        right = tk.Frame(main, bg=COL["bg2"])
        main.add(right, width=280)

        tk.Label(right, text="ADICIONAR COMANDO", font=("Consolas",10,"bold"), bg=COL["bg2"],
                 fg=COL["warm"]).pack(padx=10, pady=(10,5), anchor="w")

        self.cmd_type_var = tk.StringVar(value="DIFFUSION")
        cmd_types = ["INITIALIZE","DIFFUSION","DEPOSITION","ETCH","IMPLANTI","EPITAXY","PRINT","PLOT"]
        for ct in cmd_types:
            tk.Radiobutton(right, text=ct, variable=self.cmd_type_var, value=ct,
                           font=("Consolas",10), bg=COL["bg2"], fg=COL["fg"],
                           selectcolor=COL["bg3"], activebackground=COL["bg2"],
                           activeforeground=COL["accent"], indicatoron=True,
                           cursor="hand2").pack(anchor="w", padx=15)

        tk.Button(right, text="+ Adicionar", font=("Consolas",10,"bold"), bg=COL["accent"], fg="#fff",
                  bd=0, command=self._add_step_default, cursor="hand2", pady=6).pack(fill="x", padx=10, pady=10)

        # Simulate button
        tk.Frame(right, bg=COL["border"], height=1).pack(fill="x", padx=10, pady=5)
        self.sim_btn = tk.Button(right, text="▶  SIMULAR", font=("Consolas",12,"bold"),
                                 bg=COL["accent"], fg="#fff", bd=0, command=self._simulate,
                                 cursor="hand2", pady=10)
        self.sim_btn.pack(fill="x", padx=10, pady=10)

        self.runfile_btn = tk.Button(right, text="📄  Rodar arquivo .in",
                                     font=("Consolas",10), bg=COL["btn"], fg=COL["btn_fg"],
                                     bd=0, command=self._run_in_file, cursor="hand2", pady=6)
        self.runfile_btn.pack(fill="x", padx=10, pady=(0,4))
        tk.Label(right, text="(envia o deck literal ao motor,\nsem remontar o processo)",
                 font=("Consolas",8), bg=COL["bg2"], fg=COL["dim"], justify="center").pack(padx=10)

        self.sim_status = tk.Label(right, text="", font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"])
        self.sim_status.pack(padx=10)

    def _refresh_steps_ui(self):
        for w in self.steps_frame.winfo_children():
            w.destroy()
        for i, step in enumerate(self.steps):
            self._create_step_row(i, step)

    def _create_step_row(self, idx, step):
        colors = {"INITIALIZE":"#8B4513","DIFFUSION":"#B22222","DEPOSITION":"#CD853F",
                  "ETCH":"#A0522D","IMPLANTI":"#DC143C","EPITAXY":"#D2691E","PRINT":"#5a7a5a","PLOT":"#5a5a7a"}
        color = colors.get(step["type"], COL["dim"])

        row = tk.Frame(self.steps_frame, bg=COL["bg2"], bd=1, relief="solid", highlightbackground=COL["border"])
        row.pack(fill="x", pady=1, padx=2)

        # Header
        hdr = tk.Frame(row, bg=COL["bg2"])
        hdr.pack(fill="x")

        tk.Label(hdr, text=f" {idx+1} ", font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"], width=3).pack(side="left")
        tk.Label(hdr, text=f" {step['type']} ", font=("Consolas",10,"bold"), bg=COL["bg2"], fg=color).pack(side="left")

        # Summary
        summary = self._step_summary(step)
        tk.Label(hdr, text=summary, font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"],
                 anchor="w").pack(side="left", fill="x", expand=True, padx=5)

        # Buttons
        for txt, cmd in [("▲", lambda i=idx: self._move_step(i,-1)),
                         ("▼", lambda i=idx: self._move_step(i,1)),
                         ("✎", lambda i=idx: self._edit_step(i)),
                         ("✕", lambda i=idx: self._remove_step(i))]:
            tk.Button(hdr, text=txt, font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"] if txt!="✕" else COL["accent"],
                      bd=0, command=cmd, cursor="hand2", padx=3).pack(side="right")

    def _step_summary(self, step):
        p = step["params"]
        t = step["type"]
        if t=="INITIALIZE": return f'Si <{p.get("orientation","100")}> {p.get("dopant","")} {p.get("concentration","")}'
        if t=="DIFFUSION": return f'{p.get("ambient","")} {p.get("temperature","")}°C {p.get("time","")}min'
        if t=="DEPOSITION": return f'{p.get("material","")} {p.get("thickness","")}µm'
        if t=="ETCH": return f'{p.get("material","")}{" ALL" if p.get("all") else ""}'
        if t=="IMPLANTI": return f'{p.get("dopant","")} {p.get("energy","")}keV {p.get("dose","")}'
        if t=="EPITAXY": return f'{p.get("dopant","")} {p.get("thickness","")}µm'
        if t=="PRINT": return f'{p.get("what","")} → {p.get("filename","")}'
        if t=="PLOT": return f'{p.get("what","")} {p.get("curve","")}'
        return ""

    def _add_step_default(self):
        t = self.cmd_type_var.get()
        defaults = {
            "INITIALIZE": {"orientation":"100","dopant":"BORON","concentration":"1E15","dx":"5E-3","thickness":"0.5"},
            "DIFFUSION": {"ambient":"DRYO2","temperature":"1000","time":"15","gasConc":"","solidSol":False,"tRate":""},
            "DEPOSITION": {"material":"ALUMINUM","thickness":"0.4","dopant":"","concentration":"","temperature":""},
            "ETCH": {"material":"OXIDE","all":True,"thickness":""},
            "IMPLANTI": {"dopant":"BORON","energy":"45","dose":"1E13","distribution":""},
            "EPITAXY": {"dopant":"PHOSPHOR","thickness":"1.0","concentration":"5E15","temperature":"1000","growthRate":"0.5"},
            "PRINT": {"what":"NET","curve":"ACTIVE","extra":"CONCENTR","filename":"OUTPUT.OUT","linespa":"1000"},
            "PLOT": {"what":"NET","curve":"ACTIVE","xmax":"","cmin":"","cmax":""},
        }
        step = {"type": t, "params": dict(defaults.get(t, {}))}
        self.steps.append(step)
        self._edit_step(len(self.steps)-1)

    def _edit_step(self, idx):
        step = self.steps[idx]
        win = tk.Toplevel(self)
        win.title(f"Editar: {step['type']}")
        win.geometry("420x400")
        win.configure(bg=COL["bg"])
        win.transient(self)
        win.grab_set()

        tk.Label(win, text=step["type"], font=("Consolas",14,"bold"), bg=COL["bg"], fg=COL["accent"]).pack(pady=(15,10))

        frame = tk.Frame(win, bg=COL["bg"])
        frame.pack(fill="both", expand=True, padx=20)

        entries = {}
        row = 0
        for key, val in step["params"].items():
            tk.Label(frame, text=key, font=("Consolas",10), bg=COL["bg"], fg=COL["dim"]).grid(row=row, column=0, sticky="e", padx=(0,8), pady=3)
            if isinstance(val, bool):
                var = tk.BooleanVar(value=val)
                tk.Checkbutton(frame, variable=var, bg=COL["bg"], fg=COL["fg"], selectcolor=COL["bg3"],
                               activebackground=COL["bg"]).grid(row=row, column=1, sticky="w")
                entries[key] = ("bool", var)
            elif key in ("ambient",):
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(frame, textvariable=var, values=AMBIENTS, width=20, font=("Consolas",10))
                cb.grid(row=row, column=1, sticky="ew", pady=3)
                entries[key] = ("str", var)
            elif key in ("dopant",):
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(frame, textvariable=var, values=[""] + DOPANTS, width=20, font=("Consolas",10))
                cb.grid(row=row, column=1, sticky="ew", pady=3)
                entries[key] = ("str", var)
            elif key in ("material",):
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(frame, textvariable=var, values=MATERIALS, width=20, font=("Consolas",10))
                cb.grid(row=row, column=1, sticky="ew", pady=3)
                entries[key] = ("str", var)
            elif key in ("what",):
                var = tk.StringVar(value=val)
                cb = ttk.Combobox(frame, textvariable=var, values=["NET","BORON","PHOSPHOR","ARSENIC","ANTIMONY","ALL","OXIDE","TOTAL"], width=20, font=("Consolas",10))
                cb.grid(row=row, column=1, sticky="ew", pady=3)
                entries[key] = ("str", var)
            else:
                var = tk.StringVar(value=str(val) if val else "")
                e = tk.Entry(frame, textvariable=var, font=("Consolas",10), bg=COL["entry_bg"],
                             fg=COL["entry_fg"], insertbackground=COL["fg"], bd=1, relief="solid")
                e.grid(row=row, column=1, sticky="ew", pady=3)
                entries[key] = ("str", var)
            row += 1

        frame.columnconfigure(1, weight=1)

        def save():
            for key, (typ, var) in entries.items():
                if typ == "bool":
                    step["params"][key] = var.get()
                else:
                    step["params"][key] = var.get()
            self._refresh_steps_ui()
            win.destroy()

        btn_frame = tk.Frame(win, bg=COL["bg"])
        btn_frame.pack(fill="x", padx=20, pady=15)
        tk.Button(btn_frame, text="Salvar", font=("Consolas",10,"bold"), bg=COL["accent"], fg="#fff",
                  bd=0, command=save, cursor="hand2", padx=20, pady=5).pack(side="right")
        tk.Button(btn_frame, text="Cancelar", font=("Consolas",10), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, command=win.destroy, cursor="hand2", padx=15, pady=5).pack(side="right", padx=5)

    def _move_step(self, idx, direction):
        new = idx + direction
        if 0 <= new < len(self.steps):
            self.steps[idx], self.steps[new] = self.steps[new], self.steps[idx]
            self._refresh_steps_ui()

    def _remove_step(self, idx):
        self.steps.pop(idx)
        self._refresh_steps_ui()

    def _clear_steps(self):
        self.steps.clear()
        self._refresh_steps_ui()

    def _load_preset_diode(self):
        self.title_var.set("DIODE FOR DIFUSION SILICON TYPE P")
        self.steps = [
            {"type":"INITIALIZE","params":{"orientation":"100","dopant":"BORON","concentration":"1E15","dx":"5E-3","thickness":"0.5"}},
            {"type":"DIFFUSION","params":{"ambient":"DRYO2","temperature":"1000","time":"15","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"ETCH","params":{"material":"OXIDE","all":True,"thickness":""}},
            {"type":"DIFFUSION","params":{"ambient":"PHOSPHOR","temperature":"1100","time":"30","gasConc":"1E18","solidSol":False,"tRate":""}},
            {"type":"DIFFUSION","params":{"ambient":"NITROGEN","temperature":"900","time":"15","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"DEPOSITION","params":{"material":"OXIDE","thickness":"0.2","dopant":"","concentration":"","temperature":""}},
            {"type":"ETCH","params":{"material":"OXIDE","all":True,"thickness":""}},
            {"type":"DEPOSITION","params":{"material":"ALUMINUM","thickness":"0.4","dopant":"","concentration":"","temperature":""}},
            {"type":"PRINT","params":{"what":"NET","curve":"ACTIVE","extra":"CONCENTR","filename":"DIODED.OUT","linespa":"1000"}},
            {"type":"PRINT","params":{"what":"OXIDE","curve":"","extra":"LAYER","filename":"DIODEL.OUT","linespa":""}},
        ]
        self._refresh_steps_ui()

    def _load_preset_t1(self):
        # Tarefa 1 - CMOS: junção S/D do NMOS (n+ no epi p). Ajuste dose/energia conforme necessário.
        self.title_var.set("Tarefa 1 - Etapa 11 - Juncao S/D do NMOS (Fosforo)")
        self.steps = [
            {"type":"INITIALIZE","params":{"orientation":"100","dopant":"BORON","concentration":"1E17","dx":"4E-3","thickness":"0.6"}},
            {"type":"DIFFUSION","params":{"ambient":"DRYO2","temperature":"1000","time":"40","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"IMPLANTI","params":{"dopant":"PHOSPHOR","energy":"60","dose":"4.5E14","distribution":""}},
            {"type":"DIFFUSION","params":{"ambient":"NITROGEN","temperature":"900","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"Net","curve":"Active","extra":"Concentration","filename":"","linespa":""}},
        ]
        self._refresh_steps_ui()

    def _load_preset_t1_pmos(self):
        # Tarefa 1 - PMOS S/D (boro) no poço N AJUSTADO (forma a junção p+/n, Xj~0,29um).
        self.title_var.set("Tarefa 1 - Etapa 9 - PMOS S/D ajustado (poco N reforcado)")
        self.steps = [
            {"type":"INITIALIZE","params":{"orientation":"100","dopant":"BORON","concentration":"1E17","dx":"8E-3","thickness":"1.5"}},
            {"type":"IMPLANTI","params":{"dopant":"PHOSPHOR","energy":"100","dose":"1.2E14","distribution":""}},
            {"type":"DIFFUSION","params":{"ambient":"NITROGEN","temperature":"1150","time":"180","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"DIFFUSION","params":{"ambient":"DRYO2","temperature":"1000","time":"40","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"IMPLANTI","params":{"dopant":"BORON","energy":"50","dose":"4.5E14","distribution":""}},
            {"type":"DIFFUSION","params":{"ambient":"NITROGEN","temperature":"900","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"Net","curve":"Active","extra":"Concentration","filename":"","linespa":""}},
        ]
        self._refresh_steps_ui()

    def _load_preset_t2(self):
        # Tarefa 2 - Oxidação úmida 1000C: tempos acumulados 20/40/70/80/100/120 min (item A).
        self.title_var.set("Tarefa 2 - Oxidacao umida 1000C - tempos 20/40/70/80/100/120")
        self.steps = [
            {"type":"INITIALIZE","params":{"orientation":"100","dopant":"BORON","concentration":"1E15","dx":"2E-3","thickness":"0.5"}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"30","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"10","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
            {"type":"DIFFUSION","params":{"ambient":"WETO2","temperature":"1000","time":"20","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"LAYERS","curve":"","extra":"","filename":"","linespa":""}},
        ]
        self._refresh_steps_ui()

    def _load_preset_t3(self):
        # Tarefa 3 - MOS (substrato N): junção S/D do PMOS (boro 9e15, 90keV) + recozimento (item 5).
        self.title_var.set("Tarefa 3 - Etapa 8 - Juncao S/D PMOS (Boro 9e15 90keV)")
        self.steps = [
            {"type":"INITIALIZE","params":{"orientation":"100","dopant":"PHOSPHOR","concentration":"2.5E15","dx":"2E-3","thickness":"0.8"}},
            {"type":"DIFFUSION","params":{"ambient":"DRYO2","temperature":"1100","time":"15","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"IMPLANTI","params":{"dopant":"BORON","energy":"90","dose":"9E15","distribution":""}},
            {"type":"DIFFUSION","params":{"ambient":"NITROGEN","temperature":"900","time":"30","gasConc":"","solidSol":False,"tRate":""}},
            {"type":"PRINT","params":{"what":"Net","curve":"Active","extra":"Concentration","filename":"","linespa":""}},
        ]
        self._refresh_steps_ui()

    def _import_in(self):
        path = filedialog.askopenfilename(filetypes=[("SUPREM-III Input","*.in *.IN *.txt"),("Todos","*.*")])
        if path:
            text = Path(path).read_text(errors="replace")
            title, steps = parse_in_file(text)
            self.title_var.set(title)
            self.steps = steps
            self._refresh_steps_ui()

    def _export_in(self):
        code = build_in_file(self.title_var.get(), self.steps)
        path = filedialog.asksaveasfilename(defaultextension=".IN", filetypes=[("SUPREM-III Input","*.IN"),("Todos","*.*")])
        if path:
            Path(path).write_text(code, encoding="ascii", errors="replace")

    # ── Code Tab ──
    def _build_code_tab(self):
        bar = tk.Frame(self.tab_code, bg=COL["bg"])
        bar.pack(fill="x", padx=10, pady=10)
        tk.Button(bar, text="▶ Rodar este código", font=("Consolas",9,"bold"),
                  bg=COL["accent"], fg="#fff", bd=0,
                  command=self._run_code_text, cursor="hand2", padx=8, pady=3).pack(side="left")
        tk.Button(bar, text="📂 Abrir .in", font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"], bd=0,
                  command=self._open_in_to_code, cursor="hand2", padx=8, pady=3).pack(side="left", padx=5)
        tk.Button(bar, text="📋 Copiar", font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"], bd=0,
                  command=self._copy_code, cursor="hand2", padx=8, pady=3).pack(side="left", padx=5)
        tk.Button(bar, text="🔄 Gerar do processo", font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"], bd=0,
                  command=self._refresh_code, cursor="hand2", padx=8, pady=3).pack(side="left", padx=5)
        tk.Label(bar, text="  (cole/edite um deck e clique em Rodar — vai literal ao motor)",
                 font=("Consolas",8), bg=COL["bg"], fg=COL["dim"]).pack(side="left")

        self.code_text = scrolledtext.ScrolledText(self.tab_code, font=("Consolas",11), bg=COL["entry_bg"],
                                                    fg=COL["fg"],
                                                    insertbackground=COL["fg"], bd=0, wrap="none")
        self.code_text.pack(fill="both", expand=True, padx=10, pady=(0,10))
        # Só preenche automaticamente a partir do processo quando o usuário
        # não digitou/carregou um deck próprio (evita sobrescrever ao trocar de aba).
        self._code_user_edited = False
        self.code_text.bind("<Key>", lambda e: setattr(self, "_code_user_edited", True))
        self.notebook.bind("<<NotebookTabChanged>>",
                            lambda e: self._refresh_code() if not self._code_user_edited else None)

    def _run_code_text(self):
        deck = self.code_text.get("1.0", "end").strip()
        if not deck:
            messagebox.showwarning("Sem código", "A aba de código está vazia. "
                                   "Cole um deck .in ou gere a partir do processo.")
            return
        self._run_deck(deck)

    def _open_in_to_code(self):
        path = filedialog.askopenfilename(
            title="Abrir arquivo .in",
            filetypes=[("SUPREM-III Input", "*.in *.IN *.txt"), ("Todos", "*.*")])
        if not path:
            return
        try:
            deck = Path(path).read_text(encoding="latin1", errors="replace")
        except Exception as e:
            messagebox.showerror("Erro ao ler arquivo", str(e)); return
        self.code_text.delete("1.0", "end")
        self.code_text.insert("1.0", deck)
        self._code_user_edited = True
        self.notebook.select(self.tab_code)

    def _refresh_code(self):
        code = build_in_file(self.title_var.get(), self.steps)
        self.code_text.delete("1.0", "end")
        self.code_text.insert("1.0", code)
        self._code_user_edited = False

    def _copy_code(self):
        self._refresh_code()
        self.clipboard_clear()
        self.clipboard_append(self.code_text.get("1.0", "end"))

    # ── MINIMOS Tab (simulador de dispositivo MOS 2D/3D) ──
    def _build_minimos_tab(self):
        wrap = tk.Frame(self.tab_minimos, bg=COL["bg"])
        wrap.pack(fill="both", expand=True)

        top = tk.Frame(wrap, bg=COL["bg2"])
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="MINIMOS 6.1 — simulador de dispositivo MOS (2D/3D)",
                 font=("Consolas", 11, "bold"), bg=COL["bg2"], fg=COL["fg"]).pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(top, text="Roda o motor original (mm_pl.exe) replicando o bin/minimos.bat. "
                           "Edite/carregue um deck .inp e rode.",
                 font=("Consolas", 8), bg=COL["bg2"], fg=COL["dim"]).pack(anchor="w", padx=6, pady=(0, 6))

        # linha: pasta do MINIMOS
        dirbar = tk.Frame(top, bg=COL["bg2"]); dirbar.pack(fill="x", padx=6, pady=(0, 6))
        tk.Label(dirbar, text="Pasta bin do MINIMOS:", font=("Consolas", 9),
                 bg=COL["bg2"], fg=COL["dim"]).pack(side="left")
        found = find_minimos_dir()
        self.mm_dir = tk.StringVar(value=str(found) if found else "")
        tk.Entry(dirbar, textvariable=self.mm_dir, width=48, font=("Consolas", 9),
                 bg=COL["entry_bg"], fg=COL["fg"], insertbackground=COL["fg"], bd=1).pack(side="left", padx=4)
        tk.Button(dirbar, text="📁", font=("Consolas", 9), bg=COL["btn"], fg=COL["btn_fg"],
                  bd=0, cursor="hand2", command=self._mm_pick_dir).pack(side="left", padx=2)
        tk.Button(dirbar, text="Verificar", font=("Consolas", 9), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", command=self._mm_check_dir).pack(side="left", padx=2)

        # botões de deck
        btnbar = tk.Frame(top, bg=COL["bg2"]); btnbar.pack(fill="x", padx=6, pady=(0, 8))
        tk.Label(btnbar, text="Deck (.inp):", font=("Consolas", 9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left")
        tk.Button(btnbar, text="📂 Abrir .inp", font=("Consolas", 9), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", command=self._mm_open_inp).pack(side="left", padx=3)
        tk.Button(btnbar, text="🧱 Construtor", font=("Consolas", 9, "bold"), bg=COL["warm"], fg="#1a1a1a",
                  bd=0, cursor="hand2", command=self._mm_builder).pack(side="left", padx=3)
        tk.Button(btnbar, text="📄 Modelo 2D", font=("Consolas", 9), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", command=lambda: self._mm_template("2d")).pack(side="left", padx=3)
        tk.Button(btnbar, text="📈 Modelo I-V (STEP)", font=("Consolas", 9), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", command=lambda: self._mm_template("iv")).pack(side="left", padx=3)
        tk.Label(btnbar, text="Saída ref:", font=("Consolas", 9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=(12, 2))
        self.mm_screen = tk.StringVar(value="o")
        for txt, val in [("arquivo .ref", "o"), ("nenhuma", "i")]:
            tk.Radiobutton(btnbar, text=txt, variable=self.mm_screen, value=val, font=("Consolas", 8),
                           bg=COL["bg2"], fg=COL["fg"], selectcolor=COL["entry_bg"],
                           activebackground=COL["bg2"]).pack(side="left")

        # painel PMOS 2-D (gera perfil de dopagem e roda — contorna o limite do PMOS analítico)
        pmosbar = tk.Frame(top, bg=COL["bg2"]); pmosbar.pack(fill="x", padx=6, pady=(0, 8))
        tk.Label(pmosbar, text="PMOS 2-D:", font=("Consolas", 9, "bold"), bg=COL["bg2"],
                 fg=COL["warm"]).pack(side="left", padx=(0, 4))
        self.mm_nd = tk.StringVar(value="2.5e13")
        self.mm_vtdose = tk.StringVar(value="3.5e10")
        self.mm_vttype = tk.StringVar(value="B")
        self.mm_nss = tk.StringVar(value="2.0e11")
        def pf(lbl, var, w=8):
            tk.Label(pmosbar, text=lbl, font=("Consolas", 8), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=(6, 1))
            tk.Entry(pmosbar, textvariable=var, width=w, font=("Consolas", 9), bg=COL["entry_bg"],
                     fg=COL["fg"], insertbackground=COL["fg"], bd=1).pack(side="left")
        pf("Nd subs.:", self.mm_nd); pf("dose Vt:", self.mm_vtdose)
        tk.Label(pmosbar, text="tipo:", font=("Consolas", 8), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=(6, 1))
        ttk.Combobox(pmosbar, textvariable=self.mm_vttype, values=["B", "P"], width=3, state="readonly").pack(side="left")
        pf("Nss:", self.mm_nss)
        tk.Button(pmosbar, text="🔧 Gerar perfil + rodar PMOS", font=("Consolas", 9, "bold"),
                  bg=COL["accent"], fg="#fff", bd=0, cursor="hand2",
                  command=self._run_minimos_pmos).pack(side="left", padx=8)

        # editor do deck
        mid = tk.Frame(wrap, bg=COL["bg"]); mid.pack(fill="both", expand=True, padx=10, pady=4)
        left = tk.Frame(mid, bg=COL["bg"]); left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Deck de entrada", font=("Consolas", 9, "bold"),
                 bg=COL["bg"], fg=COL["dim"]).pack(anchor="w")
        self.mm_editor = scrolledtext.ScrolledText(left, font=("Consolas", 10), bg=COL["entry_bg"],
                                                   fg=COL["fg"], insertbackground=COL["fg"], bd=0, wrap="none", width=46)
        self.mm_editor.pack(fill="both", expand=True)
        self._mm_template("iv")

        runbar = tk.Frame(left, bg=COL["bg"]); runbar.pack(fill="x", pady=4)
        self.mm_run_btn = tk.Button(runbar, text="⚙  Rodar MINIMOS", font=("Consolas", 10, "bold"),
                                    bg=COL["accent"], fg="#fff", bd=0, cursor="hand2", pady=6,
                                    command=self._run_minimos)
        self.mm_run_btn.pack(side="left", padx=(0, 6))
        self.mm_open_btn = tk.Button(runbar, text="📁 Abrir pasta", font=("Consolas", 9),
                                     bg=COL["bg3"], fg=COL["fg"], bd=0, cursor="hand2",
                                     command=lambda: self._open_folder(getattr(self, "_mm_last_dir", None)),
                                     state="disabled")
        self.mm_open_btn.pack(side="left")

        # saída
        right = tk.Frame(mid, bg=COL["bg"]); right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.mm_out_nb = ttk.Notebook(right); self.mm_out_nb.pack(fill="both", expand=True)
        self.mm_tab_txt = ttk.Frame(self.mm_out_nb); self.mm_tab_iv = ttk.Frame(self.mm_out_nb)
        self.mm_tab_ref = ttk.Frame(self.mm_out_nb)
        self.mm_out_nb.add(self.mm_tab_txt, text=" Saída (.out) ")
        self.mm_out_nb.add(self.mm_tab_iv, text=" Curva I-V ")
        self.mm_out_nb.add(self.mm_tab_ref, text=" Referência (.ref) ")
        self.mm_tab_3d = ttk.Frame(self.mm_out_nb)
        self.mm_out_nb.add(self.mm_tab_3d, text=" Superfície 3D ")
        self.mm_out_txt = scrolledtext.ScrolledText(self.mm_tab_txt, font=("Consolas", 8), bg=COL["entry_bg"],
                                                    fg=COL["fg"], bd=0, wrap="none")
        self.mm_out_txt.pack(fill="both", expand=True)
        self.mm_iv_frame = tk.Frame(self.mm_tab_iv, bg=COL["bg"]); self.mm_iv_frame.pack(fill="both", expand=True)
        self.mm_ref_txt = scrolledtext.ScrolledText(self.mm_tab_ref, font=("Consolas", 8), bg=COL["entry_bg"],
                                                    fg=COL["fg"], bd=0, wrap="none")
        self.mm_ref_txt.pack(fill="both", expand=True)
        # aba Superfície 3D: seletor de campo + área do gráfico (lê o PIF do MINIMOS)
        d3bar = tk.Frame(self.mm_tab_3d, bg=COL["bg2"]); d3bar.pack(fill="x")
        tk.Label(d3bar, text="Campo:", font=("Consolas", 9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=(6, 3), pady=4)
        self.mm_field = tk.StringVar(value="")
        self.mm_field_cb = ttk.Combobox(d3bar, textvariable=self.mm_field, values=[], width=30, state="readonly")
        self.mm_field_cb.pack(side="left", pady=4)
        self.mm_field_cb.bind("<<ComboboxSelected>>", lambda e: self._plot_minimos_3d())
        tk.Label(d3bar, text="(gere mapas com OUTPUT ALL=YES PIF=YES no modo 2-D)",
                 font=("Consolas", 8), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=8)
        self.mm_3d_frame = tk.Frame(self.mm_tab_3d, bg=COL["bg"]); self.mm_3d_frame.pack(fill="both", expand=True)
        self._mm_pif_cache = ([], [], {})

        self.mm_status = tk.Label(wrap, text="Pronto." if found else "Defina a pasta bin do MINIMOS.",
                                  font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"], anchor="w")
        self.mm_status.pack(fill="x", padx=12, pady=(0, 8))

    def _mm_pick_dir(self):
        d = filedialog.askdirectory(title="Selecione a pasta bin do MINIMOS (com mm_pl.exe)")
        if d:
            self.mm_dir.set(d); self._mm_check_dir()

    def _mm_check_dir(self):
        d = self.mm_dir.get().strip()
        if not d:
            messagebox.showwarning("MINIMOS", "Informe a pasta bin do MINIMOS."); return
        problems = check_minimos(Path(d))
        save_minimos_dir(d)
        only_win = problems
        if only_win:
            messagebox.showerror("MINIMOS", "Problemas:\n• " + "\n• ".join(problems))
            self.mm_status.configure(text="Pasta inválida.", fg=COL["accent"])
        else:
            kind = "Win32 (.exe)" if _is_pe_executable(Path(d) / ("mm_pl" + EXE)) else "nativo"
            self.mm_status.configure(text=f"Pasta OK — mm_pl ({kind}) + stack.rul encontrados.", fg=COL["warm"])

    def _mm_open_inp(self):
        path = filedialog.askopenfilename(title="Abrir deck MINIMOS",
                  filetypes=[("MINIMOS input", "*.inp"), ("Todos", "*.*")])
        if path:
            try:
                self.mm_editor.delete("1.0", "end")
                self.mm_editor.insert("1.0", Path(path).read_text(encoding="latin1", errors="replace"))
                self.mm_status.configure(text=f"Carregado: {Path(path).name}", fg=COL["dim"])
            except Exception as e:
                messagebox.showerror("Erro ao abrir", str(e))

    def _mm_builder(self):
        """Construtor visual de deck do MINIMOS: formulário -> build_minimos_deck."""
        win = tk.Toplevel(self)
        win.title("Construtor de deck — MINIMOS")
        win.configure(bg=COL["bg"]); win.geometry("520x690")
        try:
            win.transient(self.winfo_toplevel()); win.grab_set()
        except Exception:
            pass
        cv = tk.Frame(win, bg=COL["bg"]); cv.pack(fill="both", expand=True, padx=12, pady=10)
        tk.Label(cv, text="Construtor de deck MINIMOS", font=("Consolas", 12, "bold"),
                 bg=COL["bg"], fg=COL["fg"]).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))
        V = {}
        def add(r, c, label, key, default, kind="entry", values=None, w=12):
            tk.Label(cv, text=label, font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"]).grid(
                row=r, column=c, sticky="e", padx=(4, 3), pady=3)
            var = tk.StringVar(value=str(default)); V[key] = var
            if kind == "combo":
                wdg = ttk.Combobox(cv, textvariable=var, values=values, width=w - 2, state="readonly")
            else:
                wdg = tk.Entry(cv, textvariable=var, width=w, font=("Consolas", 10),
                               bg=COL["entry_bg"], fg=COL["fg"], insertbackground=COL["fg"], bd=1)
            wdg.grid(row=r, column=c + 1, sticky="w", padx=(0, 8), pady=3)
            return var

        # título (campo largo, ocupando a linha toda)
        tk.Label(cv, text="Título:", font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"]).grid(
            row=1, column=0, sticky="e", padx=(4, 3), pady=3)
        V["title"] = tk.StringVar(value="Deck do construtor")
        tk.Entry(cv, textvariable=V["title"], font=("Consolas", 10), bg=COL["entry_bg"],
                 fg=COL["fg"], insertbackground=COL["fg"], bd=1).grid(
            row=1, column=1, columnspan=3, sticky="we", padx=(0, 8), pady=3)

        add(2, 0, "Canal:", "channel", "N", "combo", ["N", "P"])
        add(2, 2, "Porta:", "gate", "NPOLY", "combo", ["NPOLY", "PPOLY", "AL"])
        add(3, 0, "TOX (nm):", "tox_nm", "15")
        add(3, 2, "Análise:", "mode_label", "Curva I-V", "combo",
            ["Tensão de limiar", "Ponto de operação (mapas 3D)", "Curva I-V"], w=24)
        add(4, 0, "W (µm):", "w_um", "1.0")
        add(4, 2, "L (µm):", "l_um", "0.85")

        tk.Label(cv, text="── Polarização ──", font=("Consolas", 9, "bold"), bg=COL["bg"],
                 fg=COL["warm"]).grid(row=5, column=0, columnspan=4, sticky="w", pady=(8, 2))
        add(6, 0, "UD (V):", "ud", "0.1")
        add(6, 2, "UG (V):", "ug", "2.0")
        V["auto_sign"] = tk.BooleanVar(value=True)
        tk.Checkbutton(cv, text="ajustar sinal p/ PMOS automaticamente", variable=V["auto_sign"],
                       font=("Consolas", 8), bg=COL["bg"], fg=COL["fg"], selectcolor=COL["entry_bg"],
                       activebackground=COL["bg"]).grid(row=7, column=0, columnspan=4, sticky="w", padx=4)

        tk.Label(cv, text="── Varredura (curva I-V) ──", font=("Consolas", 9, "bold"), bg=COL["bg"],
                 fg=COL["warm"]).grid(row=8, column=0, columnspan=4, sticky="w", pady=(8, 2))
        add(9, 0, "Varia:", "step_label", "VD (dreno)", "combo", ["VD (dreno)", "VG (porta)"], w=16)
        add(9, 2, "passo (V):", "step", "0.5")
        add(10, 0, "nº passos:", "nstep", "8")

        tk.Label(cv, text="── Perfil (NMOS analítico) ──", font=("Consolas", 9, "bold"), bg=COL["bg"],
                 fg=COL["warm"]).grid(row=11, column=0, columnspan=4, sticky="w", pady=(8, 2))
        add(12, 0, "Substrato NB:", "nb", "5.2e16")
        add(12, 2, "Nss (cm⁻²):", "nss", "1.25e11")
        add(13, 0, "S/D elem:", "sd_elem", "AS", "combo", ["AS", "P", "B", "SB"])
        add(13, 2, "S/D dose:", "sd_dose", "2e15")
        add(14, 0, "S/D energia(keV):", "sd_akev", "160", w=10)
        add(14, 2, "óxido másc(nm):", "sd_tox_nm", "50", w=10)
        add(15, 0, "recoz. °C:", "anneal_c", "1050")
        add(15, 2, "recoz. min:", "anneal_min", "2700")
        add(16, 0, "Vt elem:", "vt_elem", "B", "combo", ["B", "P", "AS"])
        add(16, 2, "Vt dose:", "vt_dose", "0")
        add(17, 0, "Vt energia(keV):", "vt_akev", "50", w=10)

        note = tk.Label(cv, text="PMOS: o deck sai com PROFILE FILE=2-D; gere o perfil com o painel "
                                 "“PMOS 2-D” da aba.", font=("Consolas", 8), bg=COL["bg"], fg=COL["dim"],
                        wraplength=480, justify="left")
        note.grid(row=18, column=0, columnspan=4, sticky="w", pady=(8, 4))

        def collect():
            mode_map = {"Tensão de limiar": "vth", "Ponto de operação (mapas 3D)": "op", "Curva I-V": "iv"}
            p = {k: (v.get() if not isinstance(v, tk.BooleanVar) else v.get()) for k, v in V.items()}
            p["mode"] = mode_map.get(p.get("mode_label", ""), "iv")
            p["step_var"] = "DD" if p.get("step_label", "").startswith("VD") else "DG"
            for num in ("tox_nm", "w_um", "l_um", "ud", "ug", "step", "nstep", "nb", "nss",
                        "sd_dose", "sd_akev", "sd_tox_nm", "anneal_c", "anneal_min", "vt_dose", "vt_akev"):
                if p.get(num, "") == "":
                    p.pop(num, None)
            return p

        def gerar(close):
            try:
                deck = build_minimos_deck(collect())
            except Exception as e:
                messagebox.showerror("Construtor", f"Não consegui gerar o deck.\n({e})", parent=win); return
            self.mm_editor.delete("1.0", "end"); self.mm_editor.insert("1.0", deck)
            self.mm_status.configure(text="Deck gerado pelo construtor.", fg=COL["warm"])
            if close:
                win.destroy()

        bbar = tk.Frame(cv, bg=COL["bg"]); bbar.grid(row=19, column=0, columnspan=4, pady=12, sticky="w")
        tk.Button(bbar, text="Gerar deck", font=("Consolas", 10, "bold"), bg=COL["accent"], fg="#fff",
                  bd=0, cursor="hand2", padx=10, pady=4, command=lambda: gerar(False)).pack(side="left", padx=4)
        tk.Button(bbar, text="Gerar e fechar", font=("Consolas", 10), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", padx=10, pady=4, command=lambda: gerar(True)).pack(side="left", padx=4)
        tk.Button(bbar, text="Cancelar", font=("Consolas", 10), bg=COL["bg3"], fg=COL["fg"],
                  bd=0, cursor="hand2", padx=10, pady=4, command=win.destroy).pack(side="left", padx=4)

    def _mm_template(self, kind):
        if kind == "iv":
            deck = ("* Curva I-V (varredura de VD via STEP) - NMOS\n"
                    "DEVICE     CHANNEL=N  GATE=NPOLY  TOX=150.E-8  W=1.E-4  L=0.85E-4\n"
                    "BIAS       UD=0.1  UG=2.\n"
                    "STEP       DD=0.5  ND=8\n"
                    "PROFILE    NB=5.2E16  ELEM=AS  DOSE=2.E15  TOX=500.E-8  AKEV=160.\n"
                    "+          TEMP=1050.  TIME=2700\n"
                    "IMPLANT    ELEM=B  DOSE=1.E12  AKEV=12  TEMP=940  TIME=1000\n"
                    "OPTION     MODEL=2-D\n"
                    "OUTPUT     ALL=YES\n"
                    "END\n")
        else:
            deck = ("* Ponto de operacao 2D - NMOS\n"
                    "DEVICE     CHANNEL=N  GATE=NPOLY  TOX=150.E-8  W=1.E-4  L=0.85E-4\n"
                    "BIAS       UD=4.  UG=1.5\n"
                    "PROFILE    NB=5.2E16  ELEM=AS  DOSE=2.E15  TOX=500.E-8  AKEV=160.\n"
                    "+          TEMP=1050.  TIME=2700\n"
                    "IMPLANT    ELEM=B  DOSE=1.E12  AKEV=12  TEMP=940  TIME=1000\n"
                    "OPTION     MODEL=2-D\n"
                    "OUTPUT     ALL=YES PIF=YES\n"
                    "END\n")
        self.mm_editor.delete("1.0", "end"); self.mm_editor.insert("1.0", deck)

    def _run_minimos(self):
        d = self.mm_dir.get().strip()
        problems = check_minimos(Path(d) if d else None)
        if problems:
            messagebox.showerror("MINIMOS", "Não dá para rodar:\n• " + "\n• ".join(problems)); return
        deck = self.mm_editor.get("1.0", "end").rstrip() + "\n"
        self.mm_run_btn.configure(state="disabled", text="⏳ Rodando...")
        self.mm_status.configure(text="Executando mm_pl...", fg=COL["dim"])
        run_minimos(deck, Path(d), base="mm_run", screen=self.mm_screen.get(),
                    callback_done=lambda r: self.after(0, lambda: self._mm_done(r)),
                    callback_error=lambda e: self.after(0, lambda: self._mm_err(e)))

    def _run_minimos_pmos(self):
        d = self.mm_dir.get().strip()
        problems = check_minimos(Path(d) if d else None)
        if problems:
            messagebox.showerror("MINIMOS", "Não dá para rodar:\n• " + "\n• ".join(problems)); return
        try:
            nd = float(self.mm_nd.get().replace(",", "."))
            vtd = float(self.mm_vtdose.get().replace(",", "."))
            nss = float(self.mm_nss.get().replace(",", "."))
            vtt = self.mm_vttype.get().strip() or "B"
        except Exception as e:
            messagebox.showerror("PMOS 2-D", f"Valores inválidos.\n({e})"); return
        # gera o perfil 2-D num arquivo temporário
        prof = Path(tempfile.mktemp(suffix="_pmos.dop"))
        try:
            write_minimos_2d_profile(str(prof), nd_sub=nd, vt_dose=vtd, vt_type=vtt)
        except Exception as e:
            messagebox.showerror("PMOS 2-D", f"Falha ao gerar o perfil.\n({e})"); return
        # monta um deck PMOS coerente e o coloca no editor (transparência p/ o usuário)
        deck = ("* PMOS via perfil 2-D (gerado pelo Studio)\n"
                "DEVICE     CHANNEL=P  GATE=PPOLY  TOX=750.E-8  W=10.E-4  L=20.E-4\n"
                "BIAS       UD=-0.1\n"
                "PROFILE    FILE=2-D\n"
                f"INTERFACE  NSS={nss:.3E}\n"
                "OPTION     MODEL=THRES\n"
                "OUTPUT     NONE=YES\n"
                "END\n")
        self.mm_editor.delete("1.0", "end"); self.mm_editor.insert("1.0", deck)
        self.mm_run_btn.configure(state="disabled", text="⏳ Rodando...")
        self.mm_status.configure(text="Gerando perfil PMOS 2-D e rodando mm_pl...", fg=COL["dim"])
        run_minimos(deck, Path(d), base="pmos", screen=self.mm_screen.get(), dopfile=str(prof),
                    callback_done=lambda r: self.after(0, lambda: self._mm_done(r)),
                    callback_error=lambda e: self.after(0, lambda: self._mm_err(e)))

    def _mm_err(self, msg):
        self.mm_run_btn.configure(state="normal", text="⚙  Rodar MINIMOS")
        self.mm_status.configure(text="Erro.", fg=COL["accent"])
        messagebox.showerror("Erro no MINIMOS", msg)

    def _mm_done(self, r):
        self.mm_run_btn.configure(state="normal", text="⚙  Rodar MINIMOS")
        self._mm_last_dir = r.get("__dir__")
        if self._mm_last_dir:
            self.mm_open_btn.configure(state="normal")
        self.mm_out_txt.delete("1.0", "end")
        body = r.get("out") or r.get("ref") or "(sem arquivo .out — verifique o deck e o .ref)"
        self.mm_out_txt.insert("1.0", body)
        # aba de referência (.ref) — onde o motor escreve o log e o motivo de parada
        self.mm_ref_txt.delete("1.0", "end")
        self.mm_ref_txt.insert("1.0", r.get("ref") or "(sem arquivo .ref gerado)")
        # detecta parada/abort e limiar para a barra de status
        whole = (r.get("ref") or "") + "\n" + (r.get("out") or "")
        aborted = re.search(r"ABORT|PHYSICAL ERROR|INCONSIST|NOT INSTALLED", whole, re.IGNORECASE)
        mth = re.search(r"THRESHOLD VOLTAGE\s*=\s*([-0-9.]+)", whole)
        stages = " → ".join(r.get("stages", []))
        if aborted and not mth:
            self.mm_status.configure(
                text=f"⚠ Motor parou sem resultado — veja a aba Referência (.ref). [{aborted.group(0)}]",
                fg=COL["accent"])
        elif mth:
            self.mm_status.configure(text=f"Concluído: Vth = {mth.group(1)} V | {stages}", fg=COL["warm"])
        else:
            self.mm_status.configure(text=f"Concluído: {stages} | arquivos: {', '.join(r.get('files', []))}",
                                     fg=COL["warm"])
        # curva I-V
        for w in self.mm_iv_frame.winfo_children():
            w.destroy()
        headers, rows = parse_minimos_iv(r.get("iv"))
        ncol = len(rows[0]) if rows else 0
        default = ["UB", "UD", "UG", "US", "IB", "ID", "IG", "IS"]
        names = headers if (headers and len(headers) == ncol) else (
            default[:ncol] if 0 < ncol <= len(default) else [f"c{i}" for i in range(ncol)])

        if not HAS_MPL or not rows:
            tk.Label(self.mm_iv_frame,
                     text=("Sem dados I-V para plotar.\n"
                           "Use o STEP no deck (ex.: STEP DD=0.5 ND=8) para gerar a curva."),
                     font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"], justify="left").pack(padx=20, pady=20)
        elif len(rows) == 1:
            # ponto de operação único (sem STEP): não há curva — mostra os valores
            row = rows[0]
            linhas = ["Ponto de operação único (sem STEP) — não há curva a traçar.\n",
                      "Para obter uma curva I-V, adicione um STEP ao deck, por exemplo:",
                      "    STEP  DD=0.5  ND=8       (varre o dreno UD)",
                      "    STEP  DG=0.25 NG=8       (varre a porta UG)\n",
                      "Valores deste ponto (fort.61):"]
            for n, v in zip(names, row):
                unid = "V" if n.upper().startswith("U") else ("A" if n.upper().startswith("I") else "")
                linhas.append(f"    {n:<4} = {v: .4e} {unid}")
            box = scrolledtext.ScrolledText(self.mm_iv_frame, font=("Consolas", 9),
                                            bg=COL["entry_bg"], fg=COL["fg"], bd=0, wrap="word")
            box.pack(fill="both", expand=True, padx=8, pady=8)
            box.insert("1.0", "\n".join(linhas)); box.configure(state="disabled")
        else:
            cols = list(zip(*rows))
            def rng(i): return max(cols[i]) - min(cols[i])
            volt_idx = [i for i, n in enumerate(names) if n.upper().startswith("U")]
            cur_idx = [i for i, n in enumerate(names) if n.upper().startswith("I")]
            # x = a tensão efetivamente varrida (maior variação); só conta se variar
            varying_volts = [i for i in volt_idx if rng(i) > 0]
            xi = max(varying_volts, key=rng) if varying_volts else (max(range(ncol), key=rng))
            if not cur_idx:
                cur_idx = [i for i in range(ncol) if i != xi]
            cur_idx = [i for i in cur_idx if rng(i) > 0] or cur_idx
            fig = Figure(figsize=(6, 4.4), dpi=96, facecolor=COL["bg"])
            ax = fig.add_subplot(111); ax.set_facecolor(COL["bg2"])
            xs = cols[xi]
            for i in cur_idx:
                ax.plot(xs, [abs(v) for v in cols[i]], marker="o", ms=3, lw=1.5, label=names[i])
            ax.set_xlabel(f"{names[xi]} (V)", color=COL["dim"], fontsize=9)
            ax.set_ylabel("|corrente| (A)", color=COL["dim"], fontsize=9)
            ax.set_title("Curva I-V (fort.61)", color=COL["fg"], fontsize=10)
            ax.tick_params(colors=COL["dim"], labelsize=8)
            ax.grid(True, alpha=0.2, color=COL["dim"])
            ax.legend(fontsize=8, facecolor=COL["bg2"], edgecolor=COL["border"], labelcolor=COL["fg"])
            for sp in ax.spines.values(): sp.set_color(COL["border"])
            fig.tight_layout()
            c = FigureCanvasTkAgg(fig, master=self.mm_iv_frame); c.draw()
            c.get_tk_widget().pack(fill="both", expand=True)

        # superfície 3D: lê o PIF (fort.30) e popula o seletor de campos
        try:
            lat, vert, campos = parse_minimos_pif(r.get("pif"))
        except Exception:
            lat, vert, campos = [], [], {}
        self._mm_pif_cache = (lat, vert, campos)
        for w in self.mm_3d_frame.winfo_children():
            w.destroy()
        nomes = list(campos.keys())
        self.mm_field_cb.configure(values=nomes)
        if nomes:
            self.mm_field.set(nomes[0])
            self._plot_minimos_3d()
        else:
            tk.Label(self.mm_3d_frame,
                     text=("Nenhum mapa 2-D neste resultado.\n\n"
                           "Para gerar a superfície 3D, rode no modo 2-D com mapas, ex.:\n"
                           "  OPTION MODEL=2-D\n  OUTPUT ALL=YES PIF=YES\n  BIAS UD=2. UG=1.5\n\n"
                           "O MINIMOS grava os campos no arquivo PIF; o Studio os desenha aqui\n"
                           "(o visualizador antigo, plotmtv, não é necessário)."),
                     font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"], justify="left").pack(padx=16, pady=16, anchor="w")

    def _plot_minimos_3d(self):
        lat, vert, campos = self._mm_pif_cache
        for w in self.mm_3d_frame.winfo_children():
            w.destroy()
        nome = self.mm_field.get()
        if not HAS_MPL:
            tk.Label(self.mm_3d_frame, text="matplotlib não disponível para o gráfico 3D.",
                     font=("Consolas", 10), bg=COL["bg"], fg=COL["accent"]).pack(padx=16, pady=16); return
        if not nome or nome not in campos or not lat or not vert:
            return
        try:
            import numpy as _np
            from matplotlib.figure import Figure
            nl, nv = len(lat), len(vert)
            Z = _np.array(campos[nome][:nl * nv]).reshape(nv, nl)
            X, Y = _np.meshgrid(_np.array(lat), _np.array(vert))
            fig = Figure(figsize=(7, 5), facecolor=COL["bg"])
            ax = fig.add_subplot(111, projection="3d")
            ax.plot_surface(X, Y, Z, cmap="viridis", linewidth=0, antialiased=True)
            ax.set_xlabel("lateral (µm)", fontsize=8)
            ax.set_ylabel("profundidade (µm)", fontsize=8)
            ax.set_zlabel(nome, fontsize=8)
            ax.set_title(f"MINIMOS — {nome} no corte do dispositivo", fontsize=9)
            ax.invert_yaxis()
            ax.tick_params(labelsize=7)
            fig.tight_layout()
            c = FigureCanvasTkAgg(fig, master=self.mm_3d_frame); c.draw()
            c.get_tk_widget().pack(fill="both", expand=True)
        except Exception as e:
            tk.Label(self.mm_3d_frame, text=f"Falha ao desenhar a superfície:\n{e}",
                     font=("Consolas", 9), bg=COL["bg"], fg=COL["accent"], justify="left").pack(padx=16, pady=16)

    # ── Aba Perfil (perfil de dopagem do SUPREM, evolução por etapa) ──
    def _build_profile_tab(self):
        wrap = tk.Frame(self.tab_profile, bg=COL["bg"]); wrap.pack(fill="both", expand=True)
        top = tk.Frame(wrap, bg=COL["bg2"]); top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="PERFIL DE DOPAGEM — evolução do processo na lâmina (SUPREM-III)",
                 font=("Consolas", 11, "bold"), bg=COL["bg2"], fg=COL["fg"]).pack(anchor="w", padx=6, pady=(6, 2))
        tk.Label(top, text="Roda o processo da aba Processo inserindo PRINT após cada etapa, e "
                           "mostra o perfil profundidade × concentração. (SUPREM-III é 1-D: só profundidade.)",
                 font=("Consolas", 8), bg=COL["bg2"], fg=COL["dim"], justify="left").pack(anchor="w", padx=6, pady=(0, 6))
        bar = tk.Frame(top, bg=COL["bg2"]); bar.pack(fill="x", padx=6, pady=(0, 8))
        self.prof_btn = tk.Button(bar, text="📉 Gerar perfil do processo", font=("Consolas", 10, "bold"),
                                  bg=COL["accent"], fg="#fff", bd=0, cursor="hand2", pady=5,
                                  command=self._run_profile)
        self.prof_btn.pack(side="left", padx=(0, 10))
        tk.Label(bar, text="Etapa:", font=("Consolas", 9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left")
        self.prof_step = tk.StringVar(value="")
        self.prof_step_cb = ttk.Combobox(bar, textvariable=self.prof_step, values=[], width=22, state="readonly")
        self.prof_step_cb.pack(side="left", padx=4)
        self.prof_step_cb.bind("<<ComboboxSelected>>", lambda e: self._draw_profile())
        tk.Label(bar, text="Visão:", font=("Consolas", 9), bg=COL["bg2"], fg=COL["dim"]).pack(side="left", padx=(10, 2))
        self.prof_view = tk.StringVar(value="especies")
        for txt, val in [("Espécies (log)", "especies"), ("Evolução (net)", "evolucao"),
                         ("Corte da lâmina", "corte")]:
            tk.Radiobutton(bar, text=txt, variable=self.prof_view, value=val, font=("Consolas", 8),
                           bg=COL["bg2"], fg=COL["fg"], selectcolor=COL["entry_bg"], activebackground=COL["bg2"],
                           command=self._draw_profile).pack(side="left")
        self.prof_canvas_frame = tk.Frame(wrap, bg=COL["bg"]); self.prof_canvas_frame.pack(fill="both", expand=True, padx=10, pady=6)
        self.prof_status = tk.Label(wrap, text="Monte o processo na aba Processo e clique em Gerar perfil.",
                                    font=("Consolas", 9), bg=COL["bg"], fg=COL["dim"], anchor="w")
        self.prof_status.pack(fill="x", padx=12, pady=(0, 8))
        self._prof_data = ([], [])      # (plan, blocks)

    def _run_profile(self):
        if not self.steps:
            messagebox.showwarning("Perfil", "Não há etapas de processo. Monte o processo na aba Processo primeiro.")
            return
        native = find_native_dir()
        if check_native(native):
            messagebox.showerror("Perfil", "Motor nativo do SUPREM-III indisponível:\n• "
                                 + "\n• ".join(check_native(native))); return
        try:
            deck, plan = build_profile_deck(self.title_var.get() or "Perfil", self.steps)
        except Exception as e:
            messagebox.showerror("Perfil", f"Falha ao montar o deck de perfil.\n({e})"); return
        self.prof_btn.configure(state="disabled", text="⏳ Rodando...")
        self.prof_status.configure(text="Rodando SUPREM-III e extraindo perfis por etapa...", fg=COL["dim"])
        def work():
            try:
                out = run_native_sync(deck, native)
                blocks = parse_suprem_profiles(out)
                self.after(0, lambda: self._profile_done(plan, blocks))
            except Exception as e:
                self.after(0, lambda: self._profile_error(str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _profile_error(self, msg):
        self.prof_btn.configure(state="normal", text="📉 Gerar perfil do processo")
        self.prof_status.configure(text=f"Erro: {msg}", fg=COL["accent"])

    def _profile_done(self, plan, blocks):
        self.prof_btn.configure(state="normal", text="📉 Gerar perfil do processo")
        if not blocks or len(blocks) < len(plan):
            self.prof_status.configure(
                text=f"Saída sem perfis completos ({len(blocks)} de {len(plan)} blocos). "
                     "Verifique se o processo roda sem erro na aba Resultados.", fg=COL["accent"])
            if not blocks:
                return
        self._prof_data = (plan[:len(blocks)], blocks)
        etapas = []
        for lab, _q in self._prof_data[0]:
            if lab not in etapas:
                etapas.append(lab)
        self.prof_step_cb.configure(values=etapas)
        if etapas:
            self.prof_step.set(etapas[-1])       # mostra a última etapa por padrão
        self.prof_status.configure(text=f"{len(etapas)} etapas capturadas. "
                                   "Escolha a etapa e a visão.", fg=COL["warm"])
        self._draw_profile()

    def _draw_profile(self):
        for w in self.prof_canvas_frame.winfo_children():
            w.destroy()
        plan, blocks = self._prof_data
        if not blocks or not HAS_MPL:
            if not HAS_MPL:
                tk.Label(self.prof_canvas_frame, text="matplotlib indisponível para o gráfico.",
                         font=("Consolas", 10), bg=COL["bg"], fg=COL["accent"]).pack(padx=16, pady=16)
            return
        import numpy as _np
        from matplotlib.figure import Figure
        view = self.prof_view.get()
        sel = self.prof_step.get()
        # índice: (label, quantidade) -> bloco
        idx = {(lab, q): b for (lab, q), b in zip(plan, blocks)}
        etapas = []
        for lab, _q in plan:
            if lab not in etapas:
                etapas.append(lab)

        fig = Figure(figsize=(7.5, 5), facecolor=COL["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(COL["bg2"] if "bg2" in COL else COL["bg"])

        def style(xlabel, ylabel, title):
            ax.set_xlabel(xlabel, color=COL["dim"], fontsize=9)
            ax.set_ylabel(ylabel, color=COL["dim"], fontsize=9)
            ax.set_title(title, color=COL["fg"], fontsize=10)
            ax.tick_params(colors=COL["dim"], labelsize=8)
            for sp in ax.spines.values(): sp.set_color(COL["border"])
            ax.grid(True, alpha=0.2, color=COL["dim"])

        if view == "especies":
            cores = {"Net": COL["fg"], "Boron": "#e06c3a", "Phosphorus": "#3a78e0",
                     "Arsenic": "#3ab06c", "Antimony": "#b03a8c"}
            for (lab, q), b in zip(plan, blocks):
                if lab != sel:
                    continue
                d, c = b
                if q == "Net":
                    ax.plot(d, [abs(v) for v in c], lw=2.0, color=cores.get(q, None), label="Net |ativo|")
                else:
                    if max((abs(v) for v in c), default=0) <= 0:
                        continue
                    ax.plot(d, [abs(v) for v in c], lw=1.3, color=cores.get(q, None), label=q)
            ax.set_yscale("log")
            style("profundidade (µm)", "concentração (cm⁻³)", f"Perfil em: {sel}")
            ax.legend(fontsize=8, facecolor=COL["bg2"], edgecolor=COL["border"], labelcolor=COL["fg"])
        elif view == "evolucao":
            import matplotlib as _mpl
            try:
                cmap = _mpl.colormaps["viridis"]
            except Exception:
                cmap = _mpl.cm.get_cmap("viridis")
            for i, lab in enumerate(etapas):
                b = idx.get((lab, "Net"))
                if not b:
                    continue
                d, c = b
                ax.plot(d, [abs(v) for v in c], lw=1.6,
                        color=cmap(i / max(1, len(etapas) - 1)), label=lab)
            ax.set_yscale("log")
            style("profundidade (µm)", "|net ativo| (cm⁻³)", "Evolução do perfil (net) por etapa")
            ax.legend(fontsize=7, facecolor=COL["bg2"], edgecolor=COL["border"], labelcolor=COL["fg"])
        else:  # corte da lâmina (faixa colorida por n/p)
            b = idx.get((sel, "Net"))
            if not b:
                tk.Label(self.prof_canvas_frame, text="Sem dado net para esta etapa.",
                         font=("Consolas", 10), bg=COL["bg"], fg=COL["dim"]).pack(padx=16, pady=16); return
            d, c = b
            arr = _np.array(c)
            sig = _np.sign(arr)
            mag = _np.log10(_np.abs(arr) + 1e9)              # piso p/ evitar log(0)
            z = (sig * mag).reshape(-1, 1)                   # + = N, - = P
            vmax = float(_np.max(_np.abs(z))) or 1.0
            im = ax.imshow(z, aspect="auto", cmap="RdBu",
                           extent=[0, 1, d[-1], d[0]], vmin=-vmax, vmax=vmax)
            ax.set_xticks([])
            ax.set_ylabel("profundidade (µm)", color=COL["dim"], fontsize=9)
            ax.set_title(f"Corte da lâmina — {sel}  (azul = N, vermelho = P)", color=COL["fg"], fontsize=10)
            ax.tick_params(colors=COL["dim"], labelsize=8)
            cb = fig.colorbar(im, ax=ax, shrink=0.8)
            cb.set_label("sinal · log₁₀|net|", color=COL["dim"], fontsize=8)
            cb.ax.tick_params(colors=COL["dim"], labelsize=7)
        fig.tight_layout()
        c = FigureCanvasTkAgg(fig, master=self.prof_canvas_frame); c.draw()
        c.get_tk_widget().pack(fill="both", expand=True)

    # ── Oxidation Tab ──
    def _build_oxidation_tab(self):
        wrap = tk.Frame(self.tab_oxid, bg=COL["bg"])
        wrap.pack(fill="both", expand=True)

        ctrl = tk.Frame(wrap, bg=COL["bg2"])
        ctrl.pack(fill="x", padx=10, pady=10)
        tk.Label(ctrl, text="ANÁLISE DE OXIDAÇÃO (Deal-Grove)", font=("Consolas",11,"bold"),
                 bg=COL["bg2"], fg=COL["fg"]).grid(row=0, column=0, columnspan=6, sticky="w", padx=6, pady=(6,8))

        def field(r, c, label, var, width=14):
            tk.Label(ctrl, text=label, font=("Consolas",9), bg=COL["bg2"],
                     fg=COL["dim"]).grid(row=r, column=c, sticky="e", padx=(8,3), pady=3)
            e = tk.Entry(ctrl, textvariable=var, width=width, font=("Consolas",10),
                         bg=COL["entry_bg"], fg=COL["fg"], insertbackground=COL["fg"], bd=1)
            e.grid(row=r, column=c+1, sticky="w", padx=(0,8), pady=3)
            return e

        self.ox_temp = tk.StringVar(value="1000")
        self.ox_times = tk.StringVar(value="20,40,70,80,100,120")
        self.ox_ambient = tk.StringVar(value="WetO2")
        self.ox_orient = tk.StringVar(value="100")
        self.ox_doping = tk.StringVar(value="1e15")
        self.ox_Blit = tk.StringVar(value="0.287")
        self.ox_BAlit = tk.StringVar(value="0.71")
        self.ox_cd_times = tk.StringVar(value="40,80")

        field(1, 0, "Temperatura (°C):", self.ox_temp)
        tk.Label(ctrl, text="Ambiente:", font=("Consolas",9), bg=COL["bg2"],
                 fg=COL["dim"]).grid(row=1, column=2, sticky="e", padx=(8,3))
        ttk.Combobox(ctrl, textvariable=self.ox_ambient, values=["WetO2","DryO2"],
                     width=10, state="readonly").grid(row=1, column=3, sticky="w", padx=(0,8))
        field(1, 4, "Orientação <>:", self.ox_orient, 8)
        field(2, 0, "Tempos (min, vírgula):", self.ox_times, 28)
        field(2, 4, "Dopagem subs. (cm⁻³):", self.ox_doping, 10)
        field(3, 0, "B literatura (µm²/h):", self.ox_Blit, 10)
        field(3, 2, "B/A literatura (µm/h):", self.ox_BAlit, 10)
        field(3, 4, "Tempos itens C/D (min):", self.ox_cd_times, 12)

        self.ox_btn = tk.Button(ctrl, text="🔥  Rodar análise de oxidação", font=("Consolas",10,"bold"),
                                bg=COL["accent"], fg="#fff", bd=0, cursor="hand2", pady=6,
                                command=self._run_oxidation)
        self.ox_btn.grid(row=4, column=0, columnspan=4, sticky="we", padx=8, pady=(8,4))
        self.ox_csv_btn = tk.Button(ctrl, text="💾 Exportar CSV", font=("Consolas",9),
                                    bg=COL["btn"], fg=COL["btn_fg"], bd=0, cursor="hand2",
                                    command=self._export_oxidation_csv, state="disabled")
        self.ox_csv_btn.grid(row=4, column=4, columnspan=2, sticky="we", padx=8, pady=(8,4))
        self.ox_status = tk.Label(ctrl, text="τ = 0 (sem óxido inicial).  Pronto.",
                                  font=("Consolas",9), bg=COL["bg2"], fg=COL["dim"])
        self.ox_status.grid(row=5, column=0, columnspan=6, sticky="w", padx=8, pady=(0,6))

        self.ox_results = tk.Frame(wrap, bg=COL["bg"])
        self.ox_results.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self._ox_data = None

    def _run_oxidation(self):
        native = find_native_dir()
        if native is None or check_native(native):
            messagebox.showerror("Motor nativo necessário",
                "A análise de oxidação usa o motor nativo do SUPREM-III.\n"
                "Gere/compile a pasta 'suprem-run' (build_suprem.sh) ao lado do Studio.")
            return
        try:
            temp = float(self.ox_temp.get().replace(",", "."))
            times = [float(x) for x in re.split(r"[,\s]+", self.ox_times.get().strip()) if x]
            if len(times) < 2:
                raise ValueError("informe pelo menos 2 tempos")
        except Exception as e:
            messagebox.showerror("Entrada inválida", f"Verifique temperatura/tempos.\n({e})")
            return
        amb = self.ox_ambient.get(); orient = self.ox_orient.get().strip() or "100"
        doping = self.ox_doping.get().strip() or "1e15"
        self.ox_btn.configure(state="disabled", text="⏳ Simulando...")
        self.ox_status.configure(text=f"Rodando {len(times)} oxidações ({amb}, {temp:.0f} °C)...")

        def worker():
            pts = []
            try:
                for t in times:
                    deck = (f"Title  Oxidacao {amb} {temp:.0f}C {t:g}min\n"
                            f"Initialize <{orient}> Silicon Boron Concentration={doping} Thickness=0.5 dX=.002\n"
                            f"Diffusion Temperature={temp:g} Time={t:g} {amb}\n"
                            f"Print Layer\nStop\n")
                    raw = run_native_sync(deck, native)
                    xo = parse_oxide_thickness(raw)
                    if xo is None or xo <= 0:
                        raise RuntimeError(f"não consegui ler a espessura em t={t:g} min")
                    pts.append((t, xo))
                self.after(0, lambda: self._show_oxidation_results(temp, amb, orient, pts))
            except Exception as e:
                self.after(0, lambda: self._oxidation_error(str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _sim_one_oxide(self, temp, amb, orient, t):
        """Roda uma única oxidação (tempo t) e devolve a espessura, ou None.
        Usado quando o usuário escolhe um tempo C/D fora da varredura."""
        native = find_native_dir()
        if native is None or check_native(native):
            return None
        doping = self.ox_doping.get().strip() or "1e15"
        deck = (f"Title  Oxidacao {amb} {temp:.0f}C {t:g}min\n"
                f"Initialize <{orient}> Silicon Boron Concentration={doping} Thickness=0.5 dX=.002\n"
                f"Diffusion Temperature={temp:g} Time={t:g} {amb}\n"
                f"Print Layer\nStop\n")
        try:
            return parse_oxide_thickness(run_native_sync(deck, native))
        except Exception:
            return None

    def _oxidation_error(self, msg):
        self.ox_btn.configure(state="normal", text="🔥  Rodar análise de oxidação")
        self.ox_status.configure(text="Erro.", fg=COL["accent"])
        messagebox.showerror("Erro na oxidação", msg)

    def _show_oxidation_results(self, temp, amb, orient, pts):
        self.ox_btn.configure(state="normal", text="🔥  Rodar análise de oxidação")
        self.ox_csv_btn.configure(state="normal")
        for w in self.ox_results.winfo_children():
            w.destroy()
        times = [p[0] for p in pts]; xos = [p[1] for p in pts]
        fit = deal_grove_fit(times, xos)
        try:
            Blit = float(self.ox_Blit.get().replace(",", ".")); BAlit = float(self.ox_BAlit.get().replace(",", "."))
        except ValueError:
            Blit, BAlit = 0.287, 0.71
        self._ox_data = {"temp": temp, "amb": amb, "orient": orient, "pts": pts, "fit": fit,
                         "Blit": Blit, "BAlit": BAlit}
        self.ox_status.configure(
            text=(f"B = {fit['B_h']:.4f} µm²/h | A = {fit['A']:.4f} µm | "
                  f"B/A = {fit['BA_h']:.4f} µm/h | R² = {fit['r2']:.5f}"), fg=COL["warm"])

        # painel: esquerda texto, direita gráfico
        left = tk.Frame(self.ox_results, bg=COL["bg"]); left.pack(side="left", fill="y", padx=(0,8))
        txt = scrolledtext.ScrolledText(left, font=("Consolas",9), bg=COL["entry_bg"], fg=COL["fg"],
                                        width=52, bd=0, wrap="word")
        txt.pack(fill="both", expand=True)
        lines = []
        lines.append(f"OXIDAÇÃO {amb}  —  {temp:.0f} °C  —  Si <{orient}>   (τ = 0)\n")
        lines.append("A) Espessuras simuladas (SUPREM-III):")
        lines.append(f"   {'t (min)':>8}   {'Xo (µm)':>9}")
        for t, x in pts:
            lines.append(f"   {t:8g}   {x:9.4f}")
        lines.append("")
        lines.append("B) Ajuste gráfico  t/Xo = (1/B)·Xo + A/B :")
        lines.append(f"   inclinação 1/B = {fit['m']:.4f} min/µm²")
        lines.append(f"   intercepto A/B = {fit['c']:.4f} min/µm")
        lines.append(f"   B   = {fit['B_h']:.4f} µm²/h  ({fit['B_min']:.5f} µm²/min)")
        lines.append(f"   A   = {fit['A']:.4f} µm")
        lines.append(f"   B/A = {fit['BA_h']:.4f} µm/h     R² = {fit['r2']:.5f}")
        lines.append("")
        lines.append("   Literatura:")
        lines.append(f"   B   = {Blit:.4f} µm²/h   (desvio {100*(fit['B_h']-Blit)/Blit:+.1f} %)")
        lines.append(f"   B/A = {BAlit:.4f} µm/h   (desvio {100*(fit['BA_h']-BAlit)/BAlit:+.1f} %)")
        lines.append("")
        lines.append("C) Recálculo Deal-Grove  vs  D) regimes:")
        lines.append(f"   {'t':>5} {'sim':>8} {'DG(C)':>8} {'linear':>8} {'parab':>8}  regime")
        xmap = dict(pts)
        # tempos escolhidos pelo usuário para os itens C/D (ex.: 40,80)
        try:
            cd_times = [float(x) for x in re.split(r"[,\s]+", self.ox_cd_times.get().strip()) if x]
        except Exception:
            cd_times = []
        if not cd_times:
            cd_times = [times[0], times[-1]]
        for t in cd_times:
            # "sim": usa o valor já simulado; se o tempo não está na varredura, simula agora
            xs = xmap.get(t)
            if xs is None:
                xs = self._sim_one_oxide(temp, amb, orient, t)
                if xs is not None:
                    xmap[t] = xs
            xc = deal_grove_xo(t, fit["A"], fit["B_min"])
            xlin = (fit["B_min"] / fit["A"]) * t
            xpar = (fit["B_min"] * t) ** 0.5
            if xs is None:
                lines.append(f"   {t:5g} {'—':>8} {xc:8.4f} {xlin:8.4f} {xpar:8.4f}  (sem sim)")
            else:
                reg = "linear" if abs(xlin - xs) < abs(xpar - xs) else "parabólico"
                lines.append(f"   {t:5g} {xs:8.4f} {xc:8.4f} {xlin:8.4f} {xpar:8.4f}  {reg}")
        lines.append("")
        lines.append("   Transição linear↔parabólico quando Xo ≈ A.")
        lines.append("   (óxido fino → linear; óxido espesso → parabólico)")
        txt.insert("1.0", "\n".join(lines))
        txt.configure(state="disabled")

        if HAS_MPL:
            fig = Figure(figsize=(6.2, 4.6), dpi=96, facecolor=COL["bg"])
            ax = fig.add_subplot(111); ax.set_facecolor(COL["bg2"])
            xs_plot = xos; ys_plot = [t / x for t, x in pts]
            ax.scatter(xs_plot, ys_plot, color="#e04830", zorder=3, label="pontos simulados")
            xmax = max(xs_plot) * 1.05
            ax.plot([0, xmax], [fit["c"], fit["m"] * xmax + fit["c"]], color="#4a90d9",
                    lw=1.6, label=f"t/Xo = {fit['m']:.2f}·Xo + {fit['c']:.2f}")
            ax.set_xlabel("Xo (µm)", color=COL["dim"], fontsize=10)
            ax.set_ylabel("t/Xo (min/µm)", color=COL["dim"], fontsize=10)
            ax.set_title(f"Item B — Linearização Deal-Grove ({amb}, {temp:.0f} °C)",
                         color=COL["fg"], fontsize=10)
            ax.tick_params(colors=COL["dim"], labelsize=9)
            ax.grid(True, alpha=0.2, color=COL["dim"])
            ax.legend(fontsize=8, facecolor=COL["bg2"], edgecolor=COL["border"], labelcolor=COL["fg"])
            for sp in ax.spines.values(): sp.set_color(COL["border"])
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=self.ox_results)
            canvas.draw()
            canvas.get_tk_widget().pack(side="left", fill="both", expand=True)
            self._ox_fig = fig

    def _export_oxidation_csv(self):
        if not self._ox_data:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                  filetypes=[("CSV", "*.csv")], initialfile="oxidacao.csv")
        if not path:
            return
        d = self._ox_data; fit = d["fit"]
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# Oxidacao {d['amb']} {d['temp']:.0f}C Si<{d['orient']}> tau=0\n")
                f.write("t_min,Xo_um,x=Xo,y=t/Xo\n")
                for t, x in d["pts"]:
                    f.write(f"{t:g},{x:.4f},{x:.4f},{t/x:.4f}\n")
                f.write("\n# Item B\n")
                f.write(f"B_um2_h,{fit['B_h']:.5f}\nA_um,{fit['A']:.5f}\n")
                f.write(f"B_over_A_um_h,{fit['BA_h']:.5f}\nR2,{fit['r2']:.6f}\n")
                f.write(f"B_lit_um2_h,{d['Blit']}\nBA_lit_um_h,{d['BAlit']}\n")
                f.write("\n# Itens C e D (t,sim,DealGrove,linear,parabolico,regime)\n")
                xmap = dict(d["pts"]); ends = [d["pts"][0][0], d["pts"][-1][0]]
                for t in ends:
                    xs = xmap[t]; xc = deal_grove_xo(t, fit["A"], fit["B_min"])
                    xlin = (fit["B_min"]/fit["A"])*t; xpar = (fit["B_min"]*t)**0.5
                    reg = "linear" if abs(xlin-xs) < abs(xpar-xs) else "parabolico"
                    f.write(f"{t:g},{xs:.4f},{xc:.4f},{xlin:.4f},{xpar:.4f},{reg}\n")
            messagebox.showinfo("CSV exportado", f"Salvo em:\n{path}")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))

    # ── Results Tab ──
    def _build_results_tab(self):
        bar = tk.Frame(self.tab_results, bg=COL["bg"])
        bar.pack(fill="x", padx=10, pady=10)
        tk.Button(bar, text="📂 Importar .OUT", font=("Consolas",9), bg=COL["accent"], fg="#fff", bd=0,
                  command=self._import_out, cursor="hand2", padx=8, pady=3).pack(side="left")
        tk.Button(bar, text="💾 Exportar CSV", font=("Consolas",9), bg=COL["bg3"], fg=COL["fg"], bd=0,
                  command=self._export_csv, cursor="hand2", padx=8, pady=3).pack(side="left", padx=5)

        self.results_container = tk.Frame(self.tab_results, bg=COL["bg"])
        self.results_container.pack(fill="both", expand=True, padx=10, pady=(0,10))

        self.no_results_lbl = tk.Label(self.results_container,
            text="Clique em ▶ SIMULAR ou importe arquivos .OUT",
            font=("Consolas",11), bg=COL["bg"], fg=COL["dim"])
        self.no_results_lbl.pack(expand=True)

    def _show_results(self, saved_dir=None):
        for w in self.results_container.winfo_children():
            w.destroy()

        if not self.results:
            tk.Label(self.results_container, text="Nenhum resultado", font=("Consolas",11),
                     bg=COL["bg"], fg=COL["dim"]).pack(expand=True)
            return

        # Caminho onde os .out foram salvos (se houver)
        if saved_dir is None:
            for res in self.results.values():
                p = res.get("path") if isinstance(res, dict) else None
                if p:
                    saved_dir = str(Path(p).parent); break
        if saved_dir:
            bar = tk.Frame(self.results_container, bg=COL["bg2"])
            bar.pack(fill="x", padx=5, pady=(4,6))
            tk.Label(bar, text="💾 .out salvos em: " + saved_dir, font=("Consolas",9),
                     bg=COL["bg2"], fg=COL["warm"], anchor="w").pack(side="left", padx=6, pady=4)
            tk.Button(bar, text="Abrir pasta", font=("Consolas",9), bg=COL["btn"],
                      fg=COL["btn_fg"], bd=0, padx=8,
                      command=lambda d=saved_dir: self._open_folder(d)).pack(side="right", padx=6, pady=3)

        # Chart
        if HAS_MPL:
            fig = Figure(figsize=(9,4.5), dpi=96, facecolor=COL["bg"])
            ax = fig.add_subplot(111)
            ax.set_facecolor(COL["bg2"])
            colors_list = ["#e04830","#4a90d9","#50b060","#c878d0","#d4a574","#e08848"]
            ci = 0
            COL_N, COL_P = "#4a90d9", "#e04830"   # N=azul, P=vermelho
            for name, res in self.results.items():
                data = res["data"]
                if not data: continue
                x = [d[0] for d in data]
                absy = [abs(d[1]) if abs(d[1]) > 1 else 1e-1 for d in data]
                has_sign = any(d[1] < 0 for d in data)
                if has_sign:
                    # perfil líquido (net): colore por tipo — N (azul) / P (vermelho)
                    labeled = {"N": False, "P": False}
                    start = 0
                    sg = [1 if d[1] >= 0 else -1 for d in data]
                    for i in range(1, len(data) + 1):
                        if i == len(data) or sg[i] != sg[start]:
                            tipo = "N" if sg[start] > 0 else "P"
                            lbl = (f"{name} — tipo {tipo}" if not labeled[tipo] else None)
                            labeled[tipo] = True
                            ax.semilogy(x[start:i + 1], absy[start:i + 1],
                                        color=(COL_N if tipo == "N" else COL_P),
                                        linewidth=1.7, label=lbl)
                            start = i
                    # junções reais: troca de sinal com persistência e magnitude
                    for xj in _detect_junctions(data):
                        ax.axvline(xj, color=COL["dim"], ls="--", lw=0.9, alpha=0.7)
                        ax.annotate(f"Xj={xj:.3f}µm", xy=(xj, ax.get_ylim()[1]),
                                    xytext=(3, -3), textcoords="offset points",
                                    fontsize=8, color=COL["fg"], va="top")
                else:
                    # perfil de espécie (sem sinal): uma cor só, sem marcação de junção
                    ax.semilogy(x, absy, label=name, color=colors_list[ci % len(colors_list)], linewidth=1.5)
                ci += 1
            ax.set_xlabel("Profundidade (µm)", color=COL["dim"], fontsize=10)
            ax.set_ylabel("Concentração (cm⁻³)", color=COL["dim"], fontsize=10)
            ax.tick_params(colors=COL["dim"], labelsize=9)
            ax.legend(fontsize=9, facecolor=COL["bg2"], edgecolor=COL["border"], labelcolor=COL["fg"])
            ax.grid(True, alpha=0.2, color=COL["dim"])
            for spine in ax.spines.values(): spine.set_color(COL["border"])
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=self.results_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
        else:
            tk.Label(self.results_container, text="(instale matplotlib para ver gráficos)",
                     font=("Consolas",10), bg=COL["bg"], fg=COL["dim"]).pack(pady=10)

        # Data summary
        for name, res in self.results.items():
            data = res["data"]
            if not data: continue
            info = f"{name}: {len(data)} pontos, x=[{data[0][0]:.4f}..{data[-1][0]:.4f}] µm"
            peak = max(data, key=lambda d: d[1])
            info += f", pico={peak[1]:.3E} em {peak[0]:.4f} µm"
            tk.Label(self.results_container, text=info, font=("Consolas",9), bg=COL["bg"],
                     fg=COL["dim"], anchor="w").pack(fill="x", padx=5, pady=1)

    def _open_folder(self, path):
        if not path:
            messagebox.showinfo("Pasta dos resultados", "Nenhuma pasta de resultados ainda."); return
        try:
            if IS_WIN:
                os.startfile(path)  # type: ignore[attr-defined]
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showinfo("Pasta dos resultados", f"Arquivos salvos em:\n{path}\n\n({e})")

    def _import_out(self):
        paths = filedialog.askopenfilenames(filetypes=[("SUPREM-III Output","*.out *.OUT *.txt"),("Todos","*.*")])
        for path in paths:
            text = Path(path).read_text(errors="replace")
            data = parse_out_file(text)
            if data:
                name = Path(path).name
                self.results[name] = {"data": data, "raw": text}
        if paths:
            self._show_results()
            self.notebook.select(self.tab_results)

    def _export_csv(self):
        for name, res in self.results.items():
            path = filedialog.asksaveasfilename(defaultextension=".csv",
                initialfile=name.replace(".OUT",".csv").replace(".out",".csv"))
            if path:
                lines = ["depth_um,concentration_cm3\n"]
                for d, c in res["data"]:
                    lines.append(f"{d:.4f},{c:.5E}\n")
                Path(path).write_text("".join(lines))

    # ── Simulação ──
    def _simulate(self):
        if not self.steps:
            messagebox.showwarning("Sem passos", "Adicione comandos ao processo primeiro.")
            return
        code = build_in_file(self.title_var.get(), self.steps)
        self._run_deck(code)

    def _run_in_file(self):
        """Roda um arquivo .in selecionado pelo usuário, enviando o texto LITERAL
        ao motor (sem passar pelo gerador de passos do Studio)."""
        path = filedialog.askopenfilename(
            title="Selecione o arquivo .in para rodar",
            filetypes=[("SUPREM-III Input", "*.in *.IN *.txt"), ("Todos", "*.*")])
        if not path:
            return
        try:
            deck = Path(path).read_text(encoding="latin1", errors="replace")
        except Exception as e:
            messagebox.showerror("Erro ao ler arquivo", str(e))
            return
        if not deck.strip():
            messagebox.showwarning("Arquivo vazio", "O arquivo selecionado está vazio.")
            return
        # mostra o deck literal na aba de Código (para conferência)
        try:
            self.code_text.delete("1.0", "end")
            self.code_text.insert("1.0", deck)
            self._code_user_edited = True
        except Exception:
            pass
        self._run_deck(deck)

    def _run_deck(self, code):
        """Envia o texto do deck (literal) ao motor: nativo de preferência,
        DOSBox como alternativa. Usado tanto pelo SIMULAR quanto pelo
        'Rodar arquivo .in'."""
        # 1) Motor NATIVO (sem DOSBox)
        native = find_native_dir()
        if native is not None:
            nat_problems = check_native(native)
            if not nat_problems:
                self.sim_btn.configure(state="disabled", text="⏳ Simulando...")
                self.sim_status.configure(text="SUPREM-III nativo executando...")
                run_suprem_native(code, native,
                                   callback_done=self._on_sim_done,
                                   callback_error=self._on_sim_error)
                return
            messagebox.showwarning("Motor nativo incompleto",
                "Encontrei os binários nativos, mas faltam itens:\n\n  - "
                + "\n  - ".join(nat_problems)
                + "\n\nRode a inicialização (INICIALIZAR.sh) ou recompile com "
                  "build_suprem.sh. Vou tentar o DOSBox como alternativa.")

        # 2) Fallback: motor DOS via DOSBox
        if not self.dosbox_path:
            messagebox.showerror("Sem motor de simulação",
                "Não encontrei os binários nativos do SUPREM-III nem o DOSBox.\n\n"
                "• Linux/Windows: gere o motor nativo com build_suprem.sh "
                "(coloque a pasta 'suprem-run' ao lado do Studio), ou\n"
                "• Configure o DOSBox em ⚙ DOSBox para usar o motor DOS.")
            return
        if not SUPREM_DIR.exists():
            messagebox.showerror("Engine não encontrada",
                f"Pasta '{SUPREM_DIR}' não encontrada.\nCopie os arquivos do SUPREM-III para esta pasta.")
            return
        problems = check_engine(SUPREM_DIR)
        if problems:
            messagebox.showerror("Binários corrompidos",
                "Os executáveis DOS do SUPREM-III estão corrompidos ou ausentes:\n\n  - "
                + "\n  - ".join(problems)
                + "\n\nUse o motor nativo (build_suprem.sh) ou substitua os arquivos "
                  "em 'suprem_engine/' por cópias íntegras.")
            return

        self.sim_btn.configure(state="disabled", text="⏳ Simulando...")
        self.sim_status.configure(text="DOSBox executando em background...")
        run_suprem(code, self.dosbox_path,
                   callback_done=self._on_sim_done,
                   callback_error=self._on_sim_error)

    def _on_sim_done(self, results):
        self.after(0, lambda: self._handle_results(results))

    def _handle_results(self, results):
        self.sim_btn.configure(state="normal", text="▶  SIMULAR")
        saved_dir = results.pop("__dir__", None) if isinstance(results, dict) else None
        if results:
            self.results = results
            n = len(results)
            self.sim_status.configure(text=f"✓ {n} arquivo(s) gerado(s)", fg=COL["warm"])
            self._show_results(saved_dir)
            self.notebook.select(self.tab_results)
            if saved_dir:
                messagebox.showinfo("Resultados salvos",
                    f"{n} arquivo(s) .out salvos em:\n\n{saved_dir}\n\n"
                    "Use estes arquivos no seu relatório.")
        else:
            self.sim_status.configure(text="⚠ Nenhum .OUT gerado", fg=COL["accent"])
            messagebox.showwarning("Sem resultados",
                "O SUPREM-III não gerou arquivos .OUT.\nVerifique se há comandos PRINT no processo.")

    def _on_sim_error(self, error):
        self.after(0, lambda: self._handle_error(error))

    def _handle_error(self, error):
        self.sim_btn.configure(state="normal", text="▶  SIMULAR")
        self.sim_status.configure(text="✕ Erro", fg=COL["accent"])
        messagebox.showerror("Erro na simulação", error)

    # ── DOSBox Config ──
    def _update_dosbox_status(self):
        native = find_native_dir()
        if native is not None and not check_native(native):
            self.status_lbl.configure(text="Motor: ✓ nativo", fg=COL["warm"])
        elif self.dosbox_path:
            self.status_lbl.configure(text="Motor: ✓ DOSBox", fg=COL["warm"])
        else:
            self.status_lbl.configure(text="Motor: ✕ (nativo/DOSBox ausente)", fg=COL["accent"])

    def _configure_dosbox(self):
        path = filedialog.askopenfilename(title="Selecione o executável do DOSBox",
            filetypes=[("Executável","*.exe" if IS_WIN else "*"),("Todos","*.*")])
        if path:
            self.dosbox_path = path
            save_dosbox_path(path)
            self._update_dosbox_status()

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = SupremApp()
    app.mainloop()
