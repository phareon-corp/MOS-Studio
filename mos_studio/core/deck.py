"""Geração e leitura do deck de entrada do SUPREM-III (arquivos ``.IN``).

Movido de ``suprem3.py`` sem mudança de lógica: o motor é sensível a coluna,
abreviação e continuação, e qualquer ajuste aqui muda o resultado da simulação.
As únicas mudanças são de forma — tipos, documentação e nomes públicos.

Nota sobre PLOT: o comando continua sendo *gerado e lido* aqui, para que um
deck legado com PLOT ainda faça a viagem de ida e volta. O que saiu é a oferta
de PLOT no catálogo de etapas da interface (ver :mod:`mos_studio.core.recipe`),
porque a biblioteca gráfica desta compilação é um conjunto de stubs vazios e
:func:`strip_plot` apaga o comando antes de executar.
"""

from __future__ import annotations

import re
from typing import Any

StepDict = dict[str, Any]

AMBIENTS = ["DRYO2", "WETO2", "NITROGEN", "BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY"]
DOPANTS = ["BORON", "PHOSPHOR", "ARSENIC", "ANTIMONY", "BF2"]
MATERIALS = ["SILICON", "OXIDE", "NITRIDE", "ALUMINUM", "POLYSILI"]

_SUPREM_DOPANTS = ["Boron", "Phosphorus", "Arsenic", "Antimony"]


def step_to_code(step: StepDict) -> str:
    """Traduz uma etapa (``{"type":..., "params":...}``) para a linha do deck."""
    t, p = step["type"], step["params"]
    if t == "INITIALIZE":
        s = f"INITIALIZE SILICON <{p.get('orientation','100')}>"
        if p.get("dopant"):
            s += f" {p['dopant']} CONCENTR={p.get('concentration','1E15')}"
        s += f" DX={p.get('dx','5E-3')}\n+ THICKNES={p.get('thickness','0.5')}"
        return s
    if t == "DIFFUSION":
        s = f"DIFFUSION {p['ambient']} TEMPERAT={p['temperature']} TIME={p['time']}"
        if p.get("gasConc"):
            s += f" GAS.CONC={p['gasConc']}"
        if p.get("solidSol"):
            s += " SOLIDSOL"
        if p.get("tRate"):
            s += f" T.RATE={p['tRate']}"
        return s
    if t == "DEPOSITION":
        s = f"DEPOSITION {p['material']} THICKNES={p['thickness']}"
        if p.get("dopant"):
            s += f" {p['dopant']}"
        if p.get("concentration"):
            s += f" CONCENTR={p['concentration']}"
        if p.get("temperature"):
            s += f" TEMPERAT={p['temperature']}"
        return s
    if t == "ETCH":
        return f"ETCH {p['material']}" + (
            "" if p.get("all") else f" THICKNES={p.get('thickness','')}")
    if t == "IMPLANTI":
        s = f"IMPLANTI {p['dopant']} ENERGY={p['energy']} DOSE={p['dose']}"
        if p.get("distribution"):
            s += f" {p['distribution']}"
        return s
    if t == "EPITAXY":
        s = f"EPITAXY {p['dopant']} THICKNES={p['thickness']} CONCENTR={p['concentration']}"
        s += f"\n+TEMPERAT={p['temperature']} GROWTH.R={p.get('growthRate','0.5')}"
        return s
    if t == "PRINT":
        s = f"PRINT {p.get('what','NET')}"
        if p.get("curve"):
            s += f" {p['curve']}"
        if p.get("extra"):
            s += f" {p['extra']}"
        if p.get("filename"):
            s += f" FILENAME={p['filename']}"
        if p.get("linespa"):
            s += f" LINES/PA={p['linespa']}"
        return s
    if t == "PLOT":
        s = f"PLOT {p.get('what','NET')} {p.get('curve','ACTIVE')}"
        if p.get("xmax"):
            s += f" XMAX={p['xmax']}"
        if p.get("cmin"):
            s += f" CMIN={p['cmin']}"
        if p.get("cmax"):
            s += f" CMAX={p['cmax']}"
        return s
    return ""


