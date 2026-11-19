#!/usr/bin/env bash
# ============================================================================
#  montar_linux.sh — monta o pacote de Linux do MOS-Studio para as Releases.
#  SyncField Corporation
#
#  Gera: dist/mos-studio-<versão>-linux.tar.gz
#
#  O QUE VAI DENTRO
#  ----------------
#  O mesmo que um "git clone": o programa, o fonte dos motores de Stanford
#  (fontes/), os scripts que os compilam e o instalar.sh. Nada compilado.
#
#  Por que não levar os motores prontos, como no Windows: um binário de
#  Fortran compilado numa distribuição depende da libgfortran e da glibc
#  dela, e quebra na do vizinho. Compilar na máquina de quem instala leva
#  dois minutos e funciona em qualquer uma — e o instalar.sh já instala os
#  compiladores. O Python e o PySide6 também ficam por conta dele (num
#  ambiente próprio, em ~/.local/share/mos-studio/venv).
#
#  Uso:
#      ./empacotar/montar_linux.sh
# ============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

VERSAO="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -1)"
[ -n "$VERSAO" ] || { echo "!! não achei a versão no pyproject.toml"; exit 1; }

NOME="mos-studio-$VERSAO-linux"
DIST="$RAIZ/dist"
mkdir -p "$DIST"
rm -f "$DIST/$NOME.tar.gz"

# Os arquivos versionados (e os novos ainda não commitados), sem o que o
# .gitignore exclui: motores compilados, resultados, caches. O pacote de
# Windows (empacotar/) não serve a quem baixa o de Linux, mas pesa pouco e
# deixa o pacote idêntico ao repositório.
echo ">> empacotando $NOME"
git ls-files -co --exclude-standard -z \
  | tar --null -czf "$DIST/$NOME.tar.gz" --transform "s,^,$NOME/," -T -

TAM="$(du -h "$DIST/$NOME.tar.gz" | cut -f1)"
QUANTOS="$(tar tzf "$DIST/$NOME.tar.gz" | grep -vc '/$')"
echo ">> pronto: $DIST/$NOME.tar.gz  ($TAM, $QUANTOS arquivos)"
echo "   quem baixa: tar xzf $NOME.tar.gz && cd $NOME && ./instalar.sh"
