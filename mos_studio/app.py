"""Ponto de entrada do MOS-Studio.

Lê o tema da configuração do usuário, aplica a folha de estilo e abre a janela.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import config
from .ui import theme
from .ui.main_window import APP_NAME, MainWindow


def build_application(argv: list[str] | None = None) -> tuple[QApplication, MainWindow]:
    """Cria o ``QApplication`` e a janela, já com o tema aplicado.

    Separado de :func:`main` para que os testes possam montar a interface sem
    entrar no laço de eventos.
    """
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)

    config.migrate_legacy()      # traz um config.json antigo da pasta do programa
    tema = config.get("tema", theme.DEFAULT_THEME)
    theme.apply(app, tema)

    janela = MainWindow()
    return app, janela


def _analisador():
    """Opções de linha de comando.

    O programa é uma janela: quem o abre pelo menu nunca vê nada disto. As
    opções existem para os três casos em que não há janela — diagnosticar uma
    instalação que não abre, escolher o tema de uma sessão, e gerar as
    imagens da documentação.
    """
    import argparse

    from .capturas import TELAS

    a = argparse.ArgumentParser(
        prog="mos-studio",
        description="Simulação de processos e dispositivos semicondutores.")
    a.add_argument("--tema", choices=("claro", "escuro"),
                   help="terreno desta sessão; sem isto vale o que ficou "
                        "salvo nas preferências")
    a.add_argument("--tela", choices=[n for n, _ in TELAS],
                   help="tela em que abrir")
    a.add_argument("--diagnostico", "--autoteste", action="store_true",
                   dest="diagnostico",
                   help="confere a instalação, escreve um relatório e sai")
    a.add_argument("--capturar", metavar="PNG",
                   help="(dev) salva a janela em PNG e sai; com {tela} no "
                        "nome, percorre as doze telas")
    a.add_argument("--tamanho", metavar="LxA",
                   help="(dev) tamanho da janela nas capturas, ex. 1600x1000")
    return a


def main(argv: list[str] | None = None) -> int:
    """Abre o aplicativo, ou faz o que a linha de comando pediu."""
    argumentos = list(sys.argv if argv is None else argv)
    opcoes, _ = _analisador().parse_known_args(argumentos[1:])

    if opcoes.diagnostico:
        # Não abre a janela: monta tudo, confere o que está instalado e
        # escreve um relatório. É a única forma de ver o motivo de uma falha
        # no Windows, onde o programa não tem console — ver
        # :mod:`mos_studio.diagnostico`.
        from .diagnostico import executar

        return executar()

    if opcoes.capturar:
        from .capturas import capturar

        return capturar(opcoes.capturar, tema=opcoes.tema or "",
                        telas=(opcoes.tela,) if opcoes.tela else (),
                        tamanho=opcoes.tamanho or "")

    app, janela = build_application(argv)
    if opcoes.tema:
        theme.apply(app, opcoes.tema)
    if opcoes.tela:
        janela.go(opcoes.tela)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