def build_in_file(title: str, steps: list[StepDict]) -> str:
    """Monta o deck completo (``TITLE`` … ``STOP``) com fim de linha CRLF."""
    lines = [f"TITLE {title}"]
    for step in steps:
        c = step_to_code(step)
        if c:
            lines.append(c)
    lines.append("STOP")
    text = "\r\n".join(lines) + "\r\n"
    # Normalizar: qualquer \n sozinho vira \r\n (corrige continuações multi-linha)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return text


def dopants_in_steps(steps: list[StepDict]) -> list[str]:
    """Detecta quais dopantes aparecem no processo (para imprimir o perfil deles)."""
    found = []
    blob = " ".join(str(v) for s in steps
                    for v in (s.get("params", {}) or {}).values()).upper()
    for d in _SUPREM_DOPANTS:
        if d.upper()[:5] in blob or d.upper() in blob:
            found.append(d)
    return found


def build_profile_deck(title: str, steps: list[StepDict]) -> tuple[str, list[tuple[str, str]]]:
    """Monta um deck inserindo ``PRINT`` após CADA etapa de processo.

    Serve para capturar a evolução do perfil. Devolve ``(texto, plano)``, em que
    ``plano`` é a lista ordenada de ``(rótulo_da_etapa, grandeza)``
    correspondente a cada bloco ``depth concentration`` que sairá no OUTPUT — na
    mesma ordem.
    """
    dopants = dopants_in_steps(steps) or ["Boron", "Phosphorus"]
    proc = {"INITIALIZE", "DIFFUSION", "IMPLANTI", "DEPOSITION", "ETCH", "EPITAXY"}
    lines = [f"TITLE {title}"]
    plan: list[tuple[str, str]] = []
    n = 0
    nice = {"INITIALIZE": "Substrato", "DIFFUSION": "Difusão", "IMPLANTI": "Implante",
            "DEPOSITION": "Deposição", "ETCH": "Corrosão", "EPITAXY": "Epitaxia"}
    for step in steps:
        t = (step.get("type") or "").upper()
        if t in ("PRINT", "PLOT", "STOP"):
            continue                              # ignoramos prints do usuário aqui
        code = step_to_code(step)
        if not code:
            continue
        lines.append(code)
        if t in proc:
            n += 1
            pr = step.get("params", {}) or {}
            extra = ""
            if t == "DIFFUSION" and pr.get("ambient"):
                extra = f" {pr['ambient']}"
            elif t == "IMPLANTI" and pr.get("dopant"):
                extra = f" {pr['dopant']}"
            label = f"{n}. {nice.get(t, t.capitalize())}{extra}"
            lines.append("PRINT Net Active Concentration")
            plan.append((label, "Net"))
            for d in dopants:
                lines.append(f"PRINT {d} Chemical Concentration")
                plan.append((label, d))
    lines.append("STOP")
    text = "\r\n".join(lines).replace("\r\n", "\n").replace("\n", "\r\n") + "\r\n"
    return text, plan


def ensure_profile_print(deck: str) -> str:
    """Garante que o deck produza a tabela de perfil (profundidade x concentração).

    Se nenhum ``PRINT`` com ``CONCENTRATION`` existir, injeta
    ``Print Net Chemical Concentration`` antes do ``STOP``. O PRINT do usuário
    (ex.: ``Print Layer``, com as junções) é preservado — apenas se acrescenta
    o perfil.
    """
    lines = deck.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    has_conc = False
    for ln in lines:
        u = ln.upper()
        if u.lstrip().startswith("PRINT") and ("CONCENTR" in u):
            has_conc = True
            break
    if has_conc:
        return deck
    out, inserted = [], False
    for ln in lines:
        if not inserted and ln.strip().upper().startswith("STOP"):
            out.append("Print Net Chemical Concentration")
            inserted = True
        out.append(ln)
    if not inserted:
        out.append("Print Net Chemical Concentration")
        out.append("Stop")
    return "\n".join(out)


