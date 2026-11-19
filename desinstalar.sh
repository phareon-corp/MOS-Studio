#!/usr/bin/env bash
# Remove o MOS-Studio do perfil do usuário.
#
# Tira o lançador, a entrada de menu, o ícone e o ambiente Python que o
# instalador criou. NÃO toca no programa
# (este diretório), nas preferências do usuário, nem nas simulações: quem
# desinstala não espera perder o histórico. As duas pastas que ficam são
# apontadas no fim, para quem quiser apagá-las à mão.
set -euo pipefail

APPID="io.syncfield.MosStudio"
ALVOS=(
  "$HOME/.local/bin/mos-studio"
  "$HOME/.local/share/applications/$APPID.desktop"
  "$HOME/.local/share/icons/hicolor/scalable/apps/$APPID.svg"
)

# O ambiente Python do programa (PySide6) e os registros de instalação:
# são do instalador, não do usuário, e se refazem com ./instalar.sh.
DADOS="${XDG_DATA_HOME:-$HOME/.local/share}/mos-studio"
for pasta in "$DADOS/venv" "$DADOS/logs"; do
  if [ -d "$pasta" ]; then
    rm -rf "$pasta"
    echo ">> removido $pasta"
  fi
done
rmdir "$DADOS" 2>/dev/null || true

for alvo in "${ALVOS[@]}"; do
  if [ -e "$alvo" ]; then
    rm -f "$alvo"
    echo ">> removido $alvo"
  else
    echo ">> não havia $alvo"
  fi
done

command -v gtk-update-icon-cache >/dev/null 2>&1 && \
  gtk-update-icon-cache -f "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && \
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true

echo
echo ">> o que NÃO foi removido, de propósito:"
echo "   o programa:      $(cd "$(dirname "$0")" && pwd)"
echo "   as preferências: ${XDG_CONFIG_HOME:-$HOME/.config}/mos-studio"
echo "   as simulações:   a pasta de trabalho escolhida na tela de Início"
