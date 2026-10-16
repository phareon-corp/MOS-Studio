#!/usr/bin/env bash
# ============================================================================
#  montar_linux.sh — monta o pacote de Linux do MOS-Studio.
#  SyncField Corporation
#
#  Gera: dist/mos-studio-<versão>-linux-x86_64.tar.gz
#
#  O QUE VAI DENTRO, E O QUE NÃO VAI
#  ---------------------------------
#  Vai o programa, os dados e o motor 2-D já compilado, mais o instalador
#  que cria o lançador e a entrada de menu no perfil do usuário.
#
#  NÃO vai um Python próprio. Diferente do pacote de Windows, aqui o
#  programa usa o Python e o PySide6 do sistema: toda distribuição de Linux
#  tem os dois a um comando de distância, e embutir uma segunda cópia do Qt
#  (mais de 100 MB) só para repetir o que já está instalado é desperdício.
#  O ``instalar.sh`` confere as duas dependências antes de escrever
#  qualquer coisa e diz o que falta.
#
#  Uso:
#      ./empacotar/montar_linux.sh
# ============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

VERSAO="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -1)"
[ -n "$VERSAO" ] || { echo "!! não achei a versão no pyproject.toml"; exit 1; }

NOME="mos-studio-$VERSAO-linux-x86_64"
DIST="$RAIZ/dist"
ALVO="$DIST/$NOME"

rm -rf "$ALVO" "$DIST/$NOME.tar.gz"
mkdir -p "$ALVO"

echo ">> copiando o programa"
for d in mos_studio data; do
    rsync -a --exclude '__pycache__' --exclude '*.pyc' "$RAIZ/$d" "$ALVO/"
done
install -m 755 "$RAIZ/instalar.sh"    "$ALVO/instalar.sh"
install -m 755 "$RAIZ/desinstalar.sh" "$ALVO/desinstalar.sh"

echo ">> copiando o motor 2-D"
MOTOR="$RAIZ/suprem4-run"
if [ ! -x "$MOTOR/bin/suprem" ]; then
    echo "!! falta o SUPREM-IV — rode antes:  ./build_suprem4.sh"
    exit 1
fi
rsync -a --exclude '__pycache__' "$MOTOR" "$ALVO/"

# O instalador espera achar os motores ao lado do pacote; a pasta de saídas
# é criada aqui para existir já na primeira execução.
mkdir -p "$ALVO/resultados"

cat > "$ALVO/LEIA-ME.txt" <<EOF
MOS-Studio $VERSAO — Linux x86-64
=================================

Instalar (sem root):

    ./instalar.sh

Cria o lançador em ~/.local/bin/mos-studio, a entrada de menu e o ícone.
Depois é só procurar "MOS-Studio" no menu, ou rodar:  mos-studio

Desinstalar:  ./desinstalar.sh
(não toca nas preferências nem nas simulações)

PRECISA TER INSTALADO
---------------------
  Python 3.11 ou mais novo
  PySide6:   pip install --user PySide6

O instalador confere os dois antes de escrever qualquer coisa.

O QUE VEM DENTRO
----------------
  mos_studio/    o programa
  suprem4-run/   o SUPREM-IV.GS, simulador de processo 2-D
  resultados/    cada simulação que você roda fica aqui

ONDE ESTA PASTA FICA IMPORTA
----------------------------
O lançador aponta para esta pasta em vez de copiar o programa: é daqui que
ele lê o motor e o histórico de execuções. Se mover ou renomear a pasta,
rode ./instalar.sh de novo no lugar novo.

OS OUTROS DOIS MOTORES
----------------------
O SUPREM-III (processo 1-D) e o MINIMOS 6.1 (dispositivo) não acompanham
este pacote. Com o código-fonte deles, os scripts build_suprem.sh e
build_minimos.sh do repositório os compilam e basta pôr as pastas
suprem-run/ e minimos-run/ aqui ao lado. Sem eles, as telas de 1-D e de
Dispositivo avisam que o motor não foi encontrado e o resto funciona.

Se algo não abrir:  mos-studio --diagnostico

SyncField Corporation
https://github.com/phareon-corp/MOS-Studio
EOF

echo ">> empacotando"
( cd "$DIST" && tar czf "$NOME.tar.gz" "$NOME" )

TAM="$(du -h "$DIST/$NOME.tar.gz" | cut -f1)"
QUANTOS="$(find "$ALVO" -type f | wc -l)"
echo
echo ">> pronto: $DIST/$NOME.tar.gz  ($TAM, $QUANTOS arquivos)"
