#!/usr/bin/env python3
"""Converte o ícone SVG do MOS-Studio num ``.ico`` para o Windows.

O SVG em ``data/`` é a fonte única do ícone nos dois sistemas. O Windows
não lê SVG em atalhos nem em recursos de executável, então aqui ele é
rasterizado nos seis tamanhos que o shell do Windows usa (16 a 256 px) e
embrulhado num ``.ico`` de múltiplas resoluções.

A rasterização usa o QtSvg do próprio PySide6, e não o ImageMagick: o
ImageMagick sem o delegado da librsvg cai no renderizador interno dele, que
ignora gradientes e desenha o ícone errado. O Qt é o mesmo motor que pinta
o ícone no Linux, de modo que as duas plataformas mostram a mesma arte.

Uso:
    ./icone_windows.py data/io.syncfield.MosStudio.svg saida.ico
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

#: Tamanhos que o shell do Windows pede: lista de arquivos, barra de
#: tarefas, ícones grandes e a visualização em 256 px do Explorer.
TAMANHOS = (16, 24, 32, 48, 64, 128, 256)

#: Mantém o QGuiApplication vivo até o processo terminar (ver em :func:`main`).
_app = None


def rasterizar(svg: Path, lado: int) -> bytes:
    """Devolve o SVG desenhado em PNG, com fundo transparente."""
    from PySide6.QtCore import QBuffer, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    renderizador = QSvgRenderer(str(svg))
    if not renderizador.isValid():
        raise SystemExit(f"SVG inválido: {svg}")

    imagem = QImage(lado, lado, QImage.Format.Format_ARGB32_Premultiplied)
    imagem.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(imagem)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderizador.render(pintor)
    pintor.end()

    # QBuffer sem argumento usa o buffer interno dele. Passar um QByteArray
    # recém-criado seria pior: o temporário morre na saída desta linha e o
    # buffer fica apontando para memória liberada — derruba o processo.
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    imagem.save(buffer, "PNG")
    return bytes(buffer.data())


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    svg, ico = Path(sys.argv[1]), Path(sys.argv[2])

    # O Qt precisa de uma aplicação viva para desenhar, mesmo sem tela.
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    # A referência fica num global de propósito: deixar o QGuiApplication ser
    # coletado enquanto ainda há QImage vivo derruba o processo.
    global _app
    _app = QGuiApplication.instance() or QGuiApplication([])

    from PIL import Image
    quadros = [Image.open(io.BytesIO(rasterizar(svg, n))) for n in TAMANHOS]
    ico.parent.mkdir(parents=True, exist_ok=True)
    # O Pillow guarda os demais tamanhos como quadros do mesmo .ico.
    quadros[-1].save(ico, format="ICO",
                     sizes=[(n, n) for n in TAMANHOS])
    print(f"{ico}  ({ico.stat().st_size} bytes, "
          f"{len(TAMANHOS)} resoluções)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
