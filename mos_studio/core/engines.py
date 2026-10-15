"""Registro dos motores de simulação de processo, com uma interface só.

O MOS-Studio tem dois simuladores de processo que falam dialetos diferentes e
leem/escrevem de formas diferentes: o SUPREM-III (três binários em cadeia,
tabela em arquivo) e o SUPREM-IV.GS (um binário, tabela na saída padrão). A
interface não deveria saber disso. Este módulo é a costura: cada motor é um
:class:`Engine` com as mesmas sete operações, e a tela só escolhe um.

O que **não** está escondido aqui são as diferenças de física. Uma receita
traduzida para o SUPREM-IV pode perder coisas (epitaxia, por exemplo —
ver :func:`mos_studio.core.deck4.approximations`), e ``Engine.approximations``
existe justamente para a interface poder dizer isso em voz alta. Esconder
seria pior que não ter o segundo motor: o usuário compararia dois resultados
achando que simulou a mesma coisa.

Uso::

    from mos_studio.core import engines

    motor = engines.get(engines.default_id())
    deck = motor.build_in_file("Meu processo", steps)
    resultado = motor.runner(deck).execute()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

#: Identificador do SUPREM-III (o motor histórico do MOS-Studio).
SUPREM3 = "suprem3"
#: Identificador do SUPREM-IV.GS.
SUPREM4 = "suprem4"

#: Chave de configuração em que a escolha do usuário fica guardada.
CONFIG_KEY = "engine"


@dataclass(frozen=True)
class Engine:
    """Um motor de simulação de processo, visto pela interface.

    ``id`` é a chave estável (vai para a configuração e para o registro de
    execuções); ``label`` é o nome mostrado; ``blurb`` é a frase que explica
    quando escolher este e não o outro.
    """

    id: str
    label: str
    blurb: str
    #: ``() -> bool`` — o motor está instalado e utilizável?
    available: Callable[[], bool]
    #: ``(run_dir) -> list[str]`` — problemas que impedem rodar.
    check: Callable[[Any], list[str]]
    #: ``() -> Path | None`` — pasta do motor.
    find_run_dir: Callable[[], Any]
    #: ``(titulo, passos) -> str``
    build_in_file: Callable[[str, list[dict]], str]
    #: ``(titulo, passos) -> (texto, plano)``
    build_profile_deck: Callable[[str, list[dict]], tuple[str, list[tuple[str, str]]]]
    #: Classe do executor, com ``execute(on_stage=...)`` e ``cancel()``.
    runner: Any
    #: Exceção de cancelamento levantada por ``runner.execute``.
    cancelled: type[Exception]
    #: ``(deck, run_dir=None) -> str`` — execução síncrona, devolve a saída.
    run_sync: Callable[..., str]
    #: ``(saida) -> float | None`` — espessura de óxido em µm.
    oxide_thickness: Callable[[str], float | None]
    #: ``(passos) -> list[str]`` — o que a tradução não reproduz fielmente.
    approximations: Callable[[list[dict]], list[str]]


def _suprem3() -> Engine:
    from . import deck, parsers, suprem
    return Engine(
        id=SUPREM3,
        label="SUPREM-III",
        blurb="Perfis 1D, rápido e o que as receitas deste programa sempre "
              "usaram. Limite de 500 nós de malha.",
        available=lambda: not suprem.check_engine(suprem.find_run_dir()),
        check=suprem.check_engine,
        find_run_dir=suprem.find_run_dir,
        build_in_file=deck.build_in_file,
        build_profile_deck=deck.build_profile_deck,
        runner=suprem.SupremRunner,
        cancelled=suprem.Cancelled,
        run_sync=suprem.run_sync,
        oxide_thickness=parsers.parse_oxide_thickness,
        approximations=lambda passos: [],
    )


def _suprem4() -> Engine:
    from . import deck4, parsers, suprem4
    return Engine(
        id=SUPREM4,
        label="SUPREM-IV.GS",
        blurb="Modelos de difusão e oxidação mais novos (ponto-defeito, "
              "oxidação viscosa) e malha sem teto fixo. Epitaxia é "
              "aproximada por deposição dopada.",
        available=suprem4.available,
        check=suprem4.check_engine,
        find_run_dir=suprem4.find_run_dir,
        build_in_file=deck4.build_in_file,
        build_profile_deck=deck4.build_profile_deck,
        runner=suprem4.Suprem4Runner,
        cancelled=suprem4.Cancelled,
        run_sync=suprem4.run_sync,
        oxide_thickness=parsers.parse_print_1d_oxide,
        approximations=deck4.approximations,
    )


_BUILDERS = {SUPREM3: _suprem3, SUPREM4: _suprem4}

#: Ordem em que os motores aparecem na interface.
ORDER = (SUPREM3, SUPREM4)

_cache: dict[str, Engine] = {}


def get(engine_id: str) -> Engine:
    """Devolve o motor pelo identificador.

    Um identificador desconhecido cai no SUPREM-III em vez de levantar: a
    configuração do usuário pode ter sido escrita por uma versão mais nova do
    programa, e isso não é motivo para a tela não abrir.
    """
    chave = engine_id if engine_id in _BUILDERS else SUPREM3
    if chave not in _cache:
        _cache[chave] = _BUILDERS[chave]()
    return _cache[chave]


def all_engines() -> list[Engine]:
    """Todos os motores, na ordem da interface (instalados ou não)."""
    return [get(i) for i in ORDER]


def installed() -> list[Engine]:
    """Só os motores que estão realmente utilizáveis agora."""
    return [e for e in all_engines() if e.available()]


def default_id() -> str:
    """Motor a usar quando ninguém escolheu.

    Respeita a escolha salva se o motor correspondente estiver instalado;
    senão, o primeiro instalado; senão, o SUPREM-III (e a tela mostrará os
    problemas de instalação dele, que é a mensagem útil).
    """
    from .. import config

    salvo = str(config.get(CONFIG_KEY, "") or "")
    if salvo in _BUILDERS and get(salvo).available():
        return salvo
    for motor in all_engines():
        if motor.available():
            return motor.id
    return SUPREM3


def set_default(engine_id: str) -> None:
    """Guarda a escolha do usuário."""
    from .. import config

    if engine_id in _BUILDERS:
        config.set(CONFIG_KEY, engine_id)
