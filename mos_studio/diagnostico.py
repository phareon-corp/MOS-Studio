"""Relatório do estado da instalação, para quando algo não abre.

Existe por causa do Windows. No Linux, quem instala o MOS-Studio tem um
terminal à mão e vê o erro na hora. No Windows o programa é uma janela: se
o Qt não encontrar um plugin, se o motor não estiver onde devia, se o
Python do pacote estiver incompleto, a janela simplesmente não aparece e não
há onde ler o motivo.

``MOS-Studio.exe --diagnostico`` grava este relatório num arquivo de texto
ao lado do executável e o mostra. É também o que a máquina virtual de testes
executa para dizer se o pacote de Windows ficou bom
(``empacotar/testar_windows.py``).
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

from . import paths


def _linha(rotulo: str, valor: object) -> str:
    return f"{rotulo:<22} {valor}"


def _escrever(texto: str) -> None:
    """Escreve na saída padrão, se houver uma.

    Num executável de janela do Windows, ``sys.stdout`` pode ser ``None`` —
    não há console para onde escrever. ``sys.stdout.write`` ali levanta
    ``AttributeError`` e derruba justamente o relatório que deveria explicar
    o problema. Daí a guarda.
    """
    fluxo = sys.stdout
    if fluxo is None:
        return
    try:
        fluxo.write(texto)
        fluxo.flush()
    except (OSError, ValueError):
        pass


def _ambiente() -> list[str]:
    return [
        "AMBIENTE",
        _linha("sistema", f"{platform.system()} {platform.release()} "
                          f"({platform.machine()})"),
        _linha("python", sys.version.replace("\n", " ")),
        _linha("executável", sys.executable),
        _linha("pasta do programa", paths.APP_ROOT),
        _linha("configuração", paths.config_dir()),
    ]


def _qt() -> tuple[list[str], list[str]]:
    """Linhas do relatório e problemas encontrados na parte gráfica."""
    linhas = ["", "INTERFACE GRÁFICA"]
    problemas: list[str] = []
    try:
        import PySide6
        from PySide6.QtCore import qVersion
    except Exception as erro:                      # pragma: no cover - ambiente
        problemas.append(f"PySide6 não carrega: {erro}")
        linhas.append(_linha("PySide6", f"FALHOU — {erro}"))
        return linhas, problemas

    linhas.append(_linha("PySide6", PySide6.__version__))
    linhas.append(_linha("Qt", qVersion()))
    linhas.append(_linha("plugins do Qt", Path(PySide6.__file__).parent
                         / "plugins"))

    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        linhas.append(_linha("plataforma", app.platformName()))
    except Exception as erro:                      # pragma: no cover - ambiente
        problemas.append(f"o Qt não inicia: {erro}")
        linhas.append(_linha("plataforma", f"FALHOU — {erro}"))
    return linhas, problemas


def _motores() -> tuple[list[str], list[str]]:
    """Linhas do relatório e problemas de cada motor de simulação."""
    from .core import engines, minimos

    linhas = ["", "MOTORES DE SIMULAÇÃO"]
    problemas: list[str] = []
    algum = False
    for motor in engines.all_engines():
        pasta = motor.find_run_dir()
        if motor.available():
            algum = True
            linhas.append(_linha(motor.label, f"pronto — {pasta}"))
        else:
            faltas = motor.check(pasta)
            linhas.append(_linha(motor.label,
                                 "indisponível — " + "; ".join(faltas)))
    if not algum:
        problemas.append("nenhum motor de processo está utilizável")

    pasta = minimos.find_dir()
    if pasta is not None and not minimos.check_engine(pasta):
        linhas.append(_linha("MINIMOS 6.1", f"pronto — {pasta}"))
    else:
        faltas = minimos.check_engine(pasta)
        linhas.append(_linha("MINIMOS 6.1",
                             "indisponível — " + "; ".join(faltas)))
    return linhas, problemas


def _janela() -> tuple[list[str], list[str]]:
    """Monta a janela principal de verdade, sem entrar no laço de eventos.

    É o teste que importa: importar o PySide6 prova pouco, porque quase todo
    problema de empacotamento aparece ao criar o primeiro widget ou ao
    carregar a folha de estilo.
    """
    linhas = ["", "JANELA PRINCIPAL"]
    problemas: list[str] = []
    try:
        from .app import build_application

        app, janela = build_application([sys.argv[0]])
        janela.resize(1280, 800)
        app.processEvents()
        from PySide6.QtWidgets import QWidget

        linhas.append(_linha("construída", f"{janela.windowTitle()} — "
                             f"{janela.width()}x{janela.height()} px"))
        linhas.append(_linha("widgets", len(janela.findChildren(QWidget))))
        # Fechar não é cortesia: o ``closeEvent`` é quem encerra as threads de
        # sondagem dos motores e a sessão do Console. Sem isso o processo
        # aborta no fim com "QThread: Destroyed while thread is still
        # running", e o relatório viraria um falso negativo.
        janela.close()
        app.processEvents()
        linhas.append(_linha("encerrada", "sem threads pendentes"))
    except Exception as erro:                      # pragma: no cover - ambiente
        import traceback

        problemas.append(f"a janela não monta: {erro}")
        linhas.append(_linha("construída", f"FALHOU — {erro}"))
        linhas.extend("  " + l for l in
                      traceback.format_exc().strip().splitlines()[-6:])
    return linhas, problemas


def relatorio() -> tuple[str, list[str]]:
    """Devolve (texto do relatório, lista de problemas)."""
    linhas = _ambiente()
    problemas: list[str] = []
    for parte in (_qt, _motores, _janela):
        novas, achados = parte()
        linhas.extend(novas)
        problemas.extend(achados)

    linhas.append("")
    if problemas:
        linhas.append("PROBLEMAS")
        linhas.extend(f"  - {p}" for p in problemas)
    else:
        linhas.append("Nenhum problema encontrado.")
    return "\n".join(linhas) + "\n", problemas


def executar(destino: Path | None = None) -> int:
    """Escreve o relatório e devolve 0 se estiver tudo bem, 1 se não.

    No Windows, sem console, a saída padrão vai para o nada; por isso o
    relatório também é gravado em arquivo. ``destino`` existe para os
    testes; por padrão é ``diagnostico.txt`` na pasta do programa, e, se ela
    não aceitar escrita, na pasta de configuração do usuário.
    """
    texto, problemas = relatorio()
    _escrever(texto)

    if destino is None:
        destino = paths.APP_ROOT / "diagnostico.txt"
    try:
        destino.write_text(texto, encoding="utf-8")
    except OSError:
        destino = paths.config_dir() / "diagnostico.txt"
        try:
            destino.write_text(texto, encoding="utf-8")
        except OSError:
            destino = None
    if destino is not None:
        _escrever(f"\nRelatório gravado em {destino}\n")

    if os.environ.get("MOS_DIAGNOSTICO_SILENCIOSO"):
        return 1 if problemas else 0
    _mostrar(texto, problemas, destino)
    return 1 if problemas else 0


def _mostrar(texto: str, problemas: list[str], destino: Path | None) -> None:
    """Mostra o relatório numa janela, se houver interface disponível."""
    try:
        from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                                       QPlainTextEdit, QVBoxLayout)
    except Exception:                              # pragma: no cover - ambiente
        return
    app = QApplication.instance()
    if app is None:
        return
    if app.platformName() in ("offscreen", "minimal"):
        # Sem tela, o diálogo seria invisível e o exec() esperaria para
        # sempre por um clique — o instalador ficaria parado no fim.
        return

    dialogo = QDialog()
    dialogo.setWindowTitle("MOS-Studio — diagnóstico")
    dialogo.resize(760, 560)
    corpo = QVBoxLayout(dialogo)
    area = QPlainTextEdit(texto + (f"\nRelatório gravado em {destino}\n"
                                   if destino else ""))
    area.setReadOnly(True)
    # Fonte de largura fixa: o relatório é alinhado em colunas.
    fonte = area.font()
    fonte.setFamily("monospace")
    area.setFont(fonte)
    corpo.addWidget(area)
    botoes = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    botoes.rejected.connect(dialogo.reject)
    botoes.accepted.connect(dialogo.accept)
    corpo.addWidget(botoes)
    dialogo.exec()
