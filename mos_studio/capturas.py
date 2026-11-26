"""Captura as telas do MOS-Studio em PNG, sem precisar de tela de verdade.

As imagens do README saem daqui, e não de um recorte feito à mão: assim elas
podem ser refeitas depois de qualquer mudança na interface, nos dois temas,
sempre do mesmo tamanho e com o mesmo conteúdo. Uma captura desatualizada é
pior que nenhuma.

Duas decisões que valem explicar:

**O motor roda de verdade.** As telas de Resultados, Dispositivo, Estruturas
e Modelos só têm o que mostrar depois de uma simulação. A captura executa a
receita de porta do NMOS (1-D) e a receita 2-D padrão, pelos mesmos caminhos
que a interface usa quando alguém clica em *Simular*. É lento de propósito:
uma imagem de tela vazia não documenta nada.

**O ambiente é descartável.** A captura corre num ``HOME`` temporário, então
as imagens não mostram o histórico de execuções nem as preferências de quem
rodou. Sem isso, as figuras do README trariam a lista de simulações da
máquina do autor.

Uso (ver ``python -m mos_studio --help``)::

    python -m mos_studio --capturar docs/img/{tela}-claro.png --tema claro
    python -m mos_studio --capturar /tmp/inicio.png --tela inicio
"""

from __future__ import annotations

import os
import time
from pathlib import Path

#: O roteiro das capturas: cada tela, a legenda dela, e o que precisa
#: acontecer **antes** da foto.
#:
#: A ordem não é a da navegação, é a do estado: a Início vem primeiro, com o
#: programa recém-aberto e nenhuma execução na faixa de baixo; as telas de
#: resultado vêm depois da simulação correspondente. Cada ação roda uma vez
#: só — a simulação 1-D e a 2-D são feitas uma vez cada, não uma por foto.
ROTEIRO: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("inicio", "Início — motores, projetos recentes e por onde começar", ()),
    ("exemplos", "Exemplos — receitas 1-D e os decks de fábrica", ()),
    ("oxidacao", "Oxidação — Deal-Grove e o ajuste dos coeficientes", ()),
    ("processo", "Processo 1-D — a receita, passo a passo", ("receita1d",)),
    ("resultados", "Resultados 1-D — perfil de dopagem, camadas e junção",
     ("roda1d",)),
    ("dispositivo", "Dispositivo — MOSIM: curvas I-V e mapas 2-D",
     ("rodaminimos",)),
    ("malha", "Malha 2-D — linhas, regiões e contornos", ("vai2d",)),
    ("processo2d", "Processo 2-D — a receita do SUPREM-IV", ()),
    ("modelos", "Modelos — os coeficientes que o motor vai usar", ()),
    ("resultados2d", "Resultados 2-D — seção transversal e cortes",
     ("roda2d",)),
    ("console", "Console — o motor em sessão, carta por carta", ()),
    ("estrutura", "Estruturas — os arquivos que a simulação deixou", ()),
)

#: Só os nomes, na ordem do roteiro.
TELAS: tuple[tuple[str, str], ...] = tuple(
    (nome, legenda) for nome, legenda, _ in ROTEIRO)

#: Receita 1-D usada nas capturas: a região de porta de um NMOS, que forma
#: óxido fino, canal e poly — tem o que mostrar em todas as telas de 1-D.
RECEITA_1D = "nmos-porta"

#: Tamanho da janela nas capturas. Largo o bastante para o cabeçalho não
#: entrar em modo compacto e para os botões da barra de execução caberem
#: inteiros.
TAMANHO = (1600, 1000)

#: Teto de espera por uma execução, em segundos.
ESPERA = 300.0


def _tamanho(texto: str) -> tuple[int, int]:
    """Converte ``LARGURAxALTURA`` para um par de inteiros."""
    try:
        largura, altura = texto.lower().split("x")
        return max(int(largura), 800), max(int(altura), 600)
    except (ValueError, AttributeError):
        return TAMANHO


def _esperar(app, janela, segundos: float = ESPERA) -> None:
    """Deixa o Qt respirar até a execução em curso terminar.

    Sem isto a foto sairia no meio do carregamento — com a faixa de execução
    em "simulando" e o gráfico ainda vazio.
    """
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        app.processEvents()
        if not janela._run.running:
            break
        time.sleep(0.1)
    # Mais umas voltas, para os widgets que só redesenham ao receber o
    # resultado terminarem de se compor.
    for _ in range(80):
        app.processEvents()
        time.sleep(0.02)


def _assentar(app, voltas: int = 25) -> None:
    """Dá tempo de a tela recém-aberta terminar de se compor."""
    for _ in range(voltas):
        app.processEvents()
        time.sleep(0.02)


