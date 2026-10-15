#!/usr/bin/env bash
# Instala o MOS-Studio no perfil do usuário (sem root).
#
# O lançador aponta para ESTE diretório em vez de copiar o programa. É de
# propósito: os motores nativos (suprem-run/, minimos-run/) e o histórico de
# execuções (resultados/) vivem aqui, e `legacy_results_dir()` os procura ao
# lado do pacote. Copiar o código criaria uma segunda cópia que envelhece a
# cada commit, e o programa instalado deixaria de ver as execuções antigas.
#
# Instala:
#   ~/.local/bin/mos-studio                              lançador
#   ~/.local/share/applications/<APPID>.desktop          entrada de menu
#   ~/.local/share/icons/hicolor/scalable/apps/<APPID>.svg
set -euo pipefail

RAIZ="$(cd "$(dirname "$0")" && pwd)"
APPID="io.syncfield.MosStudio"
BIN="$HOME/.local/bin"
DESK="$HOME/.local/share/applications"
ICONES="$HOME/.local/share/icons/hicolor/scalable/apps"
PY="${PYTHON:-python3}"

echo ">> verificando as dependências"
"$PY" - <<'EOF'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11 ou mais novo é necessário (há {sys.version.split()[0]})")
try:
    import PySide6
except ImportError:
    sys.exit("PySide6 não está instalado — rode:  pip install --user PySide6")
print(f"   Python {sys.version.split()[0]}, PySide6 {PySide6.__version__}")
EOF

echo ">> verificando os motores nativos"
"$PY" - <<EOF
import sys
sys.path.insert(0, "$RAIZ")
from mos_studio.core import minimos, suprem
sup = suprem.find_run_dir()
problemas = suprem.check_engine(sup)
print("   SUPREM-III:", "ok" if sup and not problemas else f"ATENÇÃO — {problemas or 'pasta não encontrada'}")
mm = minimos.find_dir()
problema = minimos.check_engine(mm) if mm else "pasta não encontrada"
print("   MINIMOS   :", "ok" if mm and not problema else f"ATENÇÃO — {problema}")
EOF

mkdir -p "$BIN" "$DESK" "$ICONES"

echo ">> lançador em $BIN/mos-studio"
cat > "$BIN/mos-studio" <<EOF
#!/usr/bin/env bash
# Gerado por instalar.sh do MOS-Studio. Não edite à mão.
export PYTHONPATH="$RAIZ\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY" -m mos_studio "\$@"
EOF
chmod +x "$BIN/mos-studio"

# A ação "Diagnóstico da instalação" aparece no menu de contexto do ícone.
# É a mesma coisa que o atalho equivalente no menu Iniciar do Windows: se o
# programa não abrir, é por ali que se descobre o motivo sem usar o
# terminal. Ver mos_studio/diagnostico.py.
echo ">> entrada de menu em $DESK/$APPID.desktop"
cat > "$DESK/$APPID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MOS-Studio
GenericName=Simulador de Semicondutores
Comment=Simulação de processos e dispositivos semicondutores (SUPREM-III, SUPREM-IV.GS, MINIMOS)
Exec=mos-studio
Icon=$APPID
Terminal=false
Categories=Science;Engineering;
Keywords=SUPREM;MINIMOS;MOS;semicondutor;oxidacao;dopagem;difusao;implantacao;
StartupNotify=true
StartupWMClass=MOS-Studio
Actions=diagnostico;

[Desktop Action diagnostico]
Name=Diagnóstico da instalação
Exec=mos-studio --diagnostico
EOF

echo ">> ícone em $ICONES/$APPID.svg"
cp "$RAIZ/data/$APPID.svg" "$ICONES/$APPID.svg"

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$DESK" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && \
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "   AVISO: $HOME/.local/bin não está no PATH; o comando 'mos-studio'"
     echo "          só funcionará depois de acrescentá-lo." ;;
esac

echo
echo ">> pronto. Procure 'MOS-Studio' no menu, ou rode:  mos-studio"
echo "   programa em: $RAIZ"
echo "   preferências em: $("$PY" -c "import sys; sys.path.insert(0,'$RAIZ'); from mos_studio import paths; print(paths.config_dir())")"
