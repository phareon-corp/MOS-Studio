"""Ponte SUPREM-III → MINIMOS: do perfil de processo ao dispositivo.

O desenho pede que o perfil calculado pelo SUPREM alimente a simulação de
dispositivo. O caminho natural seria o card ``PROFILE FILE=2-D``, que entrega
ao MINIMOS a matriz de dopagem binária — ``minimos.write_2d_profile`` a gera e
está coberta por teste. **Nesta compilação do MINIMOS 6.1 esse caminho aborta
dentro do motor** (``STOP *** MINIMOS ABORT ***`` logo depois de montar a
malha, sem nome de módulo no diagnóstico), e os fontes Fortran não acompanham o
binário, então não há como localizar a falha.

A ponte honesta, então, passa pelo card analítico ``PROFILE``, que funciona por
inteiro com ``MODEL=2-D``: lemos do perfil e da receita do SUPREM as grandezas
que esse card aceita — dopagem de substrato, espécie, dose e energia do
implante de fonte/dreno, temperatura e tempo do recozimento — e deixamos o
MINIMOS reconstruir o perfil a partir delas.

Isso é uma **re-simulação a partir de parâmetros**, não o transporte do perfil
ponto a ponto. A diferença é visível e não se esconde: ``Bridge.aviso`` carrega
a ressalva para a interface, e a tela do dispositivo mostra a profundidade de
junção do SUPREM ao lado da do MINIMOS para que a divergência fique medida.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .parsers import detect_junctions, junction_threshold

#: Espécies do SUPREM → símbolos que o card PROFILE do MINIMOS aceita.
ELEM = {"BORON": "B", "PHOSPHORUS": "P", "ARSENIC": "AS", "ANTIMONY": "SB"}

#: Tipo de condução de cada espécie.
TIPO = {"BORON": "p", "PHOSPHORUS": "n", "ARSENIC": "n", "ANTIMONY": "n"}

#: O que o MINIMOS assume quando a receita não diz nada.
PADRAO = {"nb": 5.2e16, "sd_elem": "AS", "sd_dose": 2.0e15, "sd_akev": 160.0,
          "anneal_c": 1050.0, "anneal_s": 2700.0, "sd_tox_nm": 50.0}


@dataclass
class Bridge:
    """Parâmetros do MINIMOS derivados de uma execução do SUPREM."""

    channel: str = "N"
    nb: float = PADRAO["nb"]
    sd_elem: str = PADRAO["sd_elem"]
    sd_dose: float = PADRAO["sd_dose"]
    sd_akev: float = PADRAO["sd_akev"]
    anneal_c: float = PADRAO["anneal_c"]
    #: Em SEGUNDOS: é a unidade do card PROFILE do MINIMOS (os exemplos do
    #: motor usam TIME=2700, isto é 45 min). A receita do SUPREM dá minutos.
    anneal_s: float = PADRAO["anneal_s"]
    vt_dose: float = 0.0
    vt_elem: str = "B"
    vt_akev: float = 50.0
    xj_suprem: float = 0.0
    origem: dict[str, str] = field(default_factory=dict)
    aviso: str = ""

    def as_params(self) -> dict[str, Any]:
        """Parte do dicionário de ``minimos.build_deck`` que a ponte define."""
        p = {"channel": self.channel, "nb": self.nb, "sd_elem": self.sd_elem,
             "sd_dose": self.sd_dose, "sd_akev": self.sd_akev,
             "anneal_c": self.anneal_c, "anneal_s": self.anneal_s,
             "gate": "NPOLY" if self.channel == "N" else "PPOLY"}
        if self.vt_dose > 0:
            p.update(vt_dose=self.vt_dose, vt_elem=self.vt_elem,
                     vt_akev=self.vt_akev)
        return p


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default


def substrate(profile: list[tuple[float, float]]) -> float:
    """Dopagem de substrato (cm⁻³) lida na cauda do perfil."""
    if not profile:
        return 0.0
    cauda = [abs(c) for _, c in profile[-5:] if c]
    if not cauda:
        return 0.0
    cauda.sort()
    return cauda[len(cauda) // 2]


def junction(profile: list[tuple[float, float]]) -> float:
    """Junção mais profunda do perfil, em µm (0 se não houver)."""
    if not profile:
        return 0.0
    js = detect_junctions(profile, min_mag=junction_threshold(profile))
    return max(js) if js else 0.0


def _normaliza(step: Any) -> dict:
    """Aceita as três formas de passo que circulam no app.

    ``Step`` (edição), ``dict`` (projeto salvo) e ``(tipo, params)`` (receitas
    da biblioteca) viram o mesmo dicionário.
    """
    if isinstance(step, dict):
        return step
    if isinstance(step, tuple) and len(step) >= 2:
        return {"type": step[0], "params": step[1] or {}}
    if hasattr(step, "as_dict"):
        return step.as_dict()
    return {"type": getattr(step, "type", ""), "params": getattr(step, "params", {})}


def derive(steps: list[dict], profile: list[tuple[float, float]] | None = None
           ) -> Bridge:
    """Monta a ponte a partir dos passos da receita e, se houver, do perfil.

    A receita manda nas espécies e nas doses, porque é o que o usuário
    escreveu; o perfil manda na dopagem de substrato e na junção, porque são
    resultado medido. Onde a receita não diz nada, ficam os padrões do MINIMOS,
    e ``origem`` registra de onde veio cada número.
    """
    b = Bridge()
    profile = profile or []
    passos = [_normaliza(s) for s in (steps or [])]

    def tipo_de(nome: str) -> str:
        return TIPO.get((nome or "").strip().upper(), "")

    # --- substrato: define o canal (n num corpo p) e NB ---
    init = next((s for s in passos if s.get("type") == "INITIALIZE"), None)
    tipo_sub = tipo_de(init.get("params", {}).get("dopant")) if init else ""
    if tipo_sub:
        b.channel = "N" if tipo_sub == "p" else "P"
        b.origem["channel"] = "substrato da receita"
    ns = substrate(profile)
    if ns > 0:
        b.nb, b.origem["nb"] = ns, "cauda do perfil do SUPREM"
    elif init:
        c = _num(init.get("params", {}).get("concentration"))
        if c > 0:
            b.nb, b.origem["nb"] = c, "INITIALIZE da receita"

    # --- fonte/dreno: o implante mais pesado de tipo oposto ao substrato ---
    implantes = [s for s in passos if s.get("type") == "IMPLANTI"]
    oposto = "n" if b.channel == "N" else "p"
    sd = [s for s in implantes if tipo_de(s.get("params", {}).get("dopant")) == oposto]
    if sd:
        melhor = max(sd, key=lambda s: _num(s.get("params", {}).get("dose")))
        pr = melhor.get("params", {})
        esp = (pr.get("dopant") or "").strip().upper()
        b.sd_elem = ELEM.get(esp, b.sd_elem)
        b.sd_dose = _num(pr.get("dose"), b.sd_dose) or b.sd_dose
        b.sd_akev = _num(pr.get("energy"), b.sd_akev) or b.sd_akev
        b.origem["sd"] = "implante de fonte/dreno da receita"

    # --- ajuste de Vt: implante do mesmo tipo do substrato, dose menor ---
    ajuste = [s for s in implantes
              if tipo_de(s.get("params", {}).get("dopant")) == tipo_sub and tipo_sub]
    if ajuste:
        pr = min(ajuste, key=lambda s: _num(s.get("params", {}).get("dose"),
                                            float("inf"))).get("params", {})
        d = _num(pr.get("dose"))
        if 0 < d < 1e14:
            b.vt_dose = d
            b.vt_elem = ELEM.get((pr.get("dopant") or "").upper(), b.vt_elem)
            b.vt_akev = _num(pr.get("energy"), b.vt_akev) or b.vt_akev
            b.origem["vt"] = "implante de ajuste da receita"

    # --- recozimento: a difusão mais longa depois do implante de fonte/dreno ---
    pos = passos.index(sd[0]) if sd else 0
    difs = [s for s in passos[pos:] if s.get("type") == "DIFFUSION"]
    if difs:
        melhor = max(difs, key=lambda s: _num(s.get("params", {}).get("time")))
        pr = melhor.get("params", {})
        b.anneal_c = _num(pr.get("temperature"), b.anneal_c) or b.anneal_c
        minutos = _num(pr.get("time"))
        if minutos > 0:
            b.anneal_s = minutos * 60.0      # minutos da receita → segundos
        b.origem["anneal"] = "difusão da receita"

    b.xj_suprem = junction(profile)
    b.aviso = ("O MINIMOS reconstrói o perfil a partir destes parâmetros; "
               "ele não recebe o perfil do SUPREM ponto a ponto.")
    # O que a receita não tem fica com o padrão do MINIMOS — e dizer isso
    # importa: um corte de porta não tem fonte nem dreno, e sem o aviso o
    # usuário veria o transistor simulado com uma fonte/dreno inventada,
    # achando que veio do processo.
    faltando = [nome for chave, nome in (("sd", "fonte e dreno"),
                                         ("vt", "ajuste de limiar"),
                                         ("anneal", "recozimento"))
                if chave not in b.origem]
    if faltando:
        b.aviso += (" A receita não traz " + ", ".join(faltando)
                    + ": esses valores são os padrões do motor.")
    return b
