#!/usr/bin/env bash
# ============================================================================
#  build_suprem4_windows.sh — compila o SUPREM-IV.GS para Windows (x86-64),
#  por compilação cruzada a partir do Linux. SyncField Corporation
#
#  Pré-requisitos no Fedora:
#      sudo dnf install mingw64-gcc
#  (opcional, para o teste de fumaça sem VM:  sudo dnf install wine)
#
#  Uso:
#      ./build_suprem4_windows.sh
#  Gera: suprem4-run-win/{bin,data,help,examples}
#
#  POR QUE COMPILAÇÃO CRUZADA, E NÃO DENTRO DO WINDOWS
#  ---------------------------------------------------
#  O fonte é C de 1993 e não tem nada de específico de sistema além da
#  camada gráfica, que já sai de fora (ver build_suprem4.sh). Compilar aqui
#  dá um resultado reprodutível, versionável e testável com wine, sem
#  depender de um toolchain instalado à mão dentro de uma máquina virtual.
#
#  AS DIFERENÇAS EM RELAÇÃO AO BUILD DO LINUX
#  ------------------------------------------
#  1. Os caminhos dos arquivos de dados são compilados com barra invertida
#     e ficam RELATIVOS ao executável. No Linux eles apontam para a pasta de
#     instalação; no Windows o aplicativo pode estar em qualquer lugar, então
#     o motor é sempre chamado com as variáveis SUP4KEYFILE/SUP4MODELRC/
#     SUP4IMPDATA/SUP4MANDIR apontando para a pasta de dados (é o que
#     ``core/suprem4._environment`` já faz nos dois sistemas).
#  2. Uma camada de compatibilidade POSIX de três funções entra no lugar do
#     que o mingw não tem — ver patches/suprem4/win-compat/README.md.
#  3. O ``keyread`` é compilado DUAS vezes — uma para Windows, que vai no
#     pacote, e outra para Linux, que gera o ``suprem.uk`` aqui mesmo. O
#     arquivo é binário mas independente de plataforma (foi conferido: o
#     mesmo .uk roda nos dois), e gerá-lo aqui evita precisar do wine.
# ============================================================================
set -e

CROSS="${CROSS:-x86_64-w64-mingw32}"
CC_WIN="$CROSS-gcc"
command -v "$CC_WIN" >/dev/null || {
    echo "!! falta $CC_WIN (sudo dnf install mingw64-gcc)"; exit 1; }
command -v gcc >/dev/null || { echo "!! falta gcc nativo"; exit 1; }

RAIZ="$(cd "$(dirname "$0")" && pwd)"
SRC="$RAIZ/suprem4_build/fonte/src"
test -d "$SRC" || {
    echo "!! fonte do SUPREM-IV não encontrado em $SRC"
    echo "   rode antes: ./build_suprem4.sh"; exit 1; }

TRAB="$RAIZ/suprem4_build/win"
OBJ="$TRAB/obj"
LOG="$TRAB/compilacao.log"
DESTINO="$RAIZ/suprem4-run-win"
rm -rf "$TRAB" "$DESTINO"
mkdir -p "$OBJ" "$DESTINO/bin" "$DESTINO/data" "$DESTINO/help"
: > "$LOG"

# gnu89 e -fcommon pelos mesmos motivos do build do Linux: o fonte é K&R
# tardio e declara variáveis comuns em vários arquivos.
# A camada de compatibilidade POSIX vem ANTES do include do fonte, para que
# os cabeçalhos que o mingw não tem (sys/times.h, sys/file.h, sys/param.h,
# pwd.h) sejam encontrados ali. Ver patches/suprem4/win-compat/README.md.
COMPAT="$RAIZ/patches/suprem4/win-compat"
test -d "$COMPAT" || { echo "!! falta $COMPAT"; exit 1; }
# -DSYSV fica, como no build do Linux: o bloco que ele liga em sysdep.h é só
# o <fcntl.h> (de onde vêm O_WRONLY e companhia) e uns apelidos de string,
# tudo que o mingw tem. Sem ele, imagetool/makeframe.c não acha O_CREAT.
# __USE_MINGW_ANSI_STDIO troca o printf do msvcrt pelo do próprio mingw.
# Motivo: o msvcrt imprime expoente com três dígitos ("6.1e-015"), herança do
# MSVC antigo, enquanto o C padrão e o Linux usam dois ("6.1e-15"). Sem isso a
# saída do Windows difere da do Linux em toda linha com número em notação
# científica — os valores são os mesmos, mas os relatórios deixam de ser
# comparáveis e os leitores do MOS-Studio passam a ver dois formatos. Com a
# macro, conferido, a saída dos dois sistemas fica idêntica byte a byte.
CFLAGS="-std=gnu89 -fcommon -O2 -w -D__USE_MINGW_ANSI_STDIO=1 -DDEVICE -DSYSV -DNO_F77 -I$COMPAT -I$SRC/include"

DIRS="diffuse oxide mesh math shell check implant refine finel device imagetool dbase misc geom plot"