def capturar(destino: str, tema: str = "", telas: tuple[str, ...] = (),
             tamanho: str = "") -> int:
    """Salva uma ou várias telas em PNG. Devolve 0 se tudo saiu.

    Com ``{tela}`` no caminho, percorre todas as telas de :data:`TELAS` (ou
    só as listadas em ``telas``) e escreve um arquivo para cada uma. Sem
    ``{tela}``, salva uma tela só.
    """
    import tempfile

    # Sem isto o Qt tentaria abrir uma janela de verdade; a captura tem de
    # funcionar numa máquina sem sessão gráfica.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    quais = tuple(telas) or tuple(nome for nome, _ in TELAS)
    varios = "{tela}" in destino
    if not varios:
        quais = quais[:1]

    with tempfile.TemporaryDirectory(prefix="mos_capturas_") as casa:
        # HOME descartável: as imagens não mostram o histórico nem as
        # preferências de quem rodou (ver a nota no topo do módulo).
        anteriores = {v: os.environ.get(v)
                      for v in ("HOME", "XDG_CONFIG_HOME")}
        os.environ["HOME"] = casa
        os.environ["XDG_CONFIG_HOME"] = str(Path(casa) / ".config")
        try:
            return _capturar(destino, tema, quais, tamanho, varios)
        finally:
            for nome, valor in anteriores.items():
                if valor is None:
                    os.environ.pop(nome, None)
                else:
                    os.environ[nome] = valor


def _acoes(janela, app, quais: tuple[str, ...]) -> dict[str, object]:
    """As ações do roteiro, em funções nomeadas."""
    def receita1d() -> None:
        janela.open_recipe_1d(RECEITA_1D)
        _assentar(app)

    def roda1d() -> None:
        receita1d()
        janela.start_run()
        _esperar(app, janela)

    def rodaminimos() -> None:
        """Leva o perfil ao motor de dispositivo e espera a curva I-V.

        As figuras mostram o MOSIM, que é o motor que o pacote entrega (o
        MINIMOS, por licença, cada usuário instala o seu). Sem execução a tela
        mostra só "Rode a simulação para ver a curva" — nada que valha figura.
        """
        from .core import minimos as _mm
        _mm.definir_motor(_mm.MOTOR_ABERTO)
        janela.go("dispositivo")
        _assentar(app)
        janela.dispositivo._refresh_engine()
        janela.dispositivo._refresh_bridge()
        janela.dispositivo._refresh_source_note()
        janela.dispositivo.run()
        limite = time.monotonic() + ESPERA
        while time.monotonic() < limite:
            app.processEvents()
            if janela.dispositivo._worker is None:
                break
            time.sleep(0.1)
        _assentar(app, 80)

    def vai2d() -> None:
        janela.set_dimension("2d")
        _assentar(app)

    def roda2d() -> None:
        vai2d()
        janela.start_run()
        _esperar(app, janela)

    del quais
    return {"receita1d": receita1d, "roda1d": roda1d,
            "rodaminimos": rodaminimos, "vai2d": vai2d, "roda2d": roda2d}


def _capturar(destino: str, tema: str, quais: tuple[str, ...],
              tamanho: str, varios: bool) -> int:
    from .app import build_application
    from .ui import theme

    app, janela = build_application(["mos-studio"])
    if tema:
        theme.apply(app, tema)
    largura, altura = _tamanho(tamanho) if tamanho else TAMANHO
    janela.resize(largura, altura)
    janela.show()
    _assentar(app)

    acoes = _acoes(janela, app, quais)
    feitas: set[str] = set()
    pedidas = set(quais)
    molde = str(destino)
    escritos = 0
    try:
        for nome, _legenda, preparo in ROTEIRO:
            if nome not in pedidas:
                # As ações continuam valendo mesmo quando a tela não foi
                # pedida: pular a simulação 1-D deixaria a tela de
                # Dispositivo sem perfil para mostrar.
                _rodar_preparo(preparo, acoes, feitas)
                continue
            _rodar_preparo(preparo, acoes, feitas)
            janela.go(nome)
            _assentar(app)
            caminho = Path(molde.replace("{tela}", nome))
            caminho.parent.mkdir(parents=True, exist_ok=True)
            if not janela.grab().save(str(caminho)):
                print(f"!! não consegui salvar {caminho}")
                return 1
            escritos += 1
            print(f"   {caminho}  {largura}×{altura}  "
                  f"{caminho.stat().st_size // 1024} kB")
            if not varios:
                break
    finally:
        janela.close()
        app.processEvents()

    print(f">> {escritos} captura(s){f' · tema {tema}' if tema else ''}")
    return 0


def _rodar_preparo(preparo: tuple[str, ...], acoes: dict,
                   feitas: set[str]) -> None:
    """Executa as ações que ainda não rodaram."""
    for acao in preparo:
        if acao not in feitas:
            feitas.add(acao)
            acoes[acao]()
