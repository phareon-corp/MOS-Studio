#!/usr/bin/env bash
# ============================================================================
#  build_minimos.sh — compila o MINIMOS 6.1 (parte PLANAR, mm_pl) nativamente
#  Funciona no Linux (gfortran/gcc) e no Windows via MSYS2 MINGW64.
#
#  Uso:
#     ./build_minimos.sh /caminho/para/minimoswin6_1
#  Gera:  minimos-run/mm_pl[.exe]  +  copia stack.rul e examples/
#
#  Por que funciona sem o Compaq Fortran:
#   - O fonte abre as unidades FORTRAN SEM 'FILE=' (dependia do recurso
#     FORTnn do Compaq). No gfortran isso vira os nomes padrão fort.NN:
#         fort.15 = deck de entrada (NUMINP=15)
#         fort.16 = saída            (NUMOUT=16)
#         fort.31 = stack rule       (NUMRUL=31)
#         fort.61 = curva I-V        (NUMIVC=61)
#         unidade 6 = referência (stdout)
#     O Studio cuida de criar fort.15/fort.31 e ler fort.16/fort.61.
#   - gfortran 13 aceita as extensões VMS/Compaq (READONLY, SHARED) com
#     -std=legacy, então o fonte compila sem patches.
# ============================================================================
set -e
SRC="${1:?Informe a pasta do MINIMOS (que contém pl/ stdalone/ examples/)}"
SRC="$(cd "$SRC" && pwd)"
OUT="$(pwd)/minimos-run"
EXE=""
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) EXE=".exe";; esac

FC=gfortran; CC=gcc
FFLAGS="-cpp -std=legacy -ffixed-line-length-132 -fno-automatic -fallow-argument-mismatch -w -O2 -I$SRC/stdalone -I$SRC/pl"

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
echo ">> normalizando finais de linha e compilando..."
# copia fontes normalizando CRLF
mkdir s; cp "$SRC"/pl/*.F "$SRC"/pl/*.inc s/ 2>/dev/null || true
cp "$SRC"/stdalone/*.F "$SRC"/stdalone/*.inc "$SRC"/stdalone/*.c "$SRC"/stdalone/*.h s/ 2>/dev/null || true
for f in s/*.F s/*.c s/*.inc s/*.h; do [ -f "$f" ] && sed -i 's/\r$//' "$f"; done

# objetos que compõem o mm_pl (idêntico ao OBJ do pl/Makefile.win32)
PL="ac boltzman collect current doping driver gennum gummel hcinj ig mc mcinit \
    mem mgrid mini2d move msol mstack output parse phys scat sub0"
SA_F="fltpar rndm1 zzzdat"
SA_C="sacsol solaux solgau solilu solsca solbicgs sol soltim"

cd s
for b in $PL $SA_F;  do $FC $FFLAGS -c "$b.F" -o "$b.o";  done
for b in $SA_C;      do $CC -O2 -w -I. -c "$b.c" -o "c_$b.o"; done

echo ">> linkando mm_pl$EXE ..."
OBJS=""; for b in $PL $SA_F; do OBJS="$OBJS $b.o"; done
for b in $SA_C; do OBJS="$OBJS c_$b.o"; done
$FC -o "mm_pl$EXE" $OBJS

mkdir -p "$OUT/examples"
cp "mm_pl$EXE" "$OUT/"
cp "$SRC"/bin/stack.rul "$OUT/" 2>/dev/null || cp "$SRC"/stack.rul "$OUT/" 2>/dev/null || true
cp "$SRC"/examples/*.inp "$OUT/examples/" 2>/dev/null || true
echo ">> pronto: $OUT/mm_pl$EXE"
ls -la "$OUT"
