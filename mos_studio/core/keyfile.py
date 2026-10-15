"""Leitura do ``suprem.key``: a gramática que o próprio motor usa.

O ``suprem.key`` é o arquivo que o SUPREM-IV lê no início para saber quais
cartões existem, quais parâmetros cada um aceita, de que tipo, com que valor
padrão e — o que é ouro para a interface — **com que unidade**. O ``keyread``
compila esse texto no ``suprem.uk`` binário que o motor carrega.

Ler daqui resolve três problemas de uma vez:

* a lista de parâmetros da tela de Modelos deixa de ser uma tabela escrita à
  mão (que envelhece em silêncio) e passa a ser a do motor;
* cada campo ganha o texto de unidade que o motor declara, em vez de uma
  legenda inventada;
* dá para validar um cartão antes de executar, e resolver abreviações —
  ``interst`` é prefixo de ``interstitial``, e o motor aceita os dois.

Formato: ``card nome;`` seguido de um bloco entre chaves com declarações
terminadas em ponto e vírgula::

    float Dix.0 = 0.214 units = "Pre-exponential constant for Vo cm2/sec"
    message = "Negative values for Dix.0 will screw up the program"
    error = Dix.0 < 0.0;

``switch nome = N { boolean a; boolean b; }`` agrupa opções mutuamente
exclusivas — é assim que o material de um cartão é escolhido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Comprimento máximo de um nome de parâmetro. É o ``char name[12]`` de
#: ``include/check.h``: onze caracteres mais o terminador. O ``keyread``
#: trunca silenciosamente ao compilar o ``suprem.uk``, e o motor depois recusa
#: o nome completo — ``method interstitial`` dá "parameter interstitial does
#: not exist for this command", enquanto ``method interstitia`` é aceito.
#: Guardar o nome truncado aqui faz a interface emitir o que o motor aceita.
MAX_PARAM = 11

#: Tipos de declaração que aparecem no arquivo. São estes sete e só estes,
#: conferidos contra o arquivo inteiro. ``integer`` vem antes de ``int`` por
#: clareza — o ``\s+`` já impediria ``int`` de casar com ``integer orient``,
#: que foi justamente o descuido que deixou a orientação do óxido de fora.
_TYPES = ("float", "integer", "int", "boolean", "string")

_DECL = re.compile(
    r"^(?P<type>" + "|".join(_TYPES) + r")\s+(?P<name>/?[\w.]+)"
    r"(?:\s*=\s*(?P<default>\"[^\"]*\"|\S+))?")
_UNITS = re.compile(r"\bunits\s*=\s*\"([^\"]*)\"")
_MESSAGE = re.compile(r"\bmessage\s*=\s*\"([^\"]*)\"")
_CARD = re.compile(r"^card\s+([\w.]+)")
_SWITCH = re.compile(r"^switch\s+([\w.]+)(?:\s*=\s*(\d+))?")


@dataclass
class Param:
    """Um parâmetro declarado num cartão."""

    name: str
    type: str = "float"
    default: str = ""
    units: str = ""
    message: str = ""
    #: Nome do ``switch`` a que pertence, se for uma opção exclusiva.
    switch: str = ""

    @property
    def numeric(self) -> bool:
        return self.type in ("float", "integer", "int")

    @property
    def flag(self) -> bool:
        return self.type == "boolean"

    def as_float(self) -> float | None:
        try:
            return float(self.default)
        except (TypeError, ValueError):
            return None


@dataclass
class Card:
    """Um cartão do deck, com todos os parâmetros que aceita."""

    name: str
    params: list[Param] = field(default_factory=list)
    #: Índice (base 1) da opção que fica ligada quando nenhuma é informada —
    #: é o ``def.ival`` que ``check/check.c`` usa para preencher o switch.
    switch_defaults: dict[str, int] = field(default_factory=dict)

    def switch_default(self, switch: str) -> str:
        """Nome da opção que o motor liga sozinho neste switch."""
        i = self.switch_defaults.get(switch, 0)
        opcoes = [p.name for p in self.params if p.flag and p.switch == switch]
        return opcoes[i - 1] if 0 < i <= len(opcoes) else ""

    def get(self, name: str) -> Param | None:
        """Um parâmetro pelo nome, aceitando abreviação por prefixo.

        O motor aceita prefixos também nos parâmetros — o próprio ``modelrc``
        escreve ``rel.err`` por ``rel.error`` e ``inter`` por
        ``interstitial``. Sem isso, procurar o padrão de ``rel.error`` no
        arquivo não acharia nada.
        """
        # A consulta é truncada como o motor truncou a declaração: quem pedir
        # ``interstitial`` recebe o ``interstitia`` que o motor conhece.
        alvo = name.strip().lower()[:MAX_PARAM]
        for p in self.params:
            if p.name.lower() == alvo:
                return p
        achados = [p for p in self.params if p.name.lower().startswith(alvo)]
        return achados[0] if len(achados) == 1 else None

    def canon(self, name: str) -> str:
        """Nome canônico de um parâmetro, ou o próprio nome se não resolver."""
        p = self.get(name)
        return p.name if p else name

    def numbers(self) -> list[Param]:
        return [p for p in self.params if p.numeric]

    def integers(self) -> list[Param]:
        """Parâmetros inteiros, que a interface mostra sem casa decimal."""
        return [p for p in self.params if p.type in ("integer", "int")]

    def flags(self, switch: str = "") -> list[Param]:
        """Opções booleanas, filtradas por ``switch`` se for informado.

        O ``/`` no começo do nome marca o segundo switch de material dos
        cartões de impureza (o par para o coeficiente de segregação); esses
        ficam de fora da lista comum para não aparecerem duplicados.
        """
        return [p for p in self.params
                if p.flag and (not switch or p.switch == switch)
                and not p.name.startswith("/")]

    def switches(self) -> list[str]:
        vistos: list[str] = []
        for p in self.params:
            if p.switch and p.switch not in vistos:
                vistos.append(p.switch)
        return vistos


def _statements(text: str):
    """Declarações do arquivo, com o nível de chaves e a pilha de switches.

    Gera ``(texto, abre_bloco, pilha_de_switches)``. Um ``switch`` só é
    conhecido quando o ``{`` seguinte abre, por isso ele fica pendente até lá.
    """
    buf: list[str] = []
    pilha: list[str] = []
    pendente = ""
    for ch in text:
        if ch in "{}":
            s = "".join(buf).strip()
            buf = []
            if s:
                yield s, False, list(pilha)
            if ch == "{":
                pilha.append(pendente)
                pendente = ""
            elif pilha:
                pilha.pop()
            continue
        if ch == ";":
            s = "".join(buf).strip()
            buf = []
            if s:
                m = _SWITCH.match(s)
                if m:
                    pendente = m.group(1)
                yield s, False, list(pilha)
            continue
        buf.append(ch)
    s = "".join(buf).strip()
    if s:
        yield s, False, list(pilha)


def parse(text: str) -> dict[str, Card]:
    """Todos os cartões do arquivo, pelo nome em minúsculas."""
    # Comentários vão até o fim da linha, mas '#' dentro de "..." não conta.
    limpo = re.sub(r'"[^"]*"|#[^\n]*',
                   lambda m: m.group(0) if m.group(0).startswith('"') else " ",
                   text)
    cards: dict[str, Card] = {}
    atual: Card | None = None
    for s, _, pilha in _statements(limpo):
        s = " ".join(s.split())
        m = _CARD.match(s)
        if m:
            atual = Card(m.group(1).lower())
            cards[atual.name] = atual
            continue
        if atual is None:
            continue
        m = _SWITCH.match(s)
        if m:
            if m.group(2):
                atual.switch_defaults[m.group(1)] = int(m.group(2))
            continue                      # o switch em si não é parâmetro
        m = _DECL.match(s)
        if not m:
            continue
        bruto = (m.group("default") or "").strip('"')
        u = _UNITS.search(s)
        msg = _MESSAGE.search(s)
        atual.params.append(Param(
            name=m.group("name")[:MAX_PARAM], type=m.group("type"),
            default=bruto,
            units=u.group(1) if u else "",
            message=msg.group(1) if msg else "",
            switch=next((q for q in reversed(pilha) if q), "")))
    return cards


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict[str, Card]:
    del mtime                              # só participa da chave do cache
    try:
        return parse(Path(path).read_text(encoding="latin1", errors="replace"))
    except OSError:
        return {}


def cards(run_dir: Path | None = None) -> dict[str, Card]:
    """Cartões da instalação, ou ``{}`` se o motor não estiver instalado."""
    from . import suprem4

    rd = Path(run_dir) if run_dir else suprem4.find_run_dir()
    if rd is None:
        return {}
    arquivo = Path(rd) / "data" / "suprem.key"
    try:
        mtime = arquivo.stat().st_mtime
    except OSError:
        return {}
    return _load(str(arquivo), mtime)


def resolve(name: str, run_dir: Path | None = None) -> str:
    """Nome canônico de um cartão, aceitando abreviação por prefixo.

    É o que o motor faz: ``interst`` chega ao ``interstitial``. Um prefixo
    ambíguo devolve ``""``, como o motor também recusaria.
    """
    alvo = name.strip().lower()
    todos = cards(run_dir)
    if not todos:
        return alvo                        # sem motor, não dá para resolver
    if alvo in todos:
        return alvo
    achados = [c for c in todos if c.startswith(alvo)]
    return achados[0] if len(achados) == 1 else ""


def card(name: str, run_dir: Path | None = None) -> Card | None:
    """Um cartão pelo nome ou abreviação."""
    return cards(run_dir).get(resolve(name, run_dir))
