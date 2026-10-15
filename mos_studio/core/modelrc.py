"""Leitura do ``modelrc``, o arquivo de coeficientes que o motor carrega.

Os valores padrão dos modelos físicos não são escolha do MOS-Studio: estão em
``suprem4-run/data/modelrc``, que o ``main.c`` lê antes de qualquer deck. Ler
dali — em vez de manter uma tabela aqui — é o que garante que a tela de
Modelos mostre o que o motor vai de fato usar, mesmo que o arquivo seja
trocado ou editado.

Formato de cada linha útil::

    <cartão> <qualificadores…> chave=valor chave =valor …   [;]

Os qualificadores são posicionais e sem nome (``arsenic silicon``,
``oxide dry orient=111``), espaços e tabulações se misturam, o ``=`` pode ter
espaço de um lado, e algumas linhas terminam em ponto e vírgula. Comentários
começam com ``#``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: Uma atribuição ``chave=valor``, tolerando espaço antes e depois do ``=``.
_ASSIGN = re.compile(r"([A-Za-z_][\w.]*)\s*=\s*(\S+)")


@dataclass
class Record:
    """Uma linha do ``modelrc``."""

    card: str
    qualifiers: list[str] = field(default_factory=list)
    values: dict[str, str] = field(default_factory=dict)

    def matches(self, *qualifiers: str, canon=None) -> bool:
        """``True`` se todos os qualificadores pedidos estão nesta linha.

        Um qualificador pode vir como palavra solta (``dry``, ``silicon``) ou
        como seletor ``chave=valor`` (``orient=111``). O segundo caso existe
        porque o cartão ``oxide`` escolhe a orientação assim, e não por uma
        opção booleana — ``oxide dry orient=111 lin.h.0=…`` e a linha para
        ``orient=100`` convivem no arquivo.

        ``canon`` canoniza as palavras soltas; é por ele que o ``vacan`` do
        arquivo responde a uma consulta por ``vacancies``.
        """
        norm = canon or (lambda q: q)
        meus = {norm(q).lower() for q in self.qualifiers}
        for q in qualifiers:
            if not q:
                continue
            if "=" in q:
                k, _, v = q.partition("=")
                atual = self.values.get(k.strip())
                if atual is None:
                    for kk, vv in self.values.items():
                        if kk.lower() == k.strip().lower():
                            atual = vv
                            break
                if atual is None or atual.strip() != v.strip():
                    return False
            elif norm(q).lower() not in meus:
                return False
        return True


def parse(text: str) -> list[Record]:
    """Todas as linhas de atribuição do arquivo, na ordem."""
    saida: list[Record] = []
    for linha in text.splitlines():
        linha = linha.split("#", 1)[0].strip().rstrip(";").strip()
        if not linha:
            continue
        valores = {m.group(1): m.group(2) for m in _ASSIGN.finditer(linha)}
        # Os qualificadores são o que sobra depois de tirar as atribuições.
        resto = _ASSIGN.sub(" ", linha).split()
        if not resto:
            continue
        card, *quals = resto
        if not valores and not quals:
            continue
        saida.append(Record(card.lower(), [q.lower() for q in quals], valores))
    return saida


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> tuple[Record, ...]:
    """Cache por caminho e data de modificação, para reler se o arquivo mudar."""
    del mtime           # só participa da chave do cache
    try:
        return tuple(parse(Path(path).read_text(encoding="latin1",
                                                errors="replace")))
    except OSError:
        return ()


def records(run_dir: Path | None = None) -> list[Record]:
    """Linhas do ``modelrc`` da instalação, ou ``[]`` se não houver motor."""
    from . import suprem4

    rd = Path(run_dir) if run_dir else suprem4.find_run_dir()
    if rd is None:
        return []
    arquivo = Path(rd) / "data" / "modelrc"
    try:
        mtime = arquivo.stat().st_mtime
    except OSError:
        return []
    return list(_load(str(arquivo), mtime))


def lookup(card: str, key: str, *qualifiers: str,
           run_dir: Path | None = None) -> str | None:
    """Valor padrão de ``key`` no cartão ``card`` com esses qualificadores.

    Devolve a **última** ocorrência, que é a que vale: o motor lê o arquivo de
    cima para baixo e cada linha sobrescreve a anterior.
    """
    from . import keyfile

    achado: str | None = None
    # O arquivo abrevia tanto o cartão (``interst`` por ``interstitial``)
    # quanto o parâmetro (``rel.err`` por ``rel.error``). A comparação é feita
    # sobre o nome canônico dos dois lados, resolvido pelo ``suprem.key``.
    canon = keyfile.resolve(card, run_dir) or card.lower()
    kc = keyfile.card(canon, run_dir)
    alvo = (kc.canon(key) if kc else key).lower()

    @lru_cache(maxsize=None)
    def flag(nome: str) -> str:
        """Nome canônico de uma opção booleana do cartão."""
        if kc is None:
            return nome
        p = kc.get(nome)
        return p.name if p is not None and p.flag else nome

    for r in records(run_dir):
        if (keyfile.resolve(r.card, run_dir) or r.card) != canon:
            continue
        if not r.matches(*qualifiers, canon=flag):
            continue
        for k, v in r.values.items():
            nome = (kc.canon(k) if kc else k).lower()
            if nome == alvo:
                achado = v
    return achado


def defaults(card: str, keys: list[str], *qualifiers: str,
             run_dir: Path | None = None) -> dict[str, str]:
    """Vários padrões de uma vez, para montar um formulário."""
    return {k: (lookup(card, k, *qualifiers, run_dir=run_dir) or "")
            for k in keys}
