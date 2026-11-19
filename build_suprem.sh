#!/usr/bin/env bash
# ============================================================
#  build_suprem.sh  -  Compila o SUPREM-III (fonte Stanford,
#  Release B rev. 8628) NATIVO no Linux, sem DOSBox.
#  SyncField Corporation
#
#  Pre-requisitos (o ./instalar.sh instala sozinho):
#      gcc gfortran make tar gzip python3
#
#  Uso:
#      ./build_suprem.sh                      # usa fontes/suprem3-relB.8628.tar.Z
#      ./build_suprem.sh /caminho/relB.tar.Z  # outro arquivo do fonte
#  Gera: suprem-run/ (ao lado deste script), que o MOS-Studio acha sozinho.
#
#  Windows, por compilacao cruzada no Linux (para o pacote .exe):
#      ./build_suprem.sh                          # antes: gera os coeficientes
#      CROSS=x86_64-w64-mingw32 ./build_suprem.sh # gera suprem-run-win/
#  Precisa do mingw64-gcc-gfortran. Os .exe saem ligados estaticamente (nao
#  pedem DLL do gfortran). Os coeficientes S3cof0/S3uky0 sao gerados RODANDO
#  o motor, o que nao da para fazer com um .exe no Linux; sao copiados do
#  suprem-run/ nativo -- o formato sem formatacao do gfortran e' o mesmo nos
#  dois sistemas (conferido na VM de testes).
#
#  O fonte e' de Stanford, com licenca que permite copiar e distribuir
#  (exceto venda); ver fontes/LEIA-ME.md.
# ============================================================
set -e

AQUI="$(cd "$(dirname "$0")" && pwd)"
CROSS="${CROSS:-}"
if [ -n "$CROSS" ]; then
    FC="$CROSS-gfortran"; CC="$CROSS-gcc"; LDEXTRA="-static"; DESTNOME="suprem-run-win"
    test -f "$AQUI/suprem-run/S3cof0" && test -f "$AQUI/suprem-run/S3uky0" \
        || { echo "!! compile antes o SUPREM-III nativo (./build_suprem.sh): os coeficientes saem dele"; exit 1; }
else
    FC="gfortran"; CC="gcc"; LDEXTRA=""; DESTNOME="suprem-run"
fi
for f in "$CC" "$FC" make tar gzip python3; do
    command -v "$f" >/dev/null || { echo "!! falta '$f' (rode ./instalar.sh, que instala as dependencias)"; exit 1; }
