"""Os exemplos de fábrica do SUPREM-IV, como catálogo da interface.

O capítulo 4 do manual traz dezessete exemplos, e o build instala todos em
``suprem4-run/examples``. Esta é a ponte entre eles e a tela de Exemplos:
nome, dimensão, descrição e quais cartões o deck usa.

A descrição de cada um foi conferida lendo o deck, não a numeração — e as do
mockup estavam trocadas em três casos:

* **exam6** não é LOCOS: é a calibração da oxidação, com um ``foreach`` sobre
  as três orientações do substrato.
* **exam7** é o LOCOS (``fullrox`` = *full recessed oxide*): recesso, óxido
  fino, nitreto e oxidação úmida com o modelo compressível.
* a exportação para o PISCES é o segundo deck do **exam5**
  (``struct pisc=ldd.mesh``), não o exam8, que é o nitreto sob tensão.

Dois decks de fábrica são recusados pelo próprio motor, por defeito deles e
não da compilação; ficam marcados com :attr:`Example.broken` para a tela
poder avisar antes de o usuário clicar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Defeito comum ao exam11 e ao exam12, conferido no binário.
_GAAS_SILICON = (
    "O deck pede “select z=log10(silicon)”, mas neste arquivo de chaves "
    "“silicon” é nome de material: em GaAs o silício implantado é a espécie "
    "“isilicon”. A nota de GaAs do fonte contradiz o suprem.key."
)

#: Cartões que a tela lista como "o que este exemplo demonstra". Só os que
#: dizem algo sobre o processo: ``line`` e ``region`` estão em todos.
_INTERESSANTES = (
    "mode", "initialize", "implant", "deposit", "etch", "diffuse", "method",
    "oxide", "stress", "structure", "select", "contour", "plot.2d", "plot.1d",
    "print.1d", "device", "foreach", "interstitial", "vacancy", "trap",
)


@dataclass(frozen=True)
class Example:
    """Um exemplo do manual."""

    id: str
    #: Caminho relativo a ``examples/``, como ``exam5/whole.s4``.
    path: str
    name: str
    #: ``"1-D"`` ou ``"2-D"``, pela presença de um eixo x na malha.
    dim: str
    desc: str
    #: Motivo da recusa, quando o deck é defeituoso de fábrica.
    broken: str = ""
    #: Arquivos vizinhos que o deck lê e que precisam ir para a pasta de
    #: execução junto com ele.
    needs: tuple[str, ...] = ()
    #: ``True`` quando o deck continua a estrutura deixada por outro, em vez
    #: de montar a própria malha. A dimensão desses não dá para deduzir do
    #: texto: o ``sup2pis.s4`` não tem cartão ``line`` nenhum.
    continuation: bool = False
    #: Deck que precisa rodar antes, no mesmo processo. Sozinho, o
    #: ``sup2pis.s4`` responde "Pisces mesh i/o error: please specify a
    #: temperature", porque a temperatura vem da última difusão do exam5.
    after: str = ""

    @property
    def runnable(self) -> bool:
        return not self.broken


#: O catálogo. A ordem é a da tela: primeiro os 1-D de aprendizado, depois os
#: 2-D de dispositivo.
CATALOG: tuple[Example, ...] = (
    Example("exam1", "exam1/boron.in", "Difusão de boro", "1-D",
            "Implantação de boro e recozimento num substrato tipo n, com "
            "perfil antes e depois. É o exemplo de partida do manual."),
    Example("exam2", "exam2/oed.in", "Oxidação e difusão", "1-D",
            "Implante de boro sob óxido crescido, com o modelo de difusão "
            "escolhido no cartão method."),
    Example("exam3", "exam3/oed.in", "Difusão assistida por oxidação", "1-D",
            "O mesmo processo com defeitos pontuais acoplados: é o efeito "
            "OED, em que a oxidação acelera a difusão abaixo dela."),
    Example("exam4", "exam4/oed.in", "OED em duas dimensões", "2-D",
            "A mesma física do exam3 com o eixo lateral, mostrando que a "
            "aceleração só vale sob a área oxidada."),
    Example("exam6", "exam6/oxcalib.s4", "Calibração da oxidação", "2-D",
            "Um foreach sobre ⟨100⟩, ⟨110⟩ e ⟨111⟩ para comparar as taxas de "
            "oxidação das três orientações. A malha é 2-D com uma coluna só: "
            "serve de oxidação 1-D.",
            broken="O echo decorativo do deck tem “< O >”, que o avaliador "
                   "de expressão do shell recusa. A oxidação roda e sai nas "
                   "três orientações; só o cabeçalho falha."),
    Example("exam5", "exam5/whole.s4", "Transistor LDD", "2-D",
            "O processo completo: óxido de porta, poli dopado, corrosão da "
            "porta, implante de extensão, espaçador e fonte/dreno. É o "
            "projeto guiado da interface.",
            needs=("sup2pis.s4",)),
    Example("exam5pis", "exam5/sup2pis.s4", "Exportação para o PISCES", "2-D",
            "Contato, metalização e gravação da estrutura no formato do "
            "simulador de dispositivo. Continua o exam5 e precisa da "
            "estrutura que ele deixa.",
            needs=("whole.s4",), continuation=True, after="whole.s4"),
    Example("exam7", "exam7/fullrox.s4", "Isolação LOCOS", "2-D",
            "Óxido totalmente recessado: recesso no silício, óxido fino, "
            "nitreto e oxidação úmida com o modelo compressível. É onde "
            "aparece o bico de pássaro."),
    Example("exam9", "exam9/sdep.s4", "LOCOS com tensão", "2-D",
            "O mesmo LOCOS com oxidação dependente de tensão (Vc/Vr/Vd e "
            "modelo viscoso), que muda a forma do bico de pássaro."),
    Example("exam8", "exam8/nit-stress.s4", "Tensão no nitreto", "2-D",
            "Calcula a tensão mecânica numa borda de nitreto e desenha as "
            "linhas de nível do campo de tensão."),
    Example("exam10", "exam10/example10.in", "Berílio em GaAs", "1-D",
            "Difusão de berílio em arseneto de gálio, com os coeficientes "
            "do cartão da espécie."),
    Example("exam11", "exam11/example11.in", "Dopantes em GaAs", "2-D",
            "Silício implantado em GaAs através de uma janela de nitreto, "
            "com difusão lateral sob a máscara.",
            broken=_GAAS_SILICON),
    Example("exam12", "exam12/example12.in", "Ativação em GaAs", "1-D",
            "Modelo de ativação dependente da temperatura em GaAs.",
            broken=_GAAS_SILICON),
    Example("exam13", "exam13/example13.in", "Difusão de zinco", "1-D",
            "Zinco em GaAs, que difunde rápido e serve de teste do passo "
            "de tempo adaptativo."),
    Example("exam14", "exam14/example14.in", "Germânio e estanho", "1-D",
            "Espécies pesadas em GaAs pelos cartões germanium e tin."),
    Example("exam15", "exam15/example15.in", "Perfil lido de arquivo", "1-D",
            "Carrega um perfil medido de um arquivo externo em vez de "
            "calcular o implante.",
            needs=("be1",)),
    Example("exam16", "exam16/example16.in", "Perfil tabelado", "1-D",
            "Usa o cartão profile para impor uma distribuição vinda de "
            "fora do motor.",
            needs=("file1",)),
    Example("exam17", "exam17/example17.in", "Carbono em GaAs", "1-D",
            "Difusão de carbono com o cartão da espécie e defeitos "
            "pontuais de GaAs."),
)


def get(example_id: str) -> Example | None:
    return next((e for e in CATALOG if e.id == example_id), None)


def base_dir(run_dir: Path | None = None) -> Path | None:
    """Pasta ``examples`` da instalação, ou ``None`` se não houver motor."""
    from . import suprem4

    rd = Path(run_dir) if run_dir else suprem4.find_run_dir()
    if rd is None:
        return None
    pasta = Path(rd) / "examples"
    return pasta if pasta.is_dir() else None


def deck_path(ex: Example, run_dir: Path | None = None) -> Path | None:
    base = base_dir(run_dir)
    if base is None:
        return None
    p = base / ex.path
    return p if p.is_file() else None


def installed(run_dir: Path | None = None) -> list[Example]:
    """Exemplos que estão de fato instalados."""
    return [e for e in CATALOG if deck_path(e, run_dir) is not None]


def read(ex: Example, run_dir: Path | None = None) -> str:
    """O texto do deck, como está no disco."""
    p = deck_path(ex, run_dir)
    if p is None:
        return ""
    try:
        return p.read_text(encoding="latin1", errors="replace")
    except OSError:
        return ""


@lru_cache(maxsize=64)
def _cards_of(texto: str) -> tuple[str, ...]:
    """Cartões interessantes que o deck usa, na ordem de primeira aparição.

    Os decks de fábrica abreviam tudo (``bound expo``, ``meth compr``,
    ``stru outf=``, ``init or=100``), então o cabeçalho de cada linha é
    resolvido pelo ``suprem.key`` antes de entrar na lista.
    """
    from . import keyfile

    vistos: list[str] = []
    for linha in texto.splitlines():
        s = linha.strip()
        if not s or s.startswith("#"):
            continue
        cabeca = re.split(r"[\s=]", s, maxsplit=1)[0].lower()
        nome = keyfile.resolve(cabeca) or cabeca
        if nome in _INTERESSANTES and nome not in vistos:
            vistos.append(nome)
    return tuple(vistos)


def cards(ex: Example, run_dir: Path | None = None) -> list[str]:
    """Cartões que o exemplo demonstra, para a legenda do cartão da tela."""
    return list(_cards_of(read(ex, run_dir)))


def summary(ex: Example, run_dir: Path | None = None) -> str:
    """A linha de cartões como a tela mostra: ``initialize · implant · …``."""
    return " · ".join(cards(ex, run_dir)[:5])


def dim_of(ex: Example, run_dir: Path | None = None) -> str:
    """Dimensão que a tela mostra.

    Vale a do deck, não a do catálogo: foi assim que se descobriu que o
    ``exam6`` e o ``exam11`` montam malha 2-D, ao contrário do que a
    descrição sugeria. A exceção são os decks de continuação, que não têm
    malha própria para deduzir.
    """
    if ex.continuation:
        return ex.dim
    return detect_dim(ex, run_dir)


def detect_dim(ex: Example, run_dir: Path | None = None) -> str:
    """Dimensão deduzida do texto do deck.

    Um deck é 2-D quando define linhas no eixo x. Os 1-D do manual rodam em
    ``mode one.dim`` ou só com o eixo y.
    """
    texto = read(ex, run_dir)
    if not texto:
        return ex.dim
    if re.search(r"^\s*mode\s+one\.dim", texto, re.MULTILINE | re.IGNORECASE):
        return "1-D"
    tem_x = re.search(r"^\s*line\s+x\b", texto, re.MULTILINE | re.IGNORECASE)
    return "2-D" if tem_x else "1-D"


def run_deck(ex: Example, prep: "Prepared") -> str:
    """O que mandar ao motor para rodar este exemplo.

    Em geral é o nome do deck, que o motor recebe na linha de comando. Um
    deck de continuação precisa do anterior no **mesmo** processo, e aí a
    interface manda um deck de duas linhas de ``source``: a estrutura e a
    temperatura ficam na memória entre os dois.
    """
    if not ex.after:
        return f"source {prep.deck_name}\nquit\n"
    return f"source {ex.after}\nsource {prep.deck_name}\nquit\n"


@dataclass
class Prepared:
    """Um exemplo copiado para uma pasta de trabalho, pronto para rodar."""

    example: Example
    work_dir: Path
    deck_name: str
    missing: list[str] = field(default_factory=list)


def prepare(ex: Example, work_dir: Path,
            run_dir: Path | None = None) -> Prepared:
    """Copia o deck e os vizinhos de que ele precisa para ``work_dir``.

    Os exemplos leem arquivos da própria pasta — ``exam15`` carrega ``be1``,
    ``exam5/sup2pis.s4`` continua a estrutura que o ``whole.s4`` deixa. Copiar
    a pasta inteira é mais simples e mais seguro que adivinhar quais.
    """
    import shutil

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    p = deck_path(ex, run_dir)
    if p is None:
        return Prepared(ex, work_dir, "", missing=[ex.path])
    faltando: list[str] = []
    for vizinho in p.parent.iterdir():
        if vizinho.is_file():
            try:
                shutil.copy2(vizinho, work_dir / vizinho.name)
            except OSError:
                faltando.append(vizinho.name)
    return Prepared(ex, work_dir, p.name, missing=faltando)
