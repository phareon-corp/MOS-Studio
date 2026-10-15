#!/usr/bin/env bash
# ============================================================
#  build_suprem.sh  -  Compila o SUPREM-III (fonte Stanford,
#  Release B rev. 8628) NATIVO no Linux, sem DOSBox.
#  SyncField Corporation
#
#  Pre-requisitos no Fedora:
#      sudo dnf install gcc gcc-gfortran make tar
#
#  Uso:
#      ./build_suprem.sh /caminho/para/relB_8628_tar.Z
#  (ou deixe o .Z/.tar na pasta atual e rode sem argumento)
# ============================================================
set -e

SRC_ARCHIVE="${1:-relB_8628_tar.Z}"
# resolve para caminho absoluto antes de trocar de diretorio
case "$SRC_ARCHIVE" in /*) : ;; *) SRC_ARCHIVE="$(pwd)/$SRC_ARCHIVE" ;; esac
test -f "$SRC_ARCHIVE" || { echo "Arquivo nao encontrado: $SRC_ARCHIVE"; exit 1; }
ROOT="$(pwd)/suprem_build"
echo ">> Build em: $ROOT"
rm -rf "$ROOT"; mkdir -p "$ROOT"; cd "$ROOT"

# ---- 1. extrair o fonte -----------------------------------
echo ">> Extraindo $SRC_ARCHIVE ..."
case "$SRC_ARCHIVE" in
    *.Z)   gzip -dc "$SRC_ARCHIVE" > relB.tar ;;
    *.tar) cp "$SRC_ARCHIVE" relB.tar ;;
    *.gz)  gzip -dc "$SRC_ARCHIVE" > relB.tar ;;
    *) echo "Formato nao reconhecido: $SRC_ARCHIVE"; exit 1 ;;
esac
tar xf relB.tar
test -d Release/src || { echo "Estrutura inesperada (sem Release/src)"; exit 1; }

# ---- 2. wrapper f77 -> gfortran (flags legadas) -----------
mkdir -p bin
cat > bin/f77 <<'EOF'
#!/bin/sh
exec gfortran -std=legacy -fallow-argument-mismatch -fno-automatic -w -fcommon "$@"
EOF
chmod +x bin/f77
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

# ---- 5. compilar genii ------------------------------------
echo ">> Compilando genii ..."
( cd genii && make install >/dev/null )

# ---- 6. compilar setup (com shim de fdate) ----------------
echo ">> Compilando setup ..."
( cd setup
  make install >/dev/null 2>&1 || true
  gcc -O -c fdate_shim.c -o fdate_shim.o
  f77 -O setup.o gencm.o cpack.o clsfl.o opnfl-L.o geten-L.o setvl.o fdate_shim.o -o ../../run/setup )

# ---- 7. compilar sup3 (com stubs de plot) -----------------
echo ">> Compilando sup3 (simulador) ..."
( cd suprem
  make LIBS="-lm" FFLAGS="-O" >/dev/null 2>&1 || true
  gcc -O -c plotstub.c -o plotstub.o
  OBJS=$(ls *.o | grep -v plotstub.o)
  f77 -O $OBJS plotstub.o -lm -o ../../run/sup3 )

# ---- 8. inicializar (gera S3uky0 e S3cof0) ----------------
echo ">> Inicializando coeficientes (S3uky0 / S3cof0) ..."
cd ../run
chmod +x setup genii sup3 2>/dev/null || true
chmod +x setup.exe genii.exe sup3.exe 2>/dev/null || true
sed "s:^SUPRUN=.*:SUPRUN=$(pwd):" suprem.org > suprem
chmod +x suprem 2>/dev/null || true
rm -f S3uky0 S3cof0 S3prs0*
sh ./suprem initl.in /dev/null >/dev/null 2>&1 || ./suprem initl.in /dev/null >/dev/null 2>&1 || true

if [ -f S3cof0 ] && [ -f S3uky0 ]; then
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
