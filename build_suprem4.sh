#!/usr/bin/env bash
# ============================================================
#  build_suprem4.sh  -  Compila o SUPREM-IV.GS (Stanford,
#  release B.9305, via cogenda/suprem4) NATIVO em 64 bits.
#  SyncField Corporation
#
#  Pre-requisitos no Fedora:
#      sudo dnf install gcc make git
#  (Fortran NAO e' necessario: ver "Por que sem Fortran" abaixo.)
#
#  Uso:
#      ./build_suprem4.sh                  # clona o fonte da rede
#      ./build_suprem4.sh /caminho/do/fonte  # usa uma copia local
#
#  Resultado: suprem4-run/ ao lado do pacote mos_studio, com
#  bin/suprem, data/{suprem.uk,modelrc,sup4gs.imp} e examples/.
#  O MOS-Studio procura exatamente essa pasta (paths.SUPREM4_DIRS).
# ============================================================
#
#  Por que 64 bits
#  ---------------
#  O Makefile de fabrica compila com "gcc -m32". Em vez de arrastar
#  a camada de 32 bits (glibc-devel.i686 e amigos) so' para esse
#  binario, compilamos em 64 bits -- o que exige o patch 0001, ver
#  abaixo. O SUPREM-IV nao guarda ponteiros em int, so' a camada de
#  shell tinha copias de string invalidas.
#
#  Por que sem Fortran
#  -------------------
#  Tres arquivos .f acompanham o fonte (math/vector.f, finel/toms508.f,
#  finel/interface.f), mas nenhum entra nesta configuracao:
#    - vector.f  -> so' em CONVEX/CRAY; em SYSV valem as versoes C
#                   numfac/numbac de math/blklu.c;
#    - toms508.f e interface.f -> so' sao chamados quando NO_F77
#                   esta ausente (ver finel/tomcal.c).
#  Com -DSYSV -DNO_F77 o programa fecha so' com C. Se um dia o
#  reordenador TOMS-508 for necessario, e' aqui que o gfortran volta.
#
#  Por que sem graficos
#  --------------------
#  Compilamos gpsup/gpfake.c (os stubs vazios), nao a camada X11 nem
#  o gplot. O MOS-Studio desenha os proprios graficos a partir das
#  tabelas do "print.1d"; abrir janela do motor seria estorvo numa
#  execucao headless. Mesma decisao do SUPREM-III (ver ADR 0001).
# ============================================================
set -euo pipefail

FONTE_GIT="https://github.com/cogenda/suprem4.git"
AQUI="$(cd "$(dirname "$0")" && pwd)"
TRAB="$AQUI/suprem4_build"
DESTINO="$AQUI/suprem4-run"
PATCHES="$AQUI/patches/suprem4"

echo ">> MOS-Studio: build do SUPREM-IV.GS (64 bits)"

# ---- 0. ferramentas ----------------------------------------
for f in gcc make; do
    command -v "$f" >/dev/null || { echo "!! falta '$f' (sudo dnf install gcc make)"; exit 1; }
done

