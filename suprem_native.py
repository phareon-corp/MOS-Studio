"""
suprem_native.py — Backend NATIVO do SUPREM-III (sem DOSBox).
SyncField Corporation

Executa o SUPREM-III compilado nativamente (binarios setup/genii/sup3 gerados
por build_suprem.sh). Substitui o caminho via DOSBox no Linux: mesma assinatura
de run_suprem(), portanto e' um drop-in para o SUPREM-III Studio.

Espera uma pasta "run" contendo:
    setup, genii, sup3            (binarios compilados)
    S3cof0, S3uky0                (coeficientes/chave, gerados na inicializacao)
    S3err0, S3fky0, S3ibo0, ...   (arquivos de dados)
"""

import os
import re
import shutil
import tempfile
import threading
import subprocess
from pathlib import Path

# Arquivos de dados que viram variaveis de ambiente (nomes logicos do SUPREM)
_ENV_FILES = [
    "S3cof0", "S3err0", "S3fky0", "S3uky0",
    "S3ibo0", "S3ibo1", "S3ibf0", "S3iph0",
    "S3ias0", "S3isb0",
]


def strip_plot(in_content):
    """Remove comandos PLOT (e continuacoes '+'). O PLOT abre dispositivo
    grafico; aqui os perfis sao lidos dos arquivos de saida."""
    out, skipping = [], False
    for raw in in_content.replace("\r\n", "\n").split("\n"):
        s = raw.strip()
        if skipping and s.startswith("+"):
            continue
        skipping = s.upper().startswith("PLOT")
        if skipping:
            continue
        out.append(raw)
    return "\n".join(out)


def find_run_dir(hint=None):
    """Localiza a pasta 'run' do SUPREM-III nativo."""
    candidates = []
    if hint:
        candidates.append(Path(hint))
    env = os.environ.get("SUPREM_RUN_DIR")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent
    candidates += [
        here / "run",
        here / "suprem_build" / "Release" / "run",
        Path.home() / "suprem" / "run",
    ]
    for c in candidates:
        if c and (c / "sup3").exists() and (c / "genii").exists():
            return c
    return None


def check_run_dir(run_dir):
    """Confere se a pasta nativa esta completa/inicializada. Lista de problemas."""
    problems = []
    if run_dir is None or not run_dir.exists():
        return ["pasta 'run' do SUPREM-III nativo nao encontrada"]
    for b in ("setup", "genii", "sup3"):
        p = run_dir / b
        if not p.exists():
            problems.append(f"binario ausente: {b}")
        elif not os.access(p, os.X_OK):
            problems.append(f"binario sem permissao de execucao: {b}")
    for f in ("S3cof0", "S3uky0"):
        if not (run_dir / f).exists():
            problems.append(f"coeficiente ausente: {f} (rode a inicializacao)")
    return problems


