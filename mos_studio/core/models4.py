"""Os modelos físicos da tela de Modelos, com os valores reais do motor.

Cada grupo aqui é uma aba da tela: um cartão do deck, uma escolha opcional
(espécie, ambiente, estado) e a lista de parâmetros editáveis. O valor que
aparece em cada campo é o que o motor vai usar de fato, resolvido em duas
camadas por :func:`effective`:

1. ``data/modelrc``, que o motor lê antes de qualquer deck (:mod:`modelrc`);
2. o padrão compilado na gramática, em ``data/suprem.key`` (:mod:`keyfile`),
   para o que o ``modelrc`` não menciona.

A ordem importa porque as duas discordam com frequência: o ``suprem.key``
declara ``interstitial D.0 = 1e-9`` e o ``modelrc`` sobrescreve com ``1.03e6``
— quinze ordens de grandeza. Mostrar o primeiro seria mostrar um número que
nunca é usado.

Só o que o usuário alterar entra no deck (:func:`cards`). Os demais parâmetros
ficam de fora de propósito: repetir o padrão no deck não muda nada e esconderia
qual foi a decisão do projeto.

Correções em relação ao mockup, todas conferidas contra ``suprem.key``:

* **não existe cartão ``impurity``.** O cartão é o nome da espécie —
  ``arsenic silicon Dix.0=…``. Um deck com ``impurity arsenic …`` cai no
  ``/bin/sh``, porque o shell do SUPREM-IV entrega cabeçalho desconhecido ao
  sistema (ver :func:`suprem4.unknown_cards`).
* **``erfc``/``vertical``/``compress``/``viscous`` são do cartão ``method``**,
  não do ``oxide``; o padrão do motor é ``vertical``. O que o cartão ``oxide``
  seleciona é o ambiente (``dry``/``wet``) e a orientação.
* **``rel.err``/``abs.err`` são por impureza.** O ``modelrc`` dá ``abs.err``
  = 1e5 para defeitos e 1e9 para dopantes; um valor único para a aba toda
  estaria errado para metade dos casos.
* **o cartão ``trap`` tem ``total``, não ``total.0``/``total.E``.**
* **fósforo não tem ``Fi``.** Ele difunde pelo par com vacância (``Dvx``,
  ``Dvm``), e um ``phosphorus … Fi=0.92`` é recusado. Por isso a lista de
  parâmetros de cada espécie vem do cartão, não de uma lista fixa.
* os coeficientes do mockup eram inventados (arsênio ``Dix.0=8.0`` contra
  ``0.0666`` reais, interstícios ``D.0=3650`` contra ``1.03e6``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import keyfile, modelrc

#: Orientação do substrato usada pelos coeficientes de oxidação. É a mesma
#: que o cartão ``initialize`` da receita usa; mudar uma sem a outra faria a
#: tela mostrar coeficientes de um plano e o motor crescer óxido pelo de outro.
ORIENTATION = "100"

#: Material padrão dos grupos que pedem um. Toda a tela trabalha no silício;
#: os outros materiais existem no motor mas não nos fluxos da interface.
MATERIAL = "silicon"

#: Unidade e significado, em português, dos parâmetros que a tela mostra.
#: O ``suprem.key`` traz um texto único (``"Activation energy for Vo
#: diffusivity - eV"``) que mistura os dois; esta tabela só separa e traduz —
#: nenhum número vem daqui.
LABELS: dict[str, tuple[str, str]] = {
    "Dix.0": ("cm²/s", "Par com defeito neutro, pré-fator"),
    "Dix.E": ("eV", "Par neutro, energia de ativação"),
    "Dim.0": ("cm²/s", "Par com defeito negativo, pré-fator"),
    "Dim.E": ("eV", "Par negativo, energia de ativação"),
    "Dimm.0": ("cm²/s", "Par duplamente negativo, pré-fator"),
    "Dimm.E": ("eV", "Par duplamente negativo, ativação"),
    "Dip.0": ("cm²/s", "Par com defeito positivo, pré-fator"),
    "Dip.E": ("eV", "Par positivo, energia de ativação"),
    "Dvx.0": ("cm²/s", "Par com vacância neutra, pré-fator"),
    "Dvx.E": ("eV", "Par com vacância neutra, ativação"),
    "Dvm.0": ("cm²/s", "Par com vacância negativa, pré-fator"),
    "Dvm.E": ("eV", "Par com vacância negativa, ativação"),
    "Fi": ("—", "Fração que difunde pelo mecanismo intersticial"),
    "Ctn.0": ("—", "Log do pré-fator de agregação"),
    "Ctn.E": ("eV", "Agregação, energia de ativação"),
    "Seg.0": ("—", "Segregação na interface, pré-fator"),
    "Seg.E": ("eV", "Segregação, energia de ativação"),
    "ss.conc": ("cm⁻³", "Solubilidade sólida"),
    "ss.temp": ("°C", "Temperatura da solubilidade tabelada"),
    "D.0": ("cm²/s", "Difusividade do defeito, pré-fator"),
    "D.E": ("eV", "Difusividade, energia de ativação"),
    "Cstar.0": ("cm⁻³", "Concentração de equilíbrio, pré-fator"),
    "Cstar.E": ("eV", "Equilíbrio, energia de ativação"),
    "Kr.0": ("cm³/s", "Recombinação par a par no volume, pré-fator"),
    "Kr.E": ("eV", "Recombinação no volume, ativação"),
    "Ksurf.0": ("cm/s", "Recombinação na superfície, pré-fator"),
    "Ksurf.E": ("eV", "Recombinação na superfície, ativação"),
    "total": ("cm⁻³", "Densidade total de armadilhas"),
    "frac.0": ("—", "Fração ocupada em equilíbrio, pré-fator"),
    "frac.E": ("eV", "Fração ocupada, energia de ativação"),
    "lin.l.0": ("µm/min", "Taxa linear B/A abaixo do joelho, pré-fator"),
    "lin.l.e": ("eV", "Taxa linear baixa, ativação"),
    "lin.h.0": ("µm/min", "Taxa linear B/A acima do joelho, pré-fator"),
    "lin.h.e": ("eV", "Taxa linear alta, ativação"),
    "par.l.0": ("µm²/min", "Taxa parabólica B abaixo do joelho, pré-fator"),
    "par.l.e": ("eV", "Taxa parabólica baixa, ativação"),
    "par.h.0": ("µm²/min", "Taxa parabólica B acima do joelho, pré-fator"),
    "par.h.e": ("eV", "Taxa parabólica alta, ativação"),
    "l.break": ("°C", "Joelho da taxa linear"),
    "p.break": ("°C", "Joelho da taxa parabólica"),
    "thinox.0": ("µm/min", "Regime fino, pré-fator"),
    "thinox.e": ("eV", "Regime fino, ativação"),
    "thinox.l": ("µm", "Comprimento de decaimento do regime fino"),
    "ori.fac": ("—", "Fator que escala B/A de ⟨111⟩ para esta orientação"),
    "rel.error": ("—", "Erro relativo aceito no passo de tempo"),
    "abs.error": ("cm⁻³", "Erro absoluto abaixo do qual não se refina"),
    "init.time": ("min", "Primeiro passo de tempo"),
    "min.freq": ("—", "Frequência de refatoração da matriz"),
}


@dataclass(frozen=True)
class Choice:
    """Uma opção da fileira de escolha (as pastilhas do mockup)."""

    id: str
    label: str


@dataclass(frozen=True)
class Switch:
    """Um grupo de opções mutuamente exclusivas de um cartão.

    No ``suprem.key`` isso é um ``switch nome = N { boolean a; … }``: só uma
    opção pode estar ligada, e o ``N`` diz qual o motor liga sozinho. A opção
    escolhida entra no deck como palavra solta — ``method full.cpl``.
    """

    name: str
    label: str
    options: tuple[Choice, ...]
    note: str = ""


@dataclass(frozen=True)
class Group:
    """Uma aba da tela de Modelos."""

    id: str
    label: str
    card: str
    title: str
    desc: str
    #: Nomes dos parâmetros editáveis. Vazio significa "todos os numéricos do
    #: cartão", que é o caso das espécies: a lista muda de uma para outra.
    params: tuple[str, ...] = ()
    choice_label: str = ""
    choices: tuple[Choice, ...] = ()
    note: str = ""
    #: ``True`` quando a escolha também é o nome do cartão (as espécies).
    choice_is_card: bool = False
    #: ``True`` quando a escolha entra como qualificador do cartão.
    choice_is_qualifier: bool = False
    #: ``True`` quando o cartão precisa do material como qualificador.
    needs_material: bool = True
    #: Qualificadores completos de parâmetros que fogem da regra do grupo.
    #: Quando um parâmetro aparece aqui, esta lista substitui a do grupo; o
    #: token ``"{escolha}"`` é trocado pela escolha ativa da aba.
    #:
    #: Existe por causa do cartão ``oxide``, em que o escopo muda de um
    #: coeficiente para outro: o regime fino é tabelado por orientação (e o
    #: motor recusa ``thinox.0`` sem ela), as taxas linear e parabólica são
    #: guardadas uma única vez por ambiente, e o fator de orientação não
    #: depende do ambiente nenhum.
    param_quals: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Switches do cartão cujas opções a aba oferece (ver :class:`Switch`).
    switches: tuple["Switch", ...] = ()
    #: Booleano solto que a aba liga e desliga (``trap silicon enable=false``).
    toggle: str = ""
    toggle_label: str = ""
    toggle_note: str = ""

    def default_choice(self) -> str:
        return self.choices[0].id if self.choices else ""


#: As espécies que a aba de impurezas oferece. São os quatro dopantes dos
#: exemplos de fábrica; o motor tem mais de vinte cartões de espécie.
SPECIES = (Choice("arsenic", "Arsênio"), Choice("boron", "Boro"),
           Choice("phosphorus", "Fósforo"), Choice("antimony", "Antimônio"))

GROUPS: tuple[Group, ...] = (
    Group(
        id="imp", label="Impurezas", card="", title="Difusão de impurezas",
        desc="Difusividade por espécie e por estado de carga do defeito "
             "com que a impureza forma par: D = D.0 · exp(−D.E / kT).",
        choice_label="Espécie", choices=SPECIES, choice_is_card=True,
        note="Cada espécie tem seu próprio conjunto: o fósforo difunde pelo "
             "par com vacância (Dvx, Dvm) e não aceita Fi.",
    ),
    Group(
        id="method", label="Método", card="method",
        title="Método de difusão",
        desc="Define o acoplamento entre impurezas e defeitos pontuais, e a "
             "tolerância do passo de tempo. Quanto mais completo, mais lento.",
        params=("rel.error", "abs.error"),
        choice_label="Equação",
        choices=(Choice("interstitial", "Interstícios"),
                 Choice("vacancies", "Vacâncias"),
                 Choice("arsenic", "Arsênio"), Choice("boron", "Boro"),
                 Choice("phosphorus", "Fósforo"),
                 Choice("antimony", "Antimônio")),
        choice_is_qualifier=True, needs_material=False,
        note="A tolerância é por equação resolvida: o modelrc pede 1e5 cm⁻³ "
             "para defeitos e 1e9 para dopantes.",
        switches=(
            Switch("defectm", "Acoplamento com defeitos",
                   (Choice("fermi", "Fermi"), Choice("two.dim", "Two.dim"),
                    Choice("steady", "Steady"),
                    Choice("full.cpl", "Full.cpl")),
                   "Fermi ignora os defeitos pontuais e é o padrão do motor; "
                   "Full.cpl resolve impurezas, interstícios e vacâncias "
                   "acoplados, e é bem mais lento."),
            Switch("oxidem", "Movimento do óxido",
                   (Choice("erfc", "Erfc"), Choice("erf1", "Erf1"),
                    Choice("erf2", "Erf2"), Choice("erfg", "Erfg"),
                    Choice("vertical", "Vertical"),
                    Choice("compress", "Compress"),
                    Choice("viscous", "Viscous")),
                   "Erfc e as variantes erf são analíticas e rápidas; "
                   "Compress e Viscous resolvem o escoamento do óxido e "
                   "desenham o bico de pássaro. O modelrc liga Vertical."),
        ),
    ),
    Group(
        id="ox", label="Óxido", card="oxide", title="Crescimento de óxido",
        desc="Coeficientes de Deal–Grove do ambiente escolhido. Em 2-D é o "
             "que define a forma do bico de pássaro sob a máscara.",
        params=("lin.l.0", "lin.l.e", "lin.h.0", "lin.h.e", "l.break",
                "par.l.0", "par.l.e", "par.h.0", "par.h.e", "p.break",
                "thinox.0", "thinox.e", "thinox.l", "ori.fac"),
        choice_label="Ambiente",
        choices=(Choice("dry", "O₂ seco"), Choice("wet", "H₂O")),
        choice_is_qualifier=True, needs_material=False,
        param_quals={
            "thinox.0": ("{escolha}", f"orient={ORIENTATION}"),
            "thinox.e": ("{escolha}", f"orient={ORIENTATION}"),
            "thinox.l": ("{escolha}", f"orient={ORIENTATION}"),
            "ori.fac": (f"orient={ORIENTATION}",),
        },
        note="O motor guarda as taxas linear e parabólica para ⟨111⟩ e as "
             f"escala para ⟨{ORIENTATION}⟩ pelo fator de orientação. Só o "
             "regime fino é tabelado orientação por orientação — e sem ela o "
             "motor recusa o coeficiente.",
    ),
    Group(
        id="int", label="Interstícios", card="interstitial",
        title="Interstícios de silício",
        desc="Difusão, recombinação e concentração de equilíbrio dos "
             "interstícios. São eles que produzem a difusão assistida por "
             "oxidação (OED).",
        params=("D.0", "D.E", "Cstar.0", "Cstar.E", "Kr.0", "Kr.E",
                "Ksurf.0", "Ksurf.E"),
    ),
    Group(
        id="vac", label="Vacâncias", card="vacancy", title="Vacâncias",
        desc="Os mesmos parâmetros do outro defeito pontual. Vacâncias e "
             "interstícios se recombinam no volume pela taxa Kr.",
        params=("D.0", "D.E", "Cstar.0", "Cstar.E", "Kr.0", "Kr.E"),
    ),
    Group(
        id="trap", label="Armadilhas", card="trap",
        title="Armadilhas de interstícios",
        desc="Sítios que capturam interstícios e atrasam a difusão "
             "transiente logo após o implante.",
        params=("total", "frac.0", "frac.E"),
        toggle="enable", toggle_label="Armadilhas ativadas",
        toggle_note="No silício o modelrc já as liga. Desligar vira "
                    "enable=false no deck — o motor recusa ^enable.",
    ),
)


def group(gid: str) -> Group | None:
    return next((g for g in GROUPS if g.id == gid), None)


def card_name(g: Group, choice: str) -> str:
    """Nome do cartão deste grupo com esta escolha."""
    return choice if g.choice_is_card else g.card


def qualifiers(g: Group, choice: str, param: str = "") -> tuple[str, ...]:
    """Qualificadores que identificam esta linha do ``modelrc``.

    Com ``param``, respeita a exceção declarada em
    :attr:`Group.param_quals` para aquele parâmetro.
    """
    especial = g.param_quals.get(param)
    if especial is not None:
        q = [choice if x == "{escolha}" else x for x in especial]
    else:
        q = []
        if g.choice_is_qualifier and choice:
            q.append(choice)
        if g.needs_material:
            q.append(MATERIAL)
    return tuple(_canon_qual(g, choice, x) for x in q)


def _canon_qual(g: Group, choice: str, q: str) -> str:
    """Qualificador no nome que o motor conhece.

    Os nomes de parâmetro do motor são truncados em onze caracteres (ver
    :data:`keyfile.MAX_PARAM`), e ``interstitial`` é um deles: a opção da aba
    de Método se chama ``interstitial`` na gramática, mas o deck tem de dizer
    ``interstitia``, senão o motor responde "parameter interstitial does not
    exist for this command".
    """
    if "=" in q:
        return q
    kc = keyfile.card(card_name(g, choice))
    p = kc.get(q) if kc else None
    return p.name if p is not None and p.flag else q


@dataclass
class Row:
    """Uma linha da tabela da tela: parâmetro, valor, unidade, significado."""

    name: str
    value: str
    unit: str
    meaning: str
    #: Valor padrão do motor, para o botão de restaurar e para saber se mudou.
    default: str = ""
    #: ``"modelrc"`` ou ``"suprem.key"`` — de onde o padrão veio.
    source: str = ""

    @property
    def changed(self) -> bool:
        return self.value.strip() != self.default.strip()


def effective(card: str, key: str, *quals: str,
              run_dir: Path | None = None) -> tuple[str, str]:
    """Valor que o motor usa para ``key``, e de qual arquivo ele veio.

    Devolve ``(valor, origem)`` com origem ``"modelrc"`` ou ``"suprem.key"``.
    """
    v = modelrc.lookup(card, key, *quals, run_dir=run_dir)
    if v is not None:
        return (v, "modelrc")
    kc = keyfile.card(card, run_dir)
    p = kc.get(key) if kc else None
    return ((p.default if p else ""), "suprem.key" if p else "")


def param_names(g: Group, choice: str,
                run_dir: Path | None = None) -> tuple[str, ...]:
    """Parâmetros que a aba mostra.

    Com ``params`` vazio, a lista vem do cartão — é o caso das espécies, em
    que arsênio tem ``Dim``, boro tem ``Dip`` e fósforo tem ``Dvx``/``Dvm``.
    Mesmo com a lista explícita, um nome que o cartão não declara é descartado,
    para a tela nunca oferecer um campo que o motor recusaria.
    """
    kc = keyfile.card(card_name(g, choice), run_dir)
    if kc is None:
        return g.params
    if g.params:
        return tuple(kc.canon(n) for n in g.params if kc.get(n))
    conhecidos = [p.name for p in kc.numbers() if p.name in LABELS]
    return tuple(conhecidos)


def rows(g: Group, choice: str, overrides: dict[str, str] | None = None,
         run_dir: Path | None = None) -> list[Row]:
    """A tabela da aba, já com os valores alterados pelo usuário aplicados."""
    ov = overrides or {}
    card = card_name(g, choice)
    out: list[Row] = []
    for nome in param_names(g, choice, run_dir):
        quals = qualifiers(g, choice, nome)
        padrao, origem = effective(card, nome, *quals, run_dir=run_dir)
        chave = key_of(g, choice, nome)
        if not padrao.strip() and chave not in ov:
            # Parâmetro que nem o modelrc nem a gramática definem para esta
            # combinação. Não é omissão: no O2 seco o joelho da taxa está em
            # 0 °C, então o ramo de baixa temperatura nunca é usado e não tem
            # coeficiente. Um campo vazio só convidaria a gerar ``lin.l.0=``.
            continue
        unidade, sentido = LABELS.get(nome, ("", ""))
        if not sentido:
            kc = keyfile.card(card, run_dir)
            p = kc.get(nome) if kc else None
            sentido = p.units if p else ""
        out.append(Row(name=nome, value=ov.get(chave, padrao),
                       unit=unidade, meaning=sentido,
                       default=padrao, source=origem))
    return out


def key_of(g: Group, choice: str, param: str) -> str:
    """Chave de um valor alterado, estável entre sessões."""
    return f"{g.id}|{choice or '_'}|{param}"


def engine_switch(g: Group, sw: Switch, choice: str = "",
                  run_dir: Path | None = None) -> str:
    """Opção que o motor liga sozinho neste switch.

    Vale a mesma ordem dos números: o ``modelrc`` primeiro, a gramática
    depois. A diferença aparece no movimento do óxido — o ``suprem.key``
    declara ``erfc`` como padrão do switch, mas o ``modelrc`` escreve
    ``vert``, então o que o motor usa é ``vertical``.
    """
    card = card_name(g, choice)
    kc = keyfile.card(card, run_dir)
    if kc is None:
        return sw.options[0].id if sw.options else ""
    validas = {p.name for p in kc.flags(sw.name)}
    escolhida = ""
    for r in modelrc.records(run_dir):
        if (keyfile.resolve(r.card, run_dir) or r.card) != kc.name:
            continue
        for q in r.qualifiers:
            p = kc.get(q)
            if p is not None and p.name in validas:
                escolhida = p.name
    return escolhida or kc.switch_default(sw.name)


def engine_toggle(g: Group, choice: str = "",
                  run_dir: Path | None = None) -> bool:
    """Estado em que o motor deixa o booleano solto da aba."""
    if not g.toggle:
        return False
    card = card_name(g, choice)
    kc = keyfile.card(card, run_dir)
    nome = kc.canon(g.toggle) if kc else g.toggle
    estado = False
    for r in modelrc.records(run_dir):
        if kc is not None and (keyfile.resolve(r.card, run_dir)
                               or r.card) != kc.name:
            continue
        if not r.matches(*qualifiers(g, choice),
                         canon=(lambda q: (kc.canon(q) if kc else q))):
            continue
        for q in r.qualifiers:
            if (kc.canon(q) if kc else q) == nome:
                estado = True
        for k, v in r.values.items():
            if (kc.canon(k) if kc else k) == nome:
                estado = v.strip().lower() not in ("f", "false", "0")
    if estado:
        return True
    p = kc.get(nome) if kc else None
    return bool(p and p.default.strip().lower() in ("t", "true", "1"))


@dataclass
class Models4:
    """O que o projeto mudou nos modelos físicos.

    Guarda só as alterações. Um projeto sem alterações não emite cartão
    nenhum e roda com o ``modelrc`` da instalação — que é o que se quer na
    maioria dos casos.
    """

    #: Parâmetros numéricos alterados, por :func:`key_of`.
    overrides: dict[str, str] = field(default_factory=dict)
    #: Opção escolhida em cada switch, por ``"grupo|switch"``.
    switches: dict[str, str] = field(default_factory=dict)
    #: Estado escolhido para o booleano solto de cada aba, por ``"grupo|opção"``.
    toggles: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Só as alterações, para o arquivo de projeto."""
        return {"valores": dict(self.overrides),
                "switches": dict(self.switches),
                "booleanos": {k: bool(v) for k, v in self.toggles.items()}}

    @classmethod
    def from_dict(cls, dados: dict | None) -> "Models4":
        """Alterações lidas do projeto."""
        d = dados or {}
        return cls(
            overrides={str(k): str(v)
                       for k, v in (d.get("valores") or {}).items()},
            switches={str(k): str(v)
                      for k, v in (d.get("switches") or {}).items()},
            toggles={str(k): bool(v)
                     for k, v in (d.get("booleanos") or {}).items()})

    def set(self, g: Group, choice: str, param: str, value: str) -> None:
        """Registra um valor; igual ao padrão, remove a alteração."""
        k = key_of(g, choice, param)
        padrao, _ = effective(card_name(g, choice), param,
                              *qualifiers(g, choice, param))
        if value.strip() in ("", padrao.strip()):
            self.overrides.pop(k, None)
        else:
            self.overrides[k] = value.strip()

    def switch(self, g: Group, sw: Switch, choice: str = "") -> str:
        """Opção ativa no switch: a do usuário, ou a do motor."""
        return self.switches.get(f"{g.id}|{sw.name}") or engine_switch(
            g, sw, choice)

    def set_switch(self, g: Group, sw: Switch, option: str,
                   choice: str = "") -> None:
        """Escolhe uma opção; igual à do motor, deixa de ser uma alteração."""
        k = f"{g.id}|{sw.name}"
        if option == engine_switch(g, sw, choice):
            self.switches.pop(k, None)
        else:
            self.switches[k] = option

    def toggle(self, g: Group, choice: str = "") -> bool:
        """Estado do booleano solto da aba."""
        k = f"{g.id}|{choice or '_'}"
        if k in self.toggles:
            return self.toggles[k]
        return engine_toggle(g, choice)

    def set_toggle(self, g: Group, state: bool, choice: str = "") -> None:
        k = f"{g.id}|{choice or '_'}"
        if state == engine_toggle(g, choice):
            self.toggles.pop(k, None)
        else:
            self.toggles[k] = state

    def reset(self, g: Group, choice: str) -> None:
        """Restaura os padrões do motor nesta aba."""
        prefixo = f"{g.id}|{choice or '_'}|"
        for k in [k for k in self.overrides if k.startswith(prefixo)]:
            del self.overrides[k]
        for sw in g.switches:
            self.switches.pop(f"{g.id}|{sw.name}", None)
        self.toggles.pop(f"{g.id}|{choice or '_'}", None)

    def reset_all(self) -> None:
        self.overrides.clear()
        self.switches.clear()
        self.toggles.clear()

    def changed(self, g: Group, choice: str) -> list[str]:
        prefixo = f"{g.id}|{choice or '_'}|"
        return [k.split("|", 2)[2] for k in self.overrides
                if k.startswith(prefixo)]

    def count(self) -> int:
        return len(self.overrides) + len(self.switches) + len(self.toggles)

    def cards(self, run_dir: Path | None = None) -> list[str]:
        """Os cartões do deck — um por grupo e escolha com alteração.

        Cada linha junta todos os parâmetros alterados daquela combinação,
        como o motor espera: ``arsenic silicon Dix.0=0.1 Dix.E=3.5``.
        """
        # Por linha do deck, as atribuições indexadas pelo parâmetro: um
        # parâmetro cujo escopo ignora a escolha da aba (o ``ori.fac`` do
        # óxido, que não depende do ambiente) chega aqui uma vez por escolha
        # e precisa sair uma vez só.
        por_linha: dict[tuple[str, tuple[str, ...]], dict[str, str]] = {}
        for k, v in self.overrides.items():
            gid, choice, param = k.split("|", 2)
            g = group(gid)
            if g is None:
                continue
            escolha = "" if choice == "_" else choice
            if param not in param_names(g, escolha, run_dir):
                continue            # alteração órfã: parâmetro não existe mais
            chave = (card_name(g, escolha), qualifiers(g, escolha, param))
            por_linha.setdefault(chave, {})[param] = f"{param}={v}"
        # Switches e booleanos entram na mesma linha do cartão a que pertencem.
        for k, opcao in self.switches.items():
            gid, _, nome = k.partition("|")
            g = group(gid)
            sw = next((x for x in g.switches if x.name == nome), None) if g else None
            if g is None or sw is None:
                continue
            # Um switch vale para a execução inteira, não para a equação
            # selecionada na aba: ``method full.cpl``, nunca
            # ``method interstitial full.cpl``, que restringiria o modelo a
            # uma equação só.
            chave = (card_name(g, g.default_choice()),
                     (MATERIAL,) if g.needs_material else ())
            por_linha.setdefault(chave, {})[sw.name] = opcao
        for k, estado in self.toggles.items():
            gid, _, choice = k.partition("|")
            g = group(gid)
            if g is None or not g.toggle:
                continue
            escolha = "" if choice == "_" else choice
            chave = (card_name(g, escolha), qualifiers(g, escolha))
            por_linha.setdefault(chave, {})[g.toggle] = (
                g.toggle if estado else f"{g.toggle}=false")
        saida: list[str] = []
        for (card, quals), atribs in por_linha.items():
            saida.append(" ".join([card, *quals, *sorted(atribs.values())]))
        return sorted(saida)