# ---- 1. obter o fonte --------------------------------------
rm -rf "$TRAB"; mkdir -p "$TRAB"
if [ $# -ge 1 ]; then
    LOCAL="$1"
    test -d "$LOCAL/src" || { echo "!! '$LOCAL' nao parece o fonte do suprem4 (sem src/)"; exit 1; }
    echo ">> Copiando fonte local: $LOCAL"
    cp -a "$LOCAL/." "$TRAB/fonte/"
else
    command -v git >/dev/null || { echo "!! falta 'git' (ou passe o fonte local como argumento)"; exit 1; }
    echo ">> Clonando $FONTE_GIT"
    git clone --depth 1 "$FONTE_GIT" "$TRAB/fonte" >/dev/null 2>&1 \
        || { echo "!! clone falhou (sem rede?). Baixe o fonte e passe o caminho como argumento."; exit 1; }
fi
FONTE="$TRAB/fonte"
SRC="$FONTE/src"
test -f "$SRC/main.c" || { echo "!! fonte incompleto: sem src/main.c"; exit 1; }

# ---- 2. patches --------------------------------------------
# Sem o 0001 o build de 64 bits compila e linka, mas corrompe a
# expansao de "foreach v (a to b step c)" -- o motor engole valores
# truncados sem reclamar. Por isso o patch e' obrigatorio, nao opcional.
if [ -d "$PATCHES" ]; then
    for p in "$PATCHES"/*.patch; do
        [ -e "$p" ] || continue
        echo ">> Aplicando $(basename "$p")"
        patch -p1 -d "$FONTE" -s < "$p" \
            || { echo "!! patch $(basename "$p") nao aplicou -- o fonte mudou?"; exit 1; }
    done
fi

# ---- 3. compilar -------------------------------------------
OBJ="$TRAB/obj"; mkdir -p "$OBJ"
LOG="$TRAB/compilacao.log"; : > "$LOG"
# -std=gnu89: o fonte e' K&R/C89 (definicoes de funcao com lista de
#   tipos separada), que o padrao atual do gcc recusa.
# -fcommon:   variaveis de tabela declaradas sem 'extern' em varios
#   .c contam com a fusao de simbolos comuns do linker antigo.
CFLAGS="-std=gnu89 -fcommon -O2 -w -DDEVICE -DSYSV -DNO_F77 -I$SRC/include"
# Mesma lista de src/wscript. 'misc/sint.c' fica fora: duplica
# check/sint.c e o linker rejeita o simbolo repetido.
DIRS="diffuse oxide mesh math shell check implant refine finel device imagetool dbase misc geom plot"

echo ">> Compilando (pode levar um minuto)"
for d in $DIRS; do
    for f in "$SRC/$d"/*.c; do
        [ -e "$f" ] || continue
        b="$(basename "$f" .c)"
        [ "$d/$b" = "misc/sint" ] && continue
        gcc $CFLAGS -c "$f" -o "$OBJ/${d}__${b}.o" 2>>"$LOG" \
            || { echo "!! falhou ao compilar $d/$b (veja $LOG)"; exit 1; }
    done
done
# Stubs de grafico em lugar da camada X11/gplot (ver cabecalho).
gcc $CFLAGS -c "$SRC/gpsup/gpfake.c" -o "$OBJ/gpsup__gpfake.o" 2>>"$LOG"

# main.c carrega os caminhos dos arquivos de dados em tempo de
# compilacao. As variaveis de ambiente SUP4KEYFILE/SUP4MODELRC/
# SUP4IMPDATA/SUP4MANDIR ainda sobrepoem esses padroes em execucao,
# e e' assim que o MOS-Studio aponta para a propria pasta de dados.
gcc $CFLAGS \
    -DMANLOC="\"$DESTINO/help\"" \
    -DKEYLOC="\"$DESTINO/data/suprem.uk\"" \
    -DMODELLOC="\"$DESTINO/data/modelrc\"" \
    -DIMPLOC="\"$DESTINO/data/sup4gs.imp\"" \
    -c "$SRC/main.c" -o "$OBJ/main.o" 2>>"$LOG" \
    || { echo "!! falhou ao compilar main.c (veja $LOG)"; exit 1; }

echo ">> Linkando"
gcc -O2 "$OBJ"/*.o -lm -o "$TRAB/suprem" 2>>"$LOG" \
    || { echo "!! link falhou (veja $LOG)"; exit 1; }

# ---- 4. keyread + suprem.uk --------------------------------
# O motor nao le data/suprem.key direto: precisa da forma binaria
# (suprem.uk), gerada pelo utilitario keyread que vem no fonte.
echo ">> Compilando keyread e gerando suprem.uk"
gcc -std=gnu89 -fcommon -O2 -w -DSYSV -I"$SRC/include" -I"$SRC/keyread" \
    "$SRC/keyread/parser.c" "$SRC/keyread/expand.c" \
    "$SRC/keyread/main.c" "$SRC/keyread/write.c" \
    -o "$TRAB/keyread" 2>>"$LOG" \
    || { echo "!! falhou ao compilar keyread (veja $LOG)"; exit 1; }

# ---- 5. instalar -------------------------------------------
echo ">> Instalando em $DESTINO"
rm -rf "$DESTINO"
mkdir -p "$DESTINO/bin" "$DESTINO/data" "$DESTINO/help" "$DESTINO/examples"
install -m 755 "$TRAB/suprem"  "$DESTINO/bin/suprem"
install -m 755 "$TRAB/keyread" "$DESTINO/bin/keyread"
install -m 644 "$SRC/data/modelrc"    "$DESTINO/data/modelrc"
install -m 644 "$SRC/data/sup4gs.imp" "$DESTINO/data/sup4gs.imp"
install -m 644 "$SRC/data/suprem.key" "$DESTINO/data/suprem.key"
( cd "$DESTINO" && ./bin/keyread data/suprem.uk < data/suprem.key >/dev/null ) \
    || { echo "!! keyread falhou ao gerar suprem.uk"; exit 1; }
test -s "$DESTINO/data/suprem.uk" || { echo "!! suprem.uk saiu vazio"; exit 1; }

# Os exemplos de fabrica vao junto: a suite de testes do MOS-Studio
# roda alguns deles como regressao do motor (tests/test_suprem4.py).
cp -a "$FONTE/examples/." "$DESTINO/examples/"
[ -f "$FONTE/doc/Suprem-IV.GS.ps" ] && cp "$FONTE/doc/Suprem-IV.GS.ps" "$DESTINO/"
cp "$FONTE/README" "$DESTINO/README.upstream" 2>/dev/null || true

# ---- 6. teste de fumaca ------------------------------------
echo ">> Teste de fumaca (exemplo 1 de fabrica: implante de boro + difusao)"
FUMACA="$TRAB/fumaca"; mkdir -p "$FUMACA"
cp "$DESTINO/examples/exam1/boron.in" "$FUMACA/deck.in"
if ( cd "$FUMACA" && "$DESTINO/bin/suprem" deck.in >saida.txt 2>&1 ) \
   && grep -q "Solving" "$FUMACA/saida.txt"; then
    echo ">> OK: o motor rodou o exemplo 1."
else
    echo "!! o binario compilou mas nao rodou o exemplo 1. Saida:"
    tail -20 "$FUMACA/saida.txt" || true
    exit 1
fi

cat <<FIM

============================================================
 SUPREM-IV.GS instalado em:
   $DESTINO/bin/suprem

 O MOS-Studio acha essa pasta sozinho. Para usar na mao:
   export SUP4KEYFILE=$DESTINO/data/suprem.uk
   export SUP4MODELRC=$DESTINO/data/modelrc
   export SUP4IMPDATA=$DESTINO/data/sup4gs.imp
   $DESTINO/bin/suprem meu_deck.in

 Fonte de trabalho preservado em $TRAB (apague quando quiser).
============================================================
FIM
