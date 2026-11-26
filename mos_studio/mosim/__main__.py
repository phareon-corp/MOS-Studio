"""Uso: python -m mos_studio.mosim deck.inp [-o base]

Grava base.out, base.ref e base.iv (base = nome do deck sem extensão).
"""
import argparse
import sys
from pathlib import Path

from .executar import executar


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mosim", description=__doc__)
    ap.add_argument("deck")
    ap.add_argument("-o", "--base")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.deck)
    base = Path(a.base) if a.base else p.with_suffix("")
    r = executar(p.read_text(errors="replace"), log=print if a.verbose else None)
    for ext in ("out", "ref", "iv"):
        if r[ext]:
            Path(f"{base}.{ext}").write_text(r[ext])
    return r["returncode"]


if __name__ == "__main__":
    sys.exit(main())
