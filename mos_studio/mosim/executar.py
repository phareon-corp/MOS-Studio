"""Executa um deck do MINIMOS no motor aberto e gera os arquivos de saída.

Os arquivos seguem o formato dos do MINIMOS 6.1, para que quem já lê aquelas
saídas (inclusive os leitores do MOS-Studio) leia estas sem mudança:

* ``out`` — saída formatada (unidade 16), uma página por ponto de polarização;
* ``ref`` — arquivo de referência (unidade 6), com o andamento do cálculo;
* ``iv``  — tabela I-V (unidade 61).
"""
from __future__ import annotations

import datetime
import math
import time

import numpy as np

from . import __version__, fisica
from .deck import Deck, ErroDeck, ler
from . import simular

CABECALHO = "MOSIM {v}   (motor aberto compatível com MINIMOS 6.1)"


def _pagina(n: int, titulo: str, agora: str) -> list[str]:
    return ["1",
            f"          {CABECALHO.format(v=__version__):<44s}{agora}   PAGE {n:3d}",
            f"          {titulo:<80s}",
            "0"]


def _linha(rotulo: str, valor: str, unidade: str) -> str:
    return f"                    {rotulo:<20s}= {valor} ({unidade})"


def _fmt_e(v: float) -> str:
    return f"{v:10.2E}"


def pontos_polarizacao(deck: Deck, modelo: str) -> list[dict[str, float]]:
    """Lista de pontos (US, UD, UG, UB) conforme BIAS e STEP."""
    bias = deck.todas("BIAS")
    if len(bias) != 1:
        raise ErroDeck("*BIAS* STATEMENT MUST APPEAR EXACTLY ONCE")
    b = bias[0]
    if b.num("UD") is None:
        raise ErroDeck("MISSING DATA ON *BIAS* STATEMENT")
    thres = modelo == "T"
    # com THRES o manual pede que UG seja omitido, mas o MINIMOS aceita e ignora
    if not thres and b.num("UG") is None:
        raise ErroDeck("MISSING DATA ON *BIAS* STATEMENT")
    us = b.num("US", 0.0)
    u0 = {"S": us, "D": b.num("UD"), "G": b.num("UG", 0.0) or 0.0, "B": b.num("UB", us)}
    st = deck.todas("STEP")
    if not st:
        return [u0]
    s = st[0]

    def par(dk, nk):
        d, n = s.num(dk), s.num(nk)
        if (d is None) != (n is None):
            raise ErroDeck("MISSING DATA ON *STEP* STATEMENT")
        return (d or 0.0), int(round(n or 0))

    dd, nd = par("DD", "ND")
    dg, ng = par("DG", "NG")
    db, nbk = par("DB", "NB")
    if thres and ng:
        raise ErroDeck("NUG-STEPS MUST NOT BE GIVEN WHEN THRESHOLD MODEL IS SELECTED")
    ludg = s.logico("LUDG")
    lugb = s.logico("LUGB")
    pts = []
    for ib in range(nbk + 1):
        for ig in range(ng + 1):
            for idd in range(nd + 1):
                u = dict(u0)
                u["B"] = u0["B"] + ib * db
                u["G"] = u0["G"] + ig * dg
                u["D"] = u0["D"] + idd * dd
                if ludg:
                    u["G"] = u0["G"] + ig * dg + idd * dd
                if lugb:
                    u["G"] = u["G"] + ib * db
                pts.append(u)
    return pts