def run_suprem_native(in_content, run_dir, callback_done, callback_error):
    """Roda setup -> genii -> sup3 nativamente, em background.

    callback_done(results): results = lista de dicts
        {'name', 'path', 'content', 'rows'(opcional)}
    callback_error(msg)
    """
    def _run():
        work = None
        try:
            rd = Path(run_dir).resolve()
            problems = check_run_dir(rd)
            if problems:
                callback_error("SUPREM-III nativo indisponivel:\n  - " +
                               "\n  - ".join(problems))
                return

            work = Path(tempfile.mkdtemp(prefix="suprem_nat_"))
            deck = strip_plot(in_content)
            (work / "INPUT.IN").write_text(deck, encoding="ascii", errors="replace")

            # variaveis de ambiente apontando para os dados (caminhos absolutos)
            env = dict(os.environ)
            for name in _ENV_FILES:
                fp = rd / name
                if fp.exists():
                    env[name] = str(fp)
            env["S3prs0"] = "S3prs0"  # relativo (cwd=work); nomes curtos p/ o sup3

            # IMPORTANTE: o sup3 trunca nomes de arquivo de saida longos (~20 ch).
            # Por isso rodamos com cwd=work e passamos nomes RELATIVOS curtos.
            out_name = "OUTPUT.OUT"
            inf_name = "RUNINFO.TXT"
            out_file = work / out_name
            inf_file = work / inf_name

            def run(bin_name, args):
                return subprocess.run(
                    [str(rd / bin_name)] + args,
                    cwd=str(work), env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    timeout=600,
                )

            # 1) setup  (cabecalho/versao) -> grava no inicio do OUTPUT
            run("setup", ["INPUT.IN", out_name])
            # 2) genii  (parser): le INPUT.IN, gera S3prs0; loga em OUTPUT
            g = run("genii", ["INPUT.IN", out_name, inf_name])
            if g.returncode != 0:
                log = g.stdout.decode("latin1", "replace")
                callback_error("Erro no genii (parser do deck):\n" + log[-1500:])
                return
            # 3) sup3   (simulador): le S3prs0, escreve resultados em OUTPUT
            s = run("sup3", [out_name, inf_name])
            if s.returncode != 0:
                log = s.stdout.decode("latin1", "replace")
                callback_error("Erro no sup3 (simulador):\n" + log[-1500:])
                return

            # coletar saidas: OUTPUT.OUT + qualquer FILENAME= dos PRINT/PLOT
            wanted = {"OUTPUT.OUT"}
            for line in deck.split("\n"):
                m = re.search(r"FILENAME=(\S+)", line, re.IGNORECASE)
                if m:
                    wanted.add(m.group(1).upper())

            results = []
            for f in sorted(work.iterdir()):
                up = f.name.upper()
                if up == "INPUT.IN" or up.startswith("S3PRS0"):
                    continue
                if (up in wanted or up.endswith(".OUT") or up.endswith(".TXT")
                        or up.endswith(".LST")) and f.is_file() and f.stat().st_size > 10:
                    txt = f.read_text(encoding="latin1", errors="replace")
                    results.append({
                        "name": f.name,
                        "path": str(f),
                        "content": txt,
                        "rows": _parse_profile(txt),
                    })

            if not results:
                callback_error("Simulacao concluiu, mas nenhum arquivo de saida "
                               "com dados foi produzido. Confira os comandos PRINT do deck.")
                return
            callback_done(results)

        except subprocess.TimeoutExpired:
            callback_error("Tempo esgotado ao executar o SUPREM-III nativo.")
        except Exception as e:
            callback_error(f"Falha ao executar o SUPREM-III nativo: {e}")
        finally:
            if work and work.exists():
                shutil.rmtree(work, ignore_errors=True)

    threading.Thread(target=_run, daemon=True).start()


def _parse_profile(txt):
    """Extrai linhas numericas (profundidade x concentracao) de uma tabela PRINT,
    se houver. Retorna lista de tuplas de floats (pode ser vazia)."""
    rows = []
    for line in txt.splitlines():
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
        if len(nums) >= 2:
            try:
                vals = [float(x) for x in nums]
                # heuristica: 1a coluna profundidade plausivel (>=0, < 1e4 microns)
                if 0.0 <= vals[0] < 1e4:
                    rows.append(tuple(vals))
            except ValueError:
                pass
    return rows


if __name__ == "__main__":
    # teste rapido de linha de comando: python3 suprem_native.py deck.in [run_dir]
    import sys
    deck_path = sys.argv[1]
    rd = sys.argv[2] if len(sys.argv) > 2 else find_run_dir()
    done = {}
    run_suprem_native(
        Path(deck_path).read_text(),
        rd,
        callback_done=lambda r: done.setdefault("r", r),
        callback_error=lambda m: print("ERRO:", m),
    )
    import time
    for _ in range(60):
        if "r" in done:
            break
        time.sleep(1)
    for f in done.get("r", []):
        print(f"=== {f['name']} ({len(f['content'])} bytes, "
              f"{len(f['rows'])} linhas numericas) ===")
        print(f["content"][:800])