echo ">> Compilando para Windows (pode levar um minuto)"
for d in $DIRS; do
    for f in "$SRC/$d"/*.c; do
        [ -e "$f" ] || continue
        b="$(basename "$f" .c)"
        # misc/sint.c duplica check/sint.c; o linker recusa o símbolo repetido
        [ "$d/$b" = "misc/sint" ] && continue
        "$CC_WIN" $CFLAGS -c "$f" -o "$OBJ/${d}__${b}.o" 2>>"$LOG" \
            || { echo "!! falhou em $d/$b (veja $LOG)"; exit 1; }
    done
done
"$CC_WIN" $CFLAGS -c "$SRC/gpsup/gpfake.c" -o "$OBJ/gpsup__gpfake.o" 2>>"$LOG"
"$CC_WIN" $CFLAGS -c "$COMPAT/win_compat.c" -o "$OBJ/win_compat.o" 2>>"$LOG" \
    || { echo "!! falhou na camada de compatibilidade (veja $LOG)"; exit 1; }

# Caminhos padrão relativos ao executável. Valem só como último recurso: o
# MOS-Studio sempre passa as variáveis de ambiente.
"$CC_WIN" $CFLAGS \
    -DMANLOC='"help"' \
    -DKEYLOC='"data\\suprem.uk"' \
    -DMODELLOC='"data\\modelrc"' \
    -DIMPLOC='"data\\sup4gs.imp"' \
    -c "$SRC/main.c" -o "$OBJ/main.o" 2>>"$LOG" \
    || { echo "!! falhou em main.c (veja $LOG)"; exit 1; }

echo ">> Linkando suprem.exe"
"$CC_WIN" -O2 -static "$OBJ"/*.o -lm -o "$TRAB/suprem.exe" 2>>"$LOG" \
    || { echo "!! link falhou (veja $LOG)"; exit 1; }

echo ">> Compilando keyread (Windows e nativo)"
KEYSRC="$SRC/keyread/parser.c $SRC/keyread/expand.c $SRC/keyread/main.c $SRC/keyread/write.c"
# O keyread não passa pelo sysdep.h, que é quem inclui <fcntl.h> no resto do
# fonte; sem o -include ele não acha O_WRONLY/O_CREAT/O_TRUNC.
KEYFLAGS="-std=gnu89 -fcommon -O2 -w -D__USE_MINGW_ANSI_STDIO=1 -include fcntl.h -I$COMPAT -I$SRC/include -I$SRC/keyread"
# A camada entra aqui também: é ela que põe a CRT em modo binário, e sem
# isso o keyread.exe escreve o suprem.uk com CRLF e o motor o recusa.
"$CC_WIN" $KEYFLAGS -static $KEYSRC "$COMPAT/win_compat.c" \
    -o "$TRAB/keyread.exe" 2>>"$LOG" \
    || { echo "!! keyread.exe falhou (veja $LOG)"; exit 1; }
gcc $KEYFLAGS -DSYSV $KEYSRC -o "$TRAB/keyread_nativo" 2>>"$LOG" \
    || { echo "!! keyread nativo falhou (veja $LOG)"; exit 1; }

echo ">> Instalando em $DESTINO"
install -m 755 "$TRAB/suprem.exe"  "$DESTINO/bin/suprem.exe"
install -m 755 "$TRAB/keyread.exe" "$DESTINO/bin/keyread.exe"
for f in modelrc sup4gs.imp suprem.key; do
    install -m 644 "$SRC/data/$f" "$DESTINO/data/$f"
done
# O suprem.uk é gerado aqui, com o keyread nativo: o formato não depende de
# plataforma e assim o pacote fica pronto sem precisar rodar nada no Windows.
( cd "$DESTINO" && "$TRAB/keyread_nativo" data/suprem.uk < data/suprem.key >/dev/null ) \
    || { echo "!! keyread não gerou o suprem.uk"; exit 1; }

if [ -d "$RAIZ/suprem4-run/examples" ]; then
    cp -r "$RAIZ/suprem4-run/examples" "$DESTINO/examples"
elif [ -d "$SRC/../examples" ]; then
    cp -r "$SRC/../examples" "$DESTINO/examples"
fi

echo ">> Pronto: $DESTINO"
ls -la "$DESTINO/bin"

# ---- teste de fumaça, se houver wine ---------------------------------------
if command -v wine >/dev/null; then
    echo ">> Teste de fumaça com wine"
    T="$(mktemp -d)"
    cat > "$T/fumaca.in" <<'EOF'
mode two.dim
line x loc=0 spacing=0.2 tag=esq
line x loc=1 spacing=0.2 tag=dir
line y loc=0 spacing=0.05 tag=topo
line y loc=1 spacing=0.2 tag=fundo
region silicon xlo=esq xhi=dir ylo=topo yhi=fundo
boundary exposed xlo=esq xhi=dir ylo=topo yhi=topo
boundary backside xlo=esq xhi=dir ylo=fundo yhi=fundo
initialize boron conc=1e15 orient=100
select z=doping
print.1d x.value=0.5
quit
EOF
    SAIDA="$(cd "$T" && WINEDEBUG=-all \
        SUP4KEYFILE="$(winepath -w "$DESTINO/data/suprem.uk" 2>/dev/null || echo "$DESTINO/data/suprem.uk")" \
        SUP4MODELRC="$(winepath -w "$DESTINO/data/modelrc" 2>/dev/null || echo "$DESTINO/data/modelrc")" \
        SUP4IMPDATA="$(winepath -w "$DESTINO/data/sup4gs.imp" 2>/dev/null || echo "$DESTINO/data/sup4gs.imp")" \
        wine "$DESTINO/bin/suprem.exe" fumaca.in 2>&1 || true)"
    rm -rf "$T"
    if printf '%s' "$SAIDA" | grep -q "coordinate in um"; then
        echo ">> OK: o suprem.exe roda e imprime a tabela."
    else
        echo "!! O teste de fumaça não produziu tabela. Saída:"
        printf '%s\n' "$SAIDA" | tail -20
        exit 1
    fi
else
    echo ">> (wine não instalado; pulei o teste de fumaça)"
fi