def strip_plot(in_content: str) -> str:
    """Remove comandos ``PLOT`` (e suas continuações ``+``) do deck.

    A biblioteca gráfica desta compilação do SUPREM-III é um conjunto de stubs
    vazios; no backend DOSBox, PLOT travava a execução headless. A visualização
    é feita pelo próprio MOS-Studio a partir das tabelas dos ``.OUT``.
    """
    out_lines = []
    skipping = False
    for raw in in_content.replace("\r\n", "\n").split("\n"):
        stripped = raw.strip()
        if skipping and stripped.startswith("+"):
            continue  # continuação de um PLOT removido
        skipping = stripped.upper().startswith("PLOT")
        if skipping:
            continue
        out_lines.append(raw)
    text = "\n".join(out_lines)
    return text.replace("\n", "\r\n")


def deck_title(deck: str, fallback: str = "simulacao") -> str:
    """Lê o texto do ``TITLE`` de um deck."""
    for line in deck.replace("\r\n", "\n").split("\n"):
        lt = line.strip()
        if lt.lower().startswith("title"):
            t = lt[5:].strip()
            if t:
                return t
            break
    return fallback


def parse_in_file(text: str) -> tuple[str, list[StepDict]]:
    """Lê um deck ``.IN`` e devolve ``(título, etapas)``.

    Aceita o dialeto Stanford (``DEPOSIT``, ``IMPLANT``, ``EPITAXI``),
    abreviações de parâmetro nos dois sentidos e continuações com ``+``.
    """
    steps: list[StepDict] = []
    title = "SIMULACAO"
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    joined: list[str] = []
    for line in raw:
        t = line.strip()
        if not t or t.startswith("$") or t.upper().startswith("COMMENT"):
            continue
        if t.startswith("+"):
            if joined:
                joined[-1] += " " + t[1:].strip()
        else:
            joined.append(t)

    def gp(tokens, key):
        # casa KEY=valor aceitando abreviacao nos DOIS sentidos
        # (CONCENTRATION= casa com CONCENTR, e vice-versa). Minimo 4 chars.
        K = key.upper()
        for t in tokens:
            if "=" not in t:
                continue
            k, _, v = t.partition("=")
            ku = k.upper()
            n = min(len(ku), len(K))
            if n >= 4 and (ku.startswith(K[:n]) and K.startswith(ku[:n])):
                return v
        return ""

    def has(tokens, key):
        return any(t.upper() == key.upper() for t in tokens)

    def _alias(tok, name):
        # prefixo em qualquer sentido, minimo 3 chars (BF2 tem 3)
        a, b = tok.upper(), name.upper()
        n = min(len(a), len(b))
        return n >= 3 and a[:n] == b[:n]

    def fin(tokens, lst):
        for t in tokens:
            for x in lst:
                if _alias(t, x):
                    return x.upper()
        return ""

    def ori(tokens):
        for t in tokens:
            m = re.match(r"<(\d+)>", t)
            if m:
                return m.group(1)
        return "100"

    # aliases de comando: dialeto Stanford -> tipo interno do Studio
    CMD_ALIAS = {"DEPOSIT": "DEPOSITION", "DEPOSITION": "DEPOSITION",
                 "IMPLANT": "IMPLANTI", "IMPLANTI": "IMPLANTI",
                 "INITIALIZE": "INITIALIZE", "DIFFUSION": "DIFFUSION",
                 "ETCH": "ETCH", "EPITAXY": "EPITAXY", "EPITAXI": "EPITAXY",
                 "PRINT": "PRINT", "PLOT": "PLOT", "TITLE": "TITLE", "STOP": "STOP"}

    for line in joined:
        tokens = line.split()
        if not tokens:
            continue
        raw_cmd = tokens[0].upper()
        cmd = CMD_ALIAS.get(raw_cmd, raw_cmd)
        rest = tokens[1:]
        if cmd == "TITLE":
            title = " ".join(rest)
        elif cmd == "INITIALIZE":
            steps.append({"type": "INITIALIZE", "params": {
                "orientation": ori(rest), "dopant": fin(rest, DOPANTS),
                "concentration": gp(rest, "CONCENTRATION") or "1E15",
                "dx": gp(rest, "DX") or "5E-3",
                "thickness": gp(rest, "THICKNESS") or "0.5"}})
        elif cmd == "DIFFUSION":
            gc = gp(rest, "GAS.CONC") or gp(rest, "GAS.CON")
            steps.append({"type": "DIFFUSION", "params": {
                "ambient": fin(rest, AMBIENTS),
                "temperature": gp(rest, "TEMPERATURE") or "1000",
                "time": gp(rest, "TIME") or "15", "gasConc": gc,
                "solidSol": has(rest, "SOLIDSOL") or has(rest, "SOLIDSOLUBILITY"),
                "tRate": gp(rest, "T.RATE")}})
        elif cmd == "DEPOSITION":
            steps.append({"type": "DEPOSITION", "params": {
                "material": fin(rest, MATERIALS) or "OXIDE",
                "thickness": gp(rest, "THICKNESS") or "0.1",
                "dopant": fin(rest, DOPANTS),
                "concentration": gp(rest, "CONCENTRATION"),
                "temperature": gp(rest, "TEMPERATURE")}})
        elif cmd == "ETCH":
            steps.append({"type": "ETCH", "params": {
                "material": fin(rest, MATERIALS) or "OXIDE",
                "all": has(rest, "ALL") or not gp(rest, "THICKNESS"),
                "thickness": gp(rest, "THICKNESS")}})
        elif cmd == "IMPLANTI":
            steps.append({"type": "IMPLANTI", "params": {
                "dopant": fin(rest, DOPANTS) or "BORON",
                "energy": gp(rest, "ENERGY") or "45",
                "dose": gp(rest, "DOSE") or "1E13",
                "distribution": fin(rest, ["GAUSSIAN", "PEARSON", "BOLTZMAN",
                                           "2-GAUSSI"])}})
        elif cmd == "EPITAXY":
            steps.append({"type": "EPITAXY", "params": {
                "dopant": fin(rest, DOPANTS) or "PHOSPHOR",
                "thickness": gp(rest, "THICKNESS") or "1.0",
                "concentration": gp(rest, "CONCENTRATION") or "5E15",
                "temperature": gp(rest, "TEMPERATURE") or "1000",
                "growthRate": gp(rest, "GROWTH.R") or "0.5"}})
        elif cmd == "PRINT":
            steps.append({"type": "PRINT", "params": {
                "what": fin(rest, ["NET", "BORON", "PHOSPHOR", "ARSENIC",
                                   "ANTIMONY", "ALL", "OXIDE"]) or "NET",
                "curve": fin(rest, ["ACTIVE", "CHEMICAL"]),
                "extra": fin(rest, ["CONCENTR", "LAYER", "IMPURITY", "MATERIAL",
                                    "OXIDATIO"]),
                "filename": gp(rest, "FILENAME") or "OUTPUT.OUT",
                "linespa": gp(rest, "LINES/PA")}})
        elif cmd == "PLOT":
            steps.append({"type": "PLOT", "params": {
                "what": fin(rest, ["NET", "BORON", "PHOSPHOR", "ARSENIC",
                                   "ANTIMONY", "TOTAL"]) or "NET",
                "curve": fin(rest, ["ACTIVE", "CHEMICAL"]) or "ACTIVE",
                "xmax": gp(rest, "XMAX"), "cmin": gp(rest, "CMIN"),
                "cmax": gp(rest, "CMAX")}})
        elif cmd == "STOP":
            break
    return title, steps


def annotated_lines(title: str, steps: list[StepDict]) -> list[tuple[str, int | None]]:
    """As linhas do deck, cada uma com o ``uid`` da etapa que a originou.

    Serve para a interface ligar linha do deck ↔ etapa da receita (clicar numa
    linha seleciona a etapa). O texto resultante é idêntico ao de
    :func:`build_in_file` — há um teste que garante isso —, por isso esta
    função não substitui o gerador: ela o acompanha.
    """
    out: list[tuple[str, int | None]] = [(f"TITLE {title}", None)]
    for step in steps:
        code = step_to_code(step)
        if not code:
            continue
        uid = step.get("uid")
        for line in code.replace("\r\n", "\n").split("\n"):
            out.append((line, uid))
    out.append(("STOP", None))
    return out
