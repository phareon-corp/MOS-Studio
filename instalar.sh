#!/usr/bin/env bash
# ============================================================================
#  instalar.sh — instala o MOS-Studio no Linux, do zero, com um comando.
#
#      git clone https://github.com/phareon-corp/MOS-Studio.git
#      cd MOS-Studio
#      ./instalar.sh
#
#  O que faz, em ordem:
#   1. instala o que falta no sistema (compiladores C e Fortran, make, as
#      bibliotecas de que o Qt precisa para abrir a janela) pelo gerenciador
#      de pacotes da distribuição — dnf, apt, pacman ou zypper. Só esta etapa
#      pede a senha (sudo), e só se faltar alguma coisa;
#   2. cria um ambiente Python próprio do programa e instala o PySide6 nele.
#      Não usa "pip install --user": no Ubuntu/Debian recentes isso é
#      recusado (PEP 668), e misturar com o Python do sistema quebra fácil;
#   3. compila os motores a partir do fonte que vem em fontes/:
#        SUPREM-IV.GS (2-D) e SUPREM-III (1-D), de Stanford;
#        MINIMOS 6.1, se houver o minimoswin6.1.zip (ver --minimos);
#   4. cria o lançador "mos-studio", a entrada de menu e o ícone;
#   5. roda o diagnóstico do programa e mostra o que ficou pronto.
#
#  Rodar de novo é seguro: o que já está pronto é pulado.
#
#  Opções:
#      --minimos ZIP   instala o MINIMOS a partir do minimoswin6.1.zip da TU
#                      Wien (sem isto, o zip é procurado em ~/Downloads)
#      --recompilar    compila os motores de novo mesmo se já estiverem prontos
#      --sem-sistema   não chama o gerenciador de pacotes (sem sudo)
#      -h, --help      esta ajuda
#
#  O lançador aponta para ESTE diretório em vez de copiar o programa: os
#  motores e o histórico de execuções (resultados/) vivem aqui. Mover a
#  pasta exige rodar ./instalar.sh de novo.
# ============================================================================
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")" && pwd)"
APPID="io.syncfield.MosStudio"
BIN="$HOME/.local/bin"
DESK="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor/scalable/apps"
DADOS="${XDG_DATA_HOME:-$HOME/.local/share}/mos-studio"
VENV="$DADOS/venv"
LOGS="$DADOS/logs"
PYSIDE_VERSAO="6.11.1"

MINIMOS_ZIP=""
RECOMPILAR=0
SEM_SISTEMA=0
while [ $# -gt 0 ]; do
  case "$1" in
    --minimos)     MINIMOS_ZIP="${2:?--minimos precisa do caminho do zip}"; shift 2 ;;
    --minimos=*)   MINIMOS_ZIP="${1#*=}"; shift ;;
    --recompilar)  RECOMPILAR=1; shift ;;
    --sem-sistema) SEM_SISTEMA=1; shift ;;
    -h|--help)     sed -n '2,/^# =====/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "opção desconhecida: $1 (veja --help)"; exit 2 ;;
  esac
done
if [ -n "$MINIMOS_ZIP" ]; then
  MINIMOS_ZIP="$(cd "$(dirname "$MINIMOS_ZIP")" && pwd)/$(basename "$MINIMOS_ZIP")"
fi