done
if [ $# -ge 1 ]; then
    SRC_ARCHIVE="$1"
else
    SRC_ARCHIVE="$AQUI/fontes/suprem3-relB.8628.tar.Z"
    ( cd "$AQUI/fontes" && sha256sum -c --ignore-missing --quiet SHA256SUMS ) \
        || { echo "!! fontes/suprem3-relB.8628.tar.Z nao confere com SHA256SUMS"; exit 1; }
fi
# resolve para caminho absoluto antes de trocar de diretorio
case "$SRC_ARCHIVE" in /*) : ;; *) SRC_ARCHIVE="$(pwd)/$SRC_ARCHIVE" ;; esac
test -f "$SRC_ARCHIVE" || { echo "Arquivo nao encontrado: $SRC_ARCHIVE"; exit 1; }
ROOT="$AQUI/suprem_build"
echo ">> Build em: $ROOT"
rm -rf "${ROOT:?}"; mkdir -p "$ROOT"; cd "$ROOT"

# ---- 1. extrair o fonte -----------------------------------
echo ">> Extraindo $SRC_ARCHIVE ..."
case "$SRC_ARCHIVE" in
    *.Z)   gzip -dc "$SRC_ARCHIVE" > relB.tar ;;
    *.tar) cp "$SRC_ARCHIVE" relB.tar ;;
    *.gz)  gzip -dc "$SRC_ARCHIVE" > relB.tar ;;
    *) echo "Formato nao reconhecido: $SRC_ARCHIVE"; exit 1 ;;
esac
tar xf relB.tar --no-same-owner
chmod -R u+rwX Release
test -d Release/src || { echo "Estrutura inesperada (sem Release/src)"; exit 1; }

# ---- 2. wrapper f77 -> gfortran (flags legadas) -----------
mkdir -p bin
cat > bin/f77 <<EOF
#!/bin/sh
exec $FC -std=legacy -fallow-argument-mismatch -fno-automatic -w -fcommon $LDEXTRA "\$@"
EOF
chmod +x bin/f77
if [ -n "$CROSS" ]; then
    # Os Makefiles chamam 'strip ../../run/genii'; no mingw o arquivo e' genii.exe.
    cat > bin/strip <<EOF
#!/bin/sh
f="\$1"; [ -f "\$f" ] || f="\$f.exe"
exec $CROSS-strip "\$f"
EOF
    chmod +x bin/strip
    # ... e 'chmod 755 ../../run/genii', pelo mesmo motivo.
    cat > bin/chmod <<EOF
#!/bin/sh
m="\$1"; shift
for f in "\$@"; do [ -e "\$f" ] || f="\$f.exe"; command -p chmod "\$m" "\$f"; done
EOF
    command -p chmod +x bin/chmod
fi
export PATH="$ROOT/bin:$PATH"

cd Release/src

# ---- 3. correcoes no fonte (gfortran moderno) -------------
echo ">> Aplicando correcoes de portabilidade ao fonte ..."
python3 - <<'PY'
import glob, re

# (a) continuacao '&' na coluna 1  ->  '&' na coluna 6 (forma fixa)
n=0
for f in glob.glob('*/*.f'):
    L=open(f,encoding='latin1').readlines(); ch=False
    for i,l in enumerate(L):
        if l.startswith('&') and (len(l)<6 or l[5]==' '):
            L[i]=' '+l[1:5]+'&'+l[6:]; ch=True; n+=1
    if ch: open(f,'w',encoding='latin1').writelines(L)
print(f'   continuacoes convertidas: {n}')

# (b) 'implicit undefined(a-z)'  ->  'implicit none'
m=0
for f in glob.glob('*/*.f'):
    s=open(f,encoding='latin1').read()
    s2=re.sub(r'(?i)implicit\s+undefined\s*\([a-z]\-[a-z]\)','implicit none',s)
    if s2!=s: open(f,'w',encoding='latin1').write(s2); m+=1
print(f'   implicit undefined ajustados em {m} arquivos')

# (c) opnfl-L.f: STATUS=SCRATCH nao aceita FILE= no gfortran
old="      open(lu,file=fname,err=11,iostat=ierr,status=astat,form=aform)"
new=("      if (astat .eq. scrat) then\n"
     "         open(lu,err=11,iostat=ierr,status='scratch',form=aform)\n"
     "      else\n"
     "         open(lu,file=fname,err=11,iostat=ierr,status=astat,form=aform)\n"
     "      endif")
k=0
for f in glob.glob('*/opnfl-L.f'):
    s=open(f).read()
    if old in s: open(f,'w').write(s.replace(old,new)); k+=1
print(f'   opnfl-L.f (scratch) corrigidos: {k}')
PY

# ---- 4. shims em C ----------------------------------------
# fdate() (intrinseca BSD usada pelo setup)
cat > setup/fdate_shim.c <<'EOF'
#include <time.h>
#include <string.h>
void fdate_(char *out, long len){
    time_t t=time(0); char *s=ctime(&t); long n=(long)strlen(s);
    if(n>0&&s[n-1]=='\n')n--;
    for(long i=0;i<len;i++) out[i]=(i<n)?s[i]:' ';
}
EOF

# stubs no-op da biblioteca Plotcap (so usada pelo comando PLOT)
cat > suprem/plotstub.c <<'EOF'
int faxpt2_(void){return 0;} int faxtc2_(void){return 0;}
int fclear_(void){return 0;} int fcliph_(void){return 0;}
int fclipl_(void){return 0;} int fgtoa_(void){return 0;}
int fnline_(void){return 0;} int fnpen_(void){return 0;}
int fpend_(void){return 0;}  int fpgeti_(void){return 0;}
int fplot_(void){return 0;}  int fscale_(void){return 0;}
int fsym2_(void){return 0;}  int ftrans_(void){return 0;}
int stpdev_(void){return 0;} int stpfil_(void){return 0;}
EOF

mkdir -p ../run

# Os .c do fonte sao K&R: 'char *getenv();' sem prototipo. O GCC 15 (Fedora
# 42+) compila em C23 por padrao, onde isso quer dizer "zero argumentos", e
# a chamada getenv(nome) vira erro. gnu89 e' o dialeto em que foram escritos.
CFLAGS_C="-O -std=gnu89 -w"

# ---- 5. compilar genii ------------------------------------
echo ">> Compilando genii ..."
( cd genii && make install CC="$CC" CFLAGS="$CFLAGS_C" >/dev/null )

# ---- 6. compilar setup (com shim de fdate) ----------------
echo ">> Compilando setup ..."
( cd setup
  make install CC="$CC" CFLAGS="$CFLAGS_C" >/dev/null 2>&1 || true
  $CC -O -c fdate_shim.c -o fdate_shim.o
  f77 -O setup.o gencm.o cpack.o clsfl.o opnfl-L.o geten-L.o setvl.o fdate_shim.o -o ../../run/setup )

# ---- 7. compilar sup3 (com stubs de plot) -----------------
echo ">> Compilando sup3 (simulador) ..."
( cd suprem
  make CC="$CC" CFLAGS="$CFLAGS_C" LIBS="-lm" FFLAGS="-O" >/dev/null 2>&1 || true
  $CC -O -c plotstub.c -o plotstub.o
  OBJS=$(ls *.o | grep -v plotstub.o)
  f77 -O $OBJS plotstub.o -lm -o ../../run/sup3 )

# ---- 8. inicializar (gera S3uky0 e S3cof0) ----------------
cd ../run
if [ -n "$CROSS" ]; then
    for b in setup genii sup3; do
        test -f "$b.exe" || { echo "!! nao gerou $b.exe"; exit 1; }
    done
    cp "$AQUI/suprem-run/S3cof0" "$AQUI/suprem-run/S3uky0" .
    rm -f suprem.org Makefile
    rm -rf "${AQUI:?}/${DESTNOME:?}"
    cp -a "$(pwd)" "$AQUI/$DESTNOME"
    echo ">> SUCESSO. SUPREM-III para Windows em: $AQUI/$DESTNOME"
    exit 0
fi
echo ">> Inicializando coeficientes (S3uky0 / S3cof0) ..."
chmod +x setup genii sup3 2>/dev/null || true
chmod +x setup.exe genii.exe sup3.exe 2>/dev/null || true
sed "s:^SUPRUN=.*:SUPRUN=$(pwd):" suprem.org > suprem
chmod +x suprem 2>/dev/null || true
rm -f S3uky0 S3cof0 S3prs0*
sh ./suprem initl.in /dev/null >/dev/null 2>&1 || ./suprem initl.in /dev/null >/dev/null 2>&1 || true

if [ -f S3cof0 ] && [ -f S3uky0 ]; then
    rm -rf "${AQUI:?}/suprem-run"
    cp -a "$(pwd)" "$AQUI/suprem-run"
    cd "$AQUI/suprem-run"
    sed "s:^SUPRUN=.*:SUPRUN=$(pwd):" suprem.org > suprem
    chmod +x suprem
    echo ""
    echo "==================================================="
    echo " SUCESSO. SUPREM-III nativo pronto em:"
    echo "   $(pwd)"
    echo " Para rodar:"
    echo "   ./suprem entrada.in saida.out"
    echo "==================================================="
else
    echo "!! Inicializacao incompleta - verifique mensagens acima."
    exit 1
fi