def executar(texto: str, log=None, resolucao: float | None = None, dopfile=None) -> dict:
    """Roda o deck e devolve ``{"out", "ref", "iv", "returncode", "pontos"}``."""
    agora = datetime.datetime.now().strftime("%y/%m/%d  %H:%M:%S")
    ref: list[str] = []
    out: list[str] = []
    t0 = time.time()

    def rlog(s: str):
        ref.append(s)
        if log:
            log(s)

    linhas = texto.replace("\r", "").split("\n")
    titulo = linhas[0] if linhas else ""
    out += _pagina(1, titulo, agora)
    eco = []
    for l in linhas[1:]:
        if l.strip() == "":
            continue
        eco.append(f"          {l[:80]:<80s}")
        if l.strip().upper().startswith("END"):
            break
    out += eco
    ref.append(f"1          *MOSIM* REFERENCE FILE      {agora}")
    ref += [" " + e for e in eco]
    pag = 1
    try:
        deck = ler(texto)
        opt = deck.uma("OPTION")
        modelo = (opt.txt("MODEL") or "2-D")[0]
        if modelo not in ("T", "1", "2", "A"):
            raise ErroDeck(f"MODEL={opt.txt('MODEL')} ainda não é suportado pelo motor aberto "
                           "(disponíveis: THRES, 1-D, 2-D, AVAL)")
        pts = pontos_polarizacao(deck, modelo)
        m = simular.construir(deck, resolucao=resolucao, dopfile=dopfile)
    except ErroDeck as e:
        out += ["0*ERROR*    " + str(e), "0", "        1 OCCURENCE ERROR(S)"]
        ref += ["0*ERROR*    " + str(e)]
        return {"out": "\n".join(out) + "\n", "ref": "\n".join(ref) + "\n", "iv": "",
                "returncode": 1, "pontos": []}

    d = m.disp
    vt = d.vt
    s = m.sinal
    nb = max(m.nb, 1.0)
    phif = s * vt * math.log(nb / d.ni)
    cox = m.eps_ins * fisica.EPS0 / m.tins
    vfb = m.wf - phif - fisica.Q * m.nss / cox
    debye = math.sqrt(fisica.EPS_SI * fisica.EPS0 * vt / (fisica.Q * d.ni)) * 1e4
    portador = "ELECTRONS" if m.canal_n else "HOLES"
    outro = "HOLES" if m.canal_n else "ELECTRONS"
    mob_outro = fisica.Mobilidade(m.T, "p" if m.canal_n else "n")
    resultados = []
    iv = ["##     UB (V)     UD (V)     UG (V)     US (V)     IB (A)     ID (A)     IG (A)     IS (A)"]
    est = None
    rlog(f"      {time.time()-t0:5.2f} INITIAL PROCESSING")
    rlog(f"           GRID {d.nx} * {d.ny}")
    for u in pts:
        try:
            if modelo == "T":
                rlog(f"      {time.time()-t0:5.2f} THRESHOLD ITERATION  US={u['S']:6.2f} UD={u['D']:6.2f} UB={u['B']:6.2f}")
                vth, idr, est = simular.limiar(
                    m, u, est, log=lambda t: rlog("           " + t.strip()) if t.strip().startswith("limiar") else None)
                rlog(f"           THRESHOLD VOLTAGE = {vth:9.3f} (V)")
                u = dict(u, G=vth)
            elif modelo == "A":
                rlog(f"      {time.time()-t0:5.2f} ITERATION FOR MODEL = AVL  US={u['S']:6.2f} UD={u['D']:6.2f} UG={u['G']:6.2f} UB={u['B']:6.2f}")
                id2d = None
                est, e2, corr = simular.resolver_aval(
                    m, u, est, log=lambda t: rlog("           " + t.strip()) if "avalanche" in t else None)
                id2d = simular.ultima_corrente_2d(m)
                idr = corr["D"]
                vth = None
            else:
                rlog(f"      {time.time()-t0:5.2f} ITERATION FOR MODEL = 2-D  US={u['S']:6.2f} UD={u['D']:6.2f} UG={u['G']:6.2f} UB={u['B']:6.2f}")
                est, idr = simular.resolver_ponto(m, u, est)
                vth = None
            rlog(f"           DRAIN CURRENT = {idr:11.4E} (A)")
        except Exception as e:  # noqa: BLE001 — falha numérica vira erro no .out
            out += _pagina(pag + 1, "", agora)
            out += ["0*ERROR*    NO CONVERGENCE: " + str(e)]
            ref.append("0*ERROR*    " + str(e))
            return {"out": "\n".join(out) + "\n", "ref": "\n".join(ref) + "\n",
                    "iv": "\n".join(iv) + "\n", "returncode": 2, "pontos": resultados}
        pag += 1
        out += _pagina(pag, "", agora)
        out.append(_linha("SOURCE VOLTAGE", f"{u['S']:10.2f}", "V"))
        if modelo != "T":
            out.append(_linha("GATE VOLTAGE", f"{u['G']:10.2f}", "V"))
        out.append(_linha("DRAIN VOLTAGE", f"{u['D']:10.2f}", "V"))
        out.append(_linha("BULK VOLTAGE", f"{u['B']:10.2f}", "V"))
        out += ["", ""]
        out.append(_linha("FERMI BARRIER", f"{phif*1e3:10.2f}", "MV"))
        out.append(_linha("FLATBAND VOLTAGE", f"{vfb*1e3:10.2f}", "MV"))
        out.append(_linha("WORK FUNCTION", f"{m.wf*1e3:10.2f}", "MV"))
        out.append(_linha("THERMAL VOLTAGE", f"{vt*1e3:10.2f}", "MV"))
        out += ["", ""]
        out.append(_linha("OXIDE CAPACITANCE", _fmt_e(cox), "F/CM**2"))
        out.append(_linha("JUNCTION DEPTH", f"{m.xj:10.4f}", "MICRON"))
        out.append(_linha("SUBDIFFUSION", f"{m.sub:10.4f}", "MICRON"))
        out.append(_linha("DEBYE LENGTH", _fmt_e(debye), "MICRON"))
        out.append(_linha("INTRINSIC NUMBER", _fmt_e(d.ni), "CM**-3"))
        out += ["", "                    MAXIMUM MOBILITY"]
        out.append(_linha(f"FOR {portador}", _fmt_e(d.mob.mu_l), "CM**2/V/S"))
        if modelo == "A":
            out.append(_linha(f"FOR {outro}", _fmt_e(mob_outro.mu_l), "CM**2/V/S"))
        out += ["", "                    MAXIMUM DRIFT VELOCITY"]
        out.append(_linha(f"FOR {portador}", _fmt_e(d.mob.vsat), "CM/S"))
        if modelo == "A":
            out.append(_linha(f"FOR {outro}", _fmt_e(mob_outro.vsat), "CM/S"))
        out += ["", ""]
        if vth is not None:
            out.append(_linha("THRESHOLD VOLTAGE", f"{vth:10.2f}", "V"))
            out += ["", ""]
            out.append(_linha("DRAIN CURRENT", _fmt_e(idr), "A") + " MODEL=1-D")
        elif modelo == "A":
            out.append(_linha("DRAIN CURRENT", _fmt_e(id2d), "A") + " MODEL=2-D")
            out += ["", ""]
            out.append(_linha("DRAIN CURRENT", _fmt_e(idr), "A") + " MODEL=AVL")
            out.append(_linha("SOURCE CURRENT", _fmt_e(corr["S"]), "A"))
            out.append(_linha("BULK CURRENT", _fmt_e(corr["B"]), "A"))
        else:
            out.append(_linha("DRAIN CURRENT", _fmt_e(idr), "A") + " MODEL=1-D")
            out += ["", ""]
            out.append(_linha("DRAIN CURRENT", _fmt_e(idr), "A") + " MODEL=2-D")
        if modelo == "A":
            iv.append("".join(f"{v:12.3E}" for v in (u["B"], u["D"], u["G"], u["S"], corr["B"], idr,
                                                      0.0, corr["S"])))
            resultados.append(dict(u, ID=idr, IB=corr["B"], IS=corr["S"], VTH=None))
        else:
            iv.append("".join(f"{v:12.3E}" for v in (u["B"], u["D"], u["G"], u["S"], 0.0, idr, 0.0, -idr)))
            resultados.append(dict(u, ID=idr, VTH=vth))
    tra_txt = None
    if deck.todas("TRANSIENT"):
        from . import transiente
        rlog(f"      {time.time()-t0:5.2f} TRANSIENT SIMULATION")
        try:
            regs = transiente.simular(m, deck, pts[0], log=lambda t: rlog("          " + t.strip()))
        except ErroDeck as e:
            out += ["0*ERROR*    " + str(e)]
            ref.append("0*ERROR*    " + str(e))
            return {"out": "\n".join(out) + "\n", "ref": "\n".join(ref) + "\n",
                    "iv": "\n".join(iv) + "\n", "returncode": 1, "pontos": resultados}
        tra_txt = transiente.tra(regs)
        T = regs[-1]["t"] - regs[0]["t"] or 1.0
        ref.append("")
        ref.append(" MEAN VALUES ACROSS THE TOTAL SIMULATION TIME:")
        ref.append("")
        ref.append("             IBM        IDM        IGM        ISM        SUM")
        for tipo in ("ele", "hol", "dis"):
            # média no tempo (Euler implícito: cada corrente vale no intervalo que termina nela)
            med = {c: sum(regs[k][tipo][c] * (regs[k]["t"] - regs[k - 1]["t"])
                          for k in range(1, len(regs))) / T for c in "SGDB"}
            ref.append(f"       {tipo.upper()} " + "".join(f"{med[c]:11.3E}" for c in "BDGS")
                       + f"{sum(med.values()):11.3E}")
    rlog(f"      {time.time()-t0:5.2f} OUTPUT PROCESSING")
    saida = deck.uma("OUTPUT")
    pif = _pif(m, est) if saida.logico("PIF") and est is not None else None
    return {"out": "\n".join(out) + "\n", "ref": "\n".join(ref) + "\n",
            "iv": "\n".join(iv) + "\n", "returncode": 0, "pontos": resultados,
            "pif": pif, "tra": tra_txt}