etapa() { printf '\n\033[1m>> %s\033[0m\n' "$*"; }
info()  { printf '   %s\n' "$*"; }
aviso() { printf '   \033[33mATENÇÃO:\033[0m %s\n' "$*"; }
falha() { printf '\n\033[31m!! %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Linux" ] || falha "este instalador é para Linux (no Windows, use o instalador .exe das Releases)"
mkdir -p "$DADOS" "$LOGS"

# ── 1. pacotes do sistema ──────────────────────────────────────────────────
# Cada distribuição dá nomes diferentes às mesmas coisas. As listas trazem
# o necessário para compilar os motores (C e Fortran) e as bibliotecas que o
# Qt 6 carrega para abrir a janela no X11/XWayland — a que mais falta em
# instalação nova é a xcb-cursor, e sem ela a janela simplesmente não abre.

falta_algo() {
  local c
  for c in gcc gfortran make patch tar gzip unzip python3; do
    command -v "$c" >/dev/null 2>&1 || { info "falta: $c"; return 0; }
  done
  python3 -c 'import ensurepip, venv' 2>/dev/null || { info "falta: módulo venv do Python"; return 0; }
  local lib
  for lib in libxcb-cursor.so.0 libxkbcommon-x11.so.0 libxcb-icccm.so.4 \
             libxcb-keysyms.so.1 libxcb-image.so.0 libxcb-render-util.so.0 \
             libEGL.so.1 libGL.so.1 libfontconfig.so.1 libdbus-1.so.3 \
             libglib-2.0.so.0; do
    ldconfig -p 2>/dev/null | grep -q "$lib" || { info "falta: $lib"; return 0; }
  done
  return 1
}

# apt: alguns nomes mudaram (ex.: libglib2.0-0 → libglib2.0-0t64 no Ubuntu
# 24.04). "a|b" instala o primeiro que existir no repositório.
apt_escolher() {
  local grupo alt
  for grupo in "$@"; do
    for alt in ${grupo//|/ }; do
      if apt-cache show --no-all-versions "$alt" >/dev/null 2>&1; then
        echo "$alt"; break
      fi
    done
  done
}

instalar_sistema() {
  local SUDO=""
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null 2>&1 || falha "faltam pacotes do sistema e não há sudo. Instale como root e rode de novo com --sem-sistema."
    SUDO="sudo"
    info "a instalação de pacotes do sistema vai pedir sua senha (sudo)"
  fi
  if command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y gcc gcc-gfortran make patch tar gzip unzip curl \
      python3 xcb-util-cursor xcb-util-wm xcb-util-image xcb-util-keysyms \
      xcb-util-renderutil libxkbcommon-x11 mesa-libEGL mesa-libGL \
      libglvnd-opengl fontconfig dbus-libs glib2
  elif command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    $SUDO apt-get update -q
    # shellcheck disable=SC2046
    $SUDO apt-get install -y -q $(apt_escolher gcc gfortran make patch tar gzip \
      unzip curl ca-certificates python3 python3-venv libxcb-cursor0 \
      libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 \
      libx11-xcb1 libegl1 "libgl1|libgl1-mesa-glx" libopengl0 libfontconfig1 \
      "libdbus-1-3" "libglib2.0-0t64|libglib2.0-0")
  elif command -v pacman >/dev/null 2>&1; then
    $SUDO pacman -S --needed --noconfirm gcc gcc-fortran make patch tar gzip \
      unzip curl python xcb-util-cursor xcb-util-wm xcb-util-image \
      xcb-util-keysyms xcb-util-renderutil libxkbcommon-x11 libglvnd \
      fontconfig dbus glib2
  elif command -v zypper >/dev/null 2>&1; then
    $SUDO zypper --non-interactive install gcc gcc-fortran make patch tar gzip \
      unzip curl python3 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
      libxcb-keysyms1 libxcb-render-util0 libxkbcommon-x11-0 libEGL1 libGL1 \
      libOpenGL0 fontconfig libdbus-1-3 libglib-2_0-0
  else
    falha "não reconheci o gerenciador de pacotes. Instale à mão: gcc, gfortran, make, patch, tar, gzip, unzip, python3 (com venv) e as bibliotecas xcb do Qt 6; depois rode com --sem-sistema."
  fi
}

etapa "1/5  dependências do sistema"
if falta_algo; then
  if [ "$SEM_SISTEMA" -eq 1 ]; then
    aviso "faltam pacotes, mas --sem-sistema foi pedido; seguindo assim mesmo"
  else
    instalar_sistema
  fi
else
  info "tudo presente"
fi

# ── 2. Python e PySide6 ────────────────────────────────────────────────────
etapa "2/5  Python e PySide6 (em $VENV)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || falha "python3 não encontrado"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' \
  || falha "é preciso Python 3.10 ou mais novo (há $("$PY" -V 2>&1))"

if ! "$VENV/bin/python" -c 'import PySide6' >/dev/null 2>&1; then
  rm -rf "$VENV"
  "$PY" -m venv "$VENV" || falha "não consegui criar o ambiente Python (falta o pacote python3-venv?)"
  "$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
  info "baixando o PySide6 $PYSIDE_VERSAO (uns 100 MB, só na primeira vez)"
  "$VENV/bin/python" -m pip install -q --disable-pip-version-check \
      "PySide6-Essentials==$PYSIDE_VERSAO" \
    || "$VENV/bin/python" -m pip install -q --disable-pip-version-check \
      "PySide6-Essentials>=6.5" \
    || falha "o pip não conseguiu instalar o PySide6 (sem internet?)"
fi
info "$("$VENV/bin/python" -c 'import sys, PySide6; print(f"Python {sys.version.split()[0]}, PySide6 {PySide6.__version__}")')"

# O plugin do Qt que abre a janela no X11/XWayland: se alguma biblioteca
# dele faltar, o programa morre ao abrir sem dizer nada útil.
XCB="$("$VENV/bin/python" -c 'import PySide6, pathlib; p = pathlib.Path(PySide6.__file__).parent / "Qt/plugins/platforms/libqxcb.so"; print(p if p.exists() else "")')"
if [ -n "$XCB" ]; then
  FALTAM="$(LD_LIBRARY_PATH="$(dirname "$(dirname "$(dirname "$XCB")")")/lib" ldd "$XCB" 2>/dev/null | awk '/not found/{print $1}' | tr '\n' ' ')"
  if [ -n "$FALTAM" ]; then
    aviso "o Qt não vai conseguir abrir a janela; faltam: $FALTAM"
  else
    info "bibliotecas da janela (xcb): ok"
  fi
fi

MOS_PY=("$VENV/bin/python")
export PYTHONPATH="$RAIZ${PYTHONPATH:+:$PYTHONPATH}"

# ── 3. motores ─────────────────────────────────────────────────────────────
etapa "3/5  motores de simulação"

motor_ok() {   # $1 = suprem | suprem4 | minimos
  "${MOS_PY[@]}" - "$1" <<'EOF' >/dev/null 2>&1
import sys
from mos_studio.core import minimos, suprem, suprem4
qual = sys.argv[1]
if qual == "suprem":
    d = suprem.find_run_dir(); ok = d is not None and not suprem.check_engine(d)
elif qual == "suprem4":
    d = suprem4.find_run_dir(); ok = d is not None and not suprem4.check_engine(d)
else:
    d = minimos.find_dir(); ok = d is not None and not minimos.check_engine(d)
sys.exit(0 if ok else 1)
EOF
}

ERROS=()
compilar() {   # $1 = rótulo, $2 = chave de motor_ok, $3.. = comando
  local rotulo="$1" chave="$2"; shift 2
  local log="$LOGS/$chave.log"
  if [ "$RECOMPILAR" -eq 0 ] && motor_ok "$chave"; then
    info "$rotulo: já pronto"
    return 0
  fi
  info "$rotulo: compilando… (registro em $log)"
  if ( cd "$RAIZ" && "$@" ) >"$log" 2>&1 && motor_ok "$chave"; then
    info "$rotulo: ok"
  else
    aviso "$rotulo: a compilação falhou. Últimas linhas do registro:"
    tail -n 15 "$log" | sed 's/^/      /'
    ERROS+=("$rotulo")
  fi
}

compilar "SUPREM-IV.GS (2-D)" suprem4 bash "$RAIZ/build_suprem4.sh"
compilar "SUPREM-III  (1-D)"  suprem  bash "$RAIZ/build_suprem.sh"
rm -rf "$RAIZ/suprem_build"

if [ -z "$MINIMOS_ZIP" ] && ! motor_ok minimos; then
  MINIMOS_ZIP="$("${MOS_PY[@]}" -c 'from mos_studio.core import importar_minimos as m; z = m.procurar_zip(); print(z or "")' 2>/dev/null || true)"
  [ -n "$MINIMOS_ZIP" ] && info "MINIMOS: achei $MINIMOS_ZIP"
fi
if [ -n "$MINIMOS_ZIP" ]; then
  [ "$RECOMPILAR" -eq 1 ] || ! motor_ok minimos || MINIMOS_ZIP=""
fi
if [ -n "$MINIMOS_ZIP" ]; then
  compilar "MINIMOS 6.1 (dispositivo)" minimos \
    "${MOS_PY[@]}" -m mos_studio --instalar-minimos "$MINIMOS_ZIP"
elif motor_ok minimos; then
  info "MINIMOS 6.1 (dispositivo): já pronto"
else
  info "MINIMOS 6.1 (dispositivo): não instalado — ele não pode vir junto"
  info "   (licença da TU Wien). Com o minimoswin6.1.zip em mãos, rode:"
  info "      ./instalar.sh --minimos /caminho/minimoswin6.1.zip"
  info "   ou use o botão \"Instalar MINIMOS\" na tela de Dispositivo."
  info "   Registro gratuito: https://www.iue.tuwien.ac.at/software/download/download-area"
fi

# ── 4. lançador, menu e ícone ──────────────────────────────────────────────
etapa "4/5  lançador, menu e ícone"
mkdir -p "$BIN" "$DESK" "$ICONES"
cat > "$BIN/mos-studio" <<EOF
#!/usr/bin/env bash
# Gerado por instalar.sh do MOS-Studio. Não edite à mão.
export PYTHONPATH="$RAIZ\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$VENV/bin/python" -m mos_studio "\$@"
EOF
chmod +x "$BIN/mos-studio"
info "lançador: $BIN/mos-studio"

# A ação "Diagnóstico da instalação" aparece no menu de contexto do ícone:
# se o programa não abrir, é por ali que se descobre o motivo.
cat > "$DESK/$APPID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MOS-Studio
GenericName=Simulador de Semicondutores
Comment=Simulação de processos e dispositivos semicondutores (SUPREM-III, SUPREM-IV.GS, MINIMOS)
Exec=$BIN/mos-studio
Icon=$APPID
Terminal=false
Categories=Science;Engineering;
Keywords=SUPREM;MINIMOS;MOS;semicondutor;oxidacao;dopagem;difusao;implantacao;
StartupNotify=true
StartupWMClass=MOS-Studio
Actions=diagnostico;

[Desktop Action diagnostico]
Name=Diagnóstico da instalação
Exec=$BIN/mos-studio --diagnostico
EOF
cp "$RAIZ/data/$APPID.svg" "$ICONES/$APPID.svg"
info "menu: $DESK/$APPID.desktop"
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$DESK" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && \
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

# ── 5. conferência ─────────────────────────────────────────────────────────
etapa "5/5  conferência"
# O diagnóstico monta a janela inteira (sem mostrá-la) e confere os motores:
# é a prova de que o programa abre, não só de que os arquivos estão lá.
if MOS_DIAGNOSTICO_SILENCIOSO=1 QT_QPA_PLATFORM=offscreen timeout 300 \
     "$BIN/mos-studio" --diagnostico >"$LOGS/diagnostico.log" 2>&1; then
  info "a interface monta sem erro"
else
  aviso "o diagnóstico acusou problema — veja $LOGS/diagnostico.log"
  ERROS+=("interface")
fi
for par in "suprem4:SUPREM-IV.GS (2-D)" "suprem:SUPREM-III  (1-D)" "minimos:MINIMOS 6.1"; do
  if motor_ok "${par%%:*}"; then info "${par#*:}  pronto"; else info "${par#*:}  —"; fi
done

case ":$PATH:" in
  *":$BIN:"*) ;;
  *) aviso "$BIN não está no PATH; use o menu, ou acrescente-o ao PATH para o comando 'mos-studio'." ;;
esac

echo
if [ ${#ERROS[@]} -gt 0 ]; then
  printf '\033[31m!! terminou com problemas em: %s\033[0m\n' "${ERROS[*]}"
  echo "   Os registros estão em $LOGS"
  exit 1
fi
printf '\033[32m>> pronto.\033[0m Procure "MOS-Studio" no menu, ou rode:  mos-studio\n'
