"""Leitura de decks no formato de entrada do MINIMOS 6.1.

Sintaxe (manual do MINIMOS, cap. 3): a primeira linha é o título; cada
diretiva tem chaves ``CHAVE=VALOR`` separadas por branco, vírgula ou
asterisco; ``+`` na coluna 1 continua a diretiva anterior; ``*`` inicia
comentário até o fim da linha; contam as 80 primeiras colunas. Diretivas e
chaves podem ser abreviadas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DIRETIVAS = [
    "BIAS", "DEVICE", "END", "FIMPLANT", "GEOMETRY", "GRID", "IMPLANT",
    "INTERFACE", "MOBILITY", "MONTE-CARLO", "OPTION", "OUTPUT", "PROFILE",
    "RECOMBINATION", "STEP", "TRANSIENT",
]

CHAVES = {
    "BIAS": ["JCAP", "UB", "UD", "UG", "US", "VI", "VR"],
    "DEVICE": ["BULK", "CHANNEL", "DGAP", "E1", "E2", "FILM", "GATE", "INS",
               "KBULK", "L", "MAT", "SGAP", "TINS", "W", "XLEFT", "XRIGHT",
               "YDEPTH", "C1", "C2"],
    "STEP": ["DB", "DD", "DG", "DS", "C1", "C2", "E1", "E2", "ELOG", "LUDG",
             "LUGB", "NB", "NC", "ND", "NE", "NG", "NS", "VG"],
    "PROFILE": ["ACTIVATION", "AKEV", "ASYM", "CA", "CD", "C1", "C2", "DMOFF",
                "DOSE", "EA", "ED", "ELEM", "FILE", "LD", "LFIT", "NB", "NS",
                "SMOFF", "SUBS", "TEMP", "TIME", "TOX", "XOFF", "YOFF", "VAGD",
                "VAGS", "VAGX", "VAUD", "VDEN", "VDGD", "VDGS", "VDGX", "VDUD"],
    "IMPLANT": ["ACTIVATION", "AKEV", "DOSE", "ELEM", "LD", "TEMP", "TIME"],
    "INTERFACE": ["CISS", "NRD", "NRE", "NRS", "NSS", "SISS", "XISS", "PSS",
                  "PNSS", "FSS", "PFSS", "MENERG", "AUUD", "DUUD"],
    "OPTION": ["ACCELERATION", "CCLP", "CP", "CURRENT", "EA", "ED", "GCHCALC",
               "GRIDFREEZE", "IDEALITY", "INTRINSIC", "LCPUMP", "LDRAIN",
               "LSOURCE", "LVDMOSFET", "MODEL", "MPOLY", "M3MODE", "OMEGA",
               "PDOP", "PHYSCK", "RBULK", "RDRAIN", "RSOURCE", "TEMP", "UFB",
               "UN", "UP"],
    "OUTPUT": ["ALL", "AS", "AVAL", "BI", "CC", "DC", "DIGITS", "ELAT", "ETRAN",
               "IV", "JLAT", "JTRAN", "MAJ", "MIN", "MOB", "MTV", "NONE", "OXIDE",
               "PHI", "PIF", "PSI", "RHO", "STRIPS", "TC"],
    "END": ["BIN", "CAPERR", "CACCREL", "ERROR", "NAC", "NCYCLES", "NGEN",
            "NHOT", "NUPDATES", "PACCREL", "TCERR"],
    "MOBILITY": ["MB", "MC", "MI", "ML", "MQ", "MR", "MS", "MT", "MV"],
    "GRID": ["DGMI", "DJRX", "DJRY", "DOPX", "DOPY", "DOPZ", "DPXC", "DPXD",
             "DPXP", "DPYC", "DPYD", "DPYP", "DPZ", "DP1D", "DX1", "DX2", "DX3",
             "DY", "DZ", "GFILL", "GGMI", "MXTUN", "MYTUN", "PGMI", "SXTUN",
             "SYTUN", "XE1", "XE2", "XE3", "XS1", "XS2", "XS3", "YE", "YS",
             "ZE", "ZS"],
}


class ErroDeck(ValueError):
    """Deck inválido (mensagem no estilo das do MINIMOS)."""


@dataclass
class Diretiva:
    nome: str
    chaves: dict[str, str] = field(default_factory=dict)
    texto: str = ""
    ordem: list[str] = field(default_factory=list)

    def num(self, chave: str, padrao: float | None = None) -> float | None:
        v = self.chaves.get(chave)
        if v is None or v == "":
            return padrao
        try:
            return float(v.replace("D", "E").replace("d", "e"))
        except ValueError as e:
            raise ErroDeck(f"valor numérico inválido em {self.nome}: {chave}={v}") from e

    def txt(self, chave: str, padrao: str | None = None) -> str | None:
        v = self.chaves.get(chave)
        return padrao if v in (None, "") else v.upper()

    def logico(self, chave: str, padrao: bool = False) -> bool:
        v = self.chaves.get(chave)
        if v in (None, ""):
            return padrao
        return v.upper().startswith("Y")

    def __contains__(self, chave: str) -> bool:
        return chave in self.chaves


@dataclass
class Deck:
    titulo: str
    diretivas: list[Diretiva]
    linhas: list[str]

    def todas(self, nome: str) -> list[Diretiva]:
        return [d for d in self.diretivas if d.nome == nome]

    def uma(self, nome: str) -> Diretiva:
        """Primeira diretiva com esse nome (vazia se não houver)."""
        for d in self.diretivas:
            if d.nome == nome:
                return d
        return Diretiva(nome)


def _resolve(palavra: str, opcoes: list[str], onde: str) -> str:
    p = palavra.upper()
    if p in opcoes:
        return p
    # maior prefixo comum; empate entre opções = ambiguidade
    melhor, n_melhor, empate = None, 0, False
    for o in opcoes:
        n = 0
        while n < min(len(o), len(p)) and o[n] == p[n]:
            n += 1
        if n == 0:
            continue
        if n > n_melhor:
            melhor, n_melhor, empate = o, n, False
        elif n == n_melhor:
            empate = True
    if melhor is None:
        raise ErroDeck(f"chave desconhecida em {onde}: {palavra}")
    if empate:
        # prefere a opção que começa com a palavra inteira (abreviação legítima)
        inteiras = [o for o in opcoes if o.startswith(p)]
        if len(inteiras) == 1:
            return inteiras[0]
        if not inteiras:
            cands = [o for o in opcoes if o[:n_melhor] == p[:n_melhor]]
            return sorted(cands, key=len)[0]
        raise ErroDeck(f"abreviação ambígua em {onde}: {palavra}")
    return melhor


_TOK = re.compile(r"([A-Za-z][A-Za-z0-9\-]*)\s*=\s*([^\s,=]*)")


def ler(texto: str) -> Deck:
    linhas = texto.replace("\r", "").split("\n")
    if not linhas or not linhas[0].strip():
        # o MINIMOS exige a linha de título; aceitamos vazia
        pass
    titulo = linhas[0][:80] if linhas else ""
    blocos: list[list[str]] = []
    for bruta in linhas[1:]:
        l = bruta.expandtabs()[:80]   # o manual diz 72, mas o MINIMOS 6.1 lê até 80
        if l.startswith("+"):
            if not blocos:
                raise ErroDeck("linha de continuação sem diretiva")
            corpo = l[1:].split("*", 1)[0]
            blocos[-1].append(corpo)
            continue
        if not l.strip() or l.lstrip().startswith("*"):
            continue
        blocos.append([l.split("*", 1)[0]])
    diretivas: list[Diretiva] = []
    for bloco in blocos:
        texto_d = " ".join(bloco).strip()
        if not texto_d:
            continue
        nome_bruto, _, resto = texto_d.partition(" ")
        nome_bruto = nome_bruto.split(",")[0]
        try:
            nome = _resolve(nome_bruto, DIRETIVAS, "diretivas")
        except ErroDeck as e:
            raise ErroDeck(f"diretiva desconhecida: {nome_bruto}") from e
        d = Diretiva(nome, texto=texto_d)
        resto = resto.replace("=", " = ").replace(",", " ")
        resto = re.sub(r"\s*=\s*", "=", resto)
        for chave, valor in _TOK.findall(resto):
            opcoes = CHAVES.get(nome)
            k = _resolve(chave, opcoes, nome) if opcoes else chave.upper()
            d.chaves[k] = valor
            d.ordem.append(k)
        diretivas.append(d)
        if nome == "END":
            break
    if not any(d.nome == "END" for d in diretivas):
        raise ErroDeck("falta a diretiva END")
    return Deck(titulo=titulo, diretivas=diretivas, linhas=linhas)