def _pif(m, est) -> str:
    """PIF ASCII no formato do MINIMOS (grade tensorial do silício e campos)."""
    d = m.disp
    vt = d.vt
    s = m.sinal
    j0 = d.j0
    x = d.geo.x * 1e4
    y = d.geo.y[j0:] * 1e4
    ny, nx = d.ny, d.nx
    psi = (est.psi * vt).reshape(ny, nx)
    n = (est.n * d.ni).reshape(ny, nx)[j0:]
    C = d.C.reshape(ny, nx)[j0:]
    p = np.exp(np.clip(m.est["U"]["B"] / vt - psi[j0:] / vt, -700, 700)) * d.ni
    ps = psi[j0:]
    ex = -np.gradient(ps, x * 1e-4, axis=1)
    ey = -np.gradient(ps, y * 1e-4, axis=0)
    campos = {
        "NetDopingConcentration": s * C,
        "ElectrostaticPotential": s * ps,
        "SpaceChargeConcentration": s * (p - n + C),
        "ElectricField": np.hypot(ex, ey),
        "ElectricFieldLateral": s * ex,
        "ElectricFieldVertical": s * ey,
        "ElectronConcentration" if m.canal_n else "HoleConcentration": n,
    }
    L = [" (PIF Minimos_Output_1    ",
         "  (grid Gr_1    ", "    (pointList GrP_1    ", "      (orthoProduct",
         "        (axes                                                 ;  lat vert",
         "          (valueType real)",
         '          (units "um")',
         "          (valueList                                               ; vert"]
    L += [f"            {v: .6E}" for v in y]
    L += ["          )", "          (valueList                                               ;  lat"]
    L += [f"            {v: .6E}" for v in x]
    L += ["          )))))", ""]
    for nome, a in campos.items():
        L += [f"  (attribute {nome}_1    ", "    (valueType real)",
              f"    (nameList (ref GrP_1))                             ; {nx*len(y):5d}",
              "    (valueList                                                 ;  lat vert"]
        L += [f"      {v: .6E}" for v in np.asarray(a).ravel()]
        L += ["    ))", ""]
    L.append(")")
    return "\n".join(L) + "\n"
