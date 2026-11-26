"""Tela de Dispositivo: do perfil de processo ao transistor, no MINIMOS.

A ponte com o SUPREM é a razão de ser desta tela, e ela não finge mais do que
faz: o MINIMOS **reconstrói** o perfil a partir dos parâmetros que
:mod:`mos_studio.core.bridge` extrai da receita e do perfil medido — ele não
recebe o perfil ponto a ponto. O painel da ponte mostra de onde veio cada
número e põe a junção do SUPREM ao lado da do MINIMOS, para que a diferença
fique medida em vez de suposta.

Três modos de corrida, todos do próprio motor: limiar (``MODEL=THRES``), curva
I-V (``MODEL=2-D`` com varredura ``STEP``) e ponto de operação com mapas 2-D
(``MODEL=2-D`` com PIF).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QScrollArea, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from ...core import bridge as bridge_mod
from ...core import importar_minimos, minimos, parsers
from ...core.recipe import Field, fmt_number, parse_float
from .. import theme
from ..widgets.common import (Segmented, button, eyebrow, hline, label, row,
                              stretch)
from ..widgets.deck_view import DeckPanel
from ..widgets.device_plots import FieldMap, IVChart, SurfacePlot
from ..widgets.error_panel import EngineErrorPanel

#: Os três modos que o motor oferece, com o nome que o usuário lê.
MODOS = [("vth", "Limiar"), ("iv", "Curva I-V"), ("op", "Mapas 2-D")]

#: A física da corrida: o modelo 2-D (deriva-difusão dos minoritários) ou o
#: AVAL (os dois portadores, recombinação e ionização por impacto, com a
#: corrente de substrato). O limiar é sempre o modelo do próprio limiar.
FISICA = [("2d", "Deriva-difusão"), ("aval", "Com avalanche")]

#: Campos do transistor (geometria e porta).
CAMPOS_DISP = [
    Field("tox_nm", "Óxido de porta", "number", unit="nm", minimum=1,
          help="Espessura do óxido sob a porta."),
    Field("w_um", "Largura do canal", "number", unit="µm", minimum=0.01),
    Field("l_um", "Comprimento do canal", "number", unit="µm", minimum=0.1,
          help="Abaixo de ~0,3 µm o motor costuma não convergir."),
]

#: Campos de polarização.
CAMPOS_BIAS = [
    Field("ud", "Tensão de dreno", "number", unit="V",
          help="O MODEL=2-D não aceita dreno em zero; o app usa 0,1 V no "
               "lugar."),
    Field("ug", "Tensão de porta", "number", unit="V"),
    Field("step", "Passo da varredura", "number", unit="V"),
    Field("nstep", "Número de passos", "number", unit="",
          minimum=1, maximum=200),
]


class _InstallWorker(QThread):
    """Instala o MINIMOS do zip fora da interface (no Linux compila)."""

    done = Signal(str)
    failed = Signal(str)

    def __init__(self, zip_path: str, parent=None) -> None:
        super().__init__(parent)
        self._zip = zip_path

    def run(self) -> None:          # noqa: D102 - API do QThread
        try:
            self.done.emit(str(importar_minimos.importar(self._zip)))
        except importar_minimos.ErroMinimos as exc:
            self.failed.emit(str(exc))
        except OSError as exc:
            self.failed.emit(f"Erro de arquivo: {exc}")


class _RunWorker(QThread):
    """Roda o motor de dispositivo (MINIMOS ou o aberto) fora da interface."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, deck: str, motor: str, parent=None, dopfile=None) -> None:
        super().__init__(parent)
        self._deck = deck
        self._motor = motor
        self._dopfile = dopfile

    def run(self) -> None:          # noqa: D102 - API do QThread
        import threading
        pronto = threading.Event()
        caixa: dict = {}
        try:
            minimos.run_motor(self._deck, base="mos_studio", motor=self._motor,
                              dopfile=self._dopfile,
                              callback_done=lambda r: (caixa.update(r), pronto.set()),
                              callback_error=lambda e: (caixa.update(erro=e),
                                                        pronto.set()))
        except RuntimeError as exc:
            self.failed.emit(str(exc))
            return
        # o motor aberto pode levar alguns minutos numa varredura longa
        if not pronto.wait(3600):
            caixa["erro"] = "o motor não terminou em uma hora"
        if caixa.get("erro"):
            self.failed.emit(str(caixa["erro"]))
        else:
            self.done.emit(caixa)


class DeviceScreen(QWidget):
    """A tela inteira de Dispositivo."""

    run_started = Signal()
    run_finished = Signal(object)
    motor_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.params = {"tox_nm": "15", "w_um": "1.0", "l_um": "0.85",
                       "ud": "0.1", "ug": "0", "step": "0.15", "nstep": "20",
                       "channel": "N", "gate": "NPOLY", "mode": "iv",
                       "step_var": "DG"}
        self.bridge: bridge_mod.Bridge | None = None
        self.result: dict | None = None
        self._worker: _RunWorker | None = None
        self._profile: list[tuple[float, float]] = []
        self._steps: list = []
        self._rows: dict[str, object] = {}

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(theme.dimension("border"))
        raiz.addWidget(self._splitter)
        self._splitter.addWidget(self._build_params())
        self._splitter.addWidget(self._build_center())
        self._splitter.setSizes([theme.dimension("sidebar-width"), 760])
        self._splitter.setStretchFactor(1, 1)
        self._refresh_engine()
        self._refresh_bridge()

    # ── painel esquerdo ───────────────────────────────────────────────────

    def _build_params(self) -> QWidget:
        painel = QWidget()
        theme.mark(painel, surface="sidebar")
        painel.setMinimumWidth(theme.dimension("sidebar-width")
                               - theme.space("20"))
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        cabeca = QWidget()
        hl = QVBoxLayout(cabeca)
        hl.setContentsMargins(theme.space("8"), theme.space("8"),
                              theme.space("8"), theme.space("6"))
        hl.setSpacing(theme.space("3"))
        self._eyebrow_motor = eyebrow("dispositivo", True)
        hl.addWidget(self._eyebrow_motor)
        hl.addWidget(label("Dispositivo", "title"))
        lay.addWidget(cabeca)
        lay.addWidget(hline())

        corpo = QWidget()
        cl = QVBoxLayout(corpo)
        cl.setContentsMargins(theme.space("8"), theme.space("7"),
                              theme.space("8"), theme.space("7"))
        cl.setSpacing(theme.space("7"))

        # --- a ponte ---
        cl.addWidget(eyebrow("vindo do processo"))
        self._ponte_corpo = QWidget()
        theme.mark(self._ponte_corpo, surface="raised")
        self._pl = QVBoxLayout(self._ponte_corpo)
        self._pl.setContentsMargins(theme.space("6"), theme.space("5"),
                                    theme.space("6"), theme.space("5"))
        self._pl.setSpacing(theme.space("3"))
        cl.addWidget(self._ponte_corpo)
        # Simular sem passar pelo processo: um deck próprio, ou um resultado
        # do MINIMOS guardado de outra sessão.
        cl.addWidget(row(
            button("Abrir deck .inp…", "small",
                   tooltip="Simula este deck como está, ignorando os campos",
                   on_click=self.import_deck),
            button("Abrir resultado…", "small",
                   tooltip="Mostra os mapas e a curva de uma execução já "
                           "feita, sem rodar o motor",
                   on_click=self.import_result),
            stretch(), spacing="3"))
        cl.addWidget(hline())

        # --- transistor ---
        cl.addWidget(eyebrow("transistor"))
        cl.addWidget(self._seg_row("Canal", "channel",
                                   [("N", "NMOS"), ("P", "PMOS")]))
        cl.addWidget(self._seg_row("Porta", "gate",
                                   [("NPOLY", "Poli n"), ("PPOLY", "Poli p"),
                                    ("AL", "Alumínio")]))
        for campo in CAMPOS_DISP:
            cl.addWidget(self._field(campo))
        cl.addWidget(hline())

        # --- polarização ---
        cl.addWidget(eyebrow("polarização"))
        cl.addWidget(self._seg_row("Modo", "mode", MODOS))
        self._seg_fisica = self._seg_row("Física", "fisica", FISICA)
        self._seg_fisica.setToolTip(
            "Com avalanche: elétrons e lacunas, recombinação e ionização por "
            "impacto — dá a corrente de substrato (IB) e o efeito de corpo "
            "flutuante. Mais lento que a deriva-difusão.")
        cl.addWidget(self._seg_fisica)
        self._seg_var = self._seg_row("Varrer", "step_var",
                                      [("DG", "Porta"), ("DD", "Dreno")])
        cl.addWidget(self._seg_var)
        for campo in CAMPOS_BIAS:
            cl.addWidget(self._field(campo))
        cl.addStretch(1)

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        rolagem.setWidget(corpo)
        lay.addWidget(rolagem, 1)

        lay.addWidget(hline())
        self._seg_motor = Segmented(
            [(minimos.MOTOR_MINIMOS, "MINIMOS 6.1"),
             (minimos.MOTOR_ABERTO, "Aberto (MOSIM)")],
            minimos.motor_escolhido())
        self._seg_motor.setToolTip(
            "MINIMOS: o original da TU Wien, se você o instalou. Aberto: o "
            "simulador do MOS-Studio, que lê os mesmos decks e segue os "
            "modelos do manual do MINIMOS 6.")
        self._seg_motor.changed.connect(self._on_motor)
        self._motor = label("", wrap=True)
        self._motor.setFont(theme.font("mono", "micro"))
        theme.mark(self._motor, role="muted")
        rodape = QWidget()
        rl = QVBoxLayout(rodape)
        rl.setContentsMargins(theme.space("8"), theme.space("5"),
                              theme.space("8"), theme.space("5"))
        rl.setSpacing(theme.space("4"))
        rl.addWidget(self._seg_motor)
        rl.addWidget(self._motor)
        self._btn_instalar = button(
            "Instalar MINIMOS a partir do .zip…",
            tooltip="Aponte para o minimoswin6.1.zip da TU Wien. No Windows "
                    "o motor é copiado; no Linux, compilado do fonte.",
            on_click=self.install_engine)
        self._btn_instalar.setVisible(False)
        self._install_worker: _InstallWorker | None = None
        rl.addWidget(self._btn_instalar)
        acoes = QWidget()
        al = QHBoxLayout(acoes)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(theme.space("4"))
        self._btn_run = button("Simular dispositivo", "primary",
                               on_click=self.run)
        self._btn_run.setFixedHeight(theme.dimension("button-lg"))
        al.addWidget(self._btn_run, 1)
        rl.addWidget(acoes)
        lay.addWidget(rodape)
        self._update_mode_visibility()
        return painel

    def _field(self, campo: Field) -> QWidget:
        from ..widgets.step_form import FieldRow
        fr = FieldRow(campo, self.params.get(campo.key, ""))
        fr.changed.connect(self._on_param)
        self._rows[campo.key] = fr
        return fr

    def _seg_row(self, titulo: str, chave: str,
                 opcoes: list[tuple[str, str]]) -> QWidget:
        cab = label(titulo)
        cab.setFont(theme.font("sans", "base", "medium"))
        seg = Segmented(opcoes, self.params.get(chave, ""))
        seg.changed.connect(lambda _i, c=chave, s=seg:
                            self._on_param(c, s.value()))
        self._rows[chave] = seg
        host = QWidget()
        vl = QVBoxLayout(host)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(theme.space("4"))
        vl.addWidget(cab)
        vl.addWidget(seg)
        return host

    # ── centro ────────────────────────────────────────────────────────────

    def _build_center(self) -> QWidget:
        painel = QWidget()
        lay = QVBoxLayout(painel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.erro = EngineErrorPanel()
        lay.addWidget(self.erro)

        metricas = QWidget()
        theme.mark(metricas, surface="raised")
        ml = QHBoxLayout(metricas)
        ml.setContentsMargins(theme.space("10"), theme.space("8"),
                              theme.space("10"), theme.space("8"))
        ml.setSpacing(theme.space("10"))
        self._metricas: dict[str, object] = {}
        for chave, titulo, unidade in (("vt", "Limiar", "V"),
                                       ("id", "ID máx", "A"),
                                       ("nb", "Substrato", "cm⁻³"),
                                       ("xj", "Junção (SUPREM)", "µm"),
                                       ("ib", "IB máx", "A")):
            bloco = QWidget()
            bl = QVBoxLayout(bloco)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(theme.space("2"))
            bl.addWidget(eyebrow(titulo))
            valor = label("—", "metric")
            bl.addWidget(valor)
            bl.addWidget(label(unidade, "unit"))
            ml.addWidget(bloco)
            self._metricas[chave] = valor
            if chave == "ib":
                self._bloco_ib = bloco
                bloco.setVisible(False)
        ml.addStretch(1)
        lay.addWidget(metricas)
        lay.addWidget(hline())

        self.abas = QTabWidget()
        self.abas.setDocumentMode(True)
        self.iv = IVChart()
        self.abas.addTab(self.iv, "Curva I-V")
        self.mapa_host = QWidget()
        mh = QVBoxLayout(self.mapa_host)
        mh.setContentsMargins(0, 0, 0, 0)
        mh.setSpacing(0)
        barra = QWidget()
        bl = QHBoxLayout(barra)
        bl.setContentsMargins(theme.space("8"), theme.space("4"),
                              theme.space("8"), theme.space("4"))
        bl.setSpacing(theme.space("4"))
        bl.addWidget(eyebrow("campo"))
        self._seg_campo = Segmented([], "")
        bl.addWidget(self._seg_campo, 1)
        mh.addWidget(barra)
        mh.addWidget(hline())
        self.mapa = FieldMap()
        mh.addWidget(self.mapa, 1)
        self.abas.addTab(self.mapa_host, "Mapas 2-D")

        # Superfície 3-D: o gráfico que o app antigo desenhava com o
        # plot_surface do matplotlib e que se perdeu na migração. Compartilha
        # o campo escolhido com o mapa 2-D — são duas vistas do mesmo dado.
        self.sup_host = QWidget()
        sh = QVBoxLayout(self.sup_host)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(0)
        barra3d = QWidget()
        b3 = QHBoxLayout(barra3d)
        b3.setContentsMargins(theme.space("8"), theme.space("4"),
                              theme.space("8"), theme.space("4"))
        b3.setSpacing(theme.space("4"))
        b3.addWidget(eyebrow("vista"))
        self._b_malha = button("Malha", "small", checkable=True)
        self._b_malha.setChecked(True)
        self._b_malha.setToolTip("Mostra as linhas da grade do MINIMOS")
        self._b_malha.toggled.connect(
            lambda on: self.superficie.set_wireframe(on))
        b3.addWidget(self._b_malha)
        for rotulo, az, elev in (("De cima", 0.0, 84.0),
                                 ("De lado", 90.0, 8.0),
                                 ("Isométrica", 35.0, 28.0)):
            b3.addWidget(button(
                rotulo, "small",
                on_click=lambda _c=False, a=az, e=elev:
                self.superficie.set_view(a, e)))
        b3.addStretch(1)
        sh.addWidget(barra3d)
        sh.addWidget(hline())
        self.superficie = SurfacePlot()
        sh.addWidget(self.superficie, 1)
        self.abas.addTab(self.sup_host, "Superfície 3-D")
        self.deck = DeckPanel()
        self.deck.setMinimumWidth(0)
        # O deck é editável: dá para mudar o que o MINIMOS realmente simula,
        # sem passar pelos campos nem pelo que o SUPREM gerou.
        self.deck.edit_started.connect(self._start_manual_deck)
        self.deck.edit_discarded.connect(self._discard_manual_deck)
        self.deck.run_literal_requested.connect(self.run)
        self.deck.hide_requested.connect(
            lambda: self._mostrar_aba(self.iv))
        self.abas.addTab(self.deck, "Deck .inp")
        lay.addWidget(self.abas, 1)

        lay.addWidget(hline())
        rodape = QWidget()
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(theme.space("10"), theme.space("5"),
                              theme.space("10"), theme.space("5"))
        rl.setSpacing(theme.space("5"))
        self._andamento = label("")
        theme.mark(self._andamento, role="muted")
        self._andamento.setFont(theme.font("mono", "micro"))
        rl.addWidget(self._andamento)
        rl.addWidget(stretch())
        self._aviso = label("")
        theme.mark(self._aviso, role="muted")
        self._aviso.setFont(theme.font("mono", "micro"))
        rl.addWidget(self._aviso)
        lay.addWidget(rodape)
        return painel

    # ── ponte com o processo ──────────────────────────────────────────────

    def set_process(self, steps, profile) -> None:
        """Recebe a receita e o perfil do processo e refaz a ponte."""
        self._steps = list(steps or [])
        self._profile = list(profile or [])
        self._refresh_bridge()

    def _refresh_bridge(self) -> None:
        self.bridge = bridge_mod.derive(self._steps, self._profile)
        b = self.bridge
        # o canal segue o substrato, mas o usuário pode discordar depois
        if "channel" in b.origem and isinstance(self._rows.get("channel"),
                                                Segmented):
            self.params["channel"] = b.channel
            self._rows["channel"].set_value(b.channel)
            self.params["gate"] = "NPOLY" if b.channel == "N" else "PPOLY"
            if isinstance(self._rows.get("gate"), Segmented):
                self._rows["gate"].set_value(self.params["gate"])
        while self._pl.count():
            item = self._pl.takeAt(0)
            w = item.widget()
            if w is not None:
                # setParent(None) ANTES do deleteLater(): tirar do layout não
                # tira da tela. O deleteLater só apaga na próxima volta do
                # laço de eventos, e as linhas novas entram agora — sem isto
                # as antigas continuam pintadas por baixo, e o painel fica
                # com os textos sobrepostos.
                w.setParent(None)
                w.deleteLater()
        if not self._steps:
            vazio = label("Nenhuma receita carregada: o MINIMOS vai usar os "
                          "valores padrão do próprio motor.", wrap=True)
            theme.mark(vazio, role="muted")
            self._pl.addWidget(vazio)
        else:
            linhas = [("Substrato", f"{fmt_number(b.nb)} cm⁻³",
                       b.origem.get("nb", "padrão do motor")),
                      ("Fonte/dreno", f"{b.sd_elem}, {fmt_number(b.sd_dose)} "
                       f"cm⁻², {fmt_number(b.sd_akev)} keV",
                       b.origem.get("sd", "padrão do motor")),
                      ("Recozimento", f"{fmt_number(b.anneal_c)} °C, "
                       f"{fmt_number(b.anneal_s)} s",
                       b.origem.get("anneal", "padrão do motor"))]
            if b.vt_dose > 0:
                linhas.append(("Ajuste de limiar",
                               f"{b.vt_elem}, {fmt_number(b.vt_dose)} cm⁻²",
                               b.origem.get("vt", "")))
            for titulo, valor, origem in linhas:
                t = label(titulo)
                t.setFont(theme.font("sans", "small", "medium"))
                v = label(valor, "mono")
                o = label(origem)
                theme.mark(o, role="muted")
                o.setFont(theme.font("mono", "micro"))
                self._pl.addWidget(t)
                self._pl.addWidget(v)
                self._pl.addWidget(o)
        nota = label(b.aviso, wrap=True)
        theme.mark(nota, role="muted")
        nota.setFont(theme.font("mono", "micro"))
        self._pl.addWidget(nota)
        self._aviso.setText(bridge_mod.AVISO_MOSIM if self._ponte_direta() else b.aviso)
        self._metricas["nb"].setText(fmt_number(b.nb))
        # Três casas: a junção vem de uma interpolação entre dois nós da
        # malha, e seis casas prometeriam uma precisão que ela não tem.
        self._metricas["xj"].setText(f"{b.xj_suprem:.3f}".replace(".", ",")
                                     if b.xj_suprem else "—")
        self._refresh_deck()

    # ── estado ────────────────────────────────────────────────────────────

    def _on_param(self, chave: str, valor) -> None:
        self.params[chave] = valor
        if chave == "mode":
            self._update_mode_visibility()
        self._refresh_deck()

    def _update_mode_visibility(self) -> None:
        self._seg_var.setVisible(self.params.get("mode") == "iv")
        self._seg_fisica.setVisible(self.params.get("mode") != "vth")
        for chave in ("step", "nstep"):
            w = self._rows.get(chave)
            if w is not None:
                w.setVisible(self.params.get("mode") == "iv")

    def deck_params(self) -> dict:
        """Os parâmetros completos do deck: a ponte mais o que a tela ajusta."""
        p = dict(self.bridge.as_params()) if self.bridge else {}
        p["channel"] = self.params.get("channel", p.get("channel", "N"))
        p["gate"] = self.params.get("gate", "NPOLY")
        for chave, padrao in (("tox_nm", 15.0), ("w_um", 1.0), ("l_um", 0.85),
                              ("ud", 0.1), ("ug", 0.0), ("step", 0.15)):
            v = parse_float(self.params.get(chave))
            p[chave] = padrao if v is None else v
        n = parse_float(self.params.get("nstep"))
        p["nstep"] = int(n) if n else 20
        p["mode"] = self.params.get("mode", "iv")
        p["fisica"] = self.params.get("fisica", "2d")
        p["step_var"] = self.params.get("step_var", "DG")
        p["auto_sign"] = False
        p["maps"] = p["mode"] == "op"
        p["title"] = "Dispositivo montado no MOS-Studio"
        return p

    def _mostrar_aba(self, widget) -> None:
        """Mostra a aba daquele widget.

        Por referência, não por índice: acrescentar a Superfície 3-D no meio
        da lista já tinha mandado o "abrir deck" para a aba errada.
        """
        i = self.abas.indexOf(widget)
        if i >= 0:
            self.abas.setCurrentIndex(i)

    def deck_text(self) -> str:
        """O deck que vai ao motor: o dos campos, ou o editado à mão."""
        if self.deck.editing:
            return self.deck.text()
        return minimos.build_deck(self.deck_params())

    def _ponte_direta(self, motor: str | None = None) -> bool:
        """O perfil do SUPREM vai ponto a ponto? (só o MOSIM lê FILE=2-D)."""
        motor = motor or minimos.motor_escolhido()
        return (motor == minimos.MOTOR_ABERTO and bool(self._profile)
                and not self.deck.editing)

    def _deck_e_perfil(self, motor: str) -> tuple[str, str | None]:
        """O deck da corrida e, com a ponte direta, o arquivo de dopagem."""
        texto = self.deck_text()
        if not self._ponte_direta(motor):
            return texto, None
        import tempfile
        caminho = Path(tempfile.mkdtemp(prefix="mos_studio_perfil_")) / "perfil2d.bin"
        try:
            return bridge_mod.deck_com_perfil(texto, self._profile, caminho), str(caminho)
        except (ValueError, KeyError, ZeroDivisionError) as exc:
            # sem perfil utilizável, a ponte por parâmetros continua valendo
            self._andamento.setText(f"perfil não transportado ({exc}); usando os parâmetros")
            return texto, None

    def manual_deck(self) -> bool:
        return self.deck.editing

    def _start_manual_deck(self) -> None:
        self.deck.set_manual(minimos.build_deck(self.deck_params()))
        self._refresh_source_note()

    def _discard_manual_deck(self) -> None:
        # Força a regeneração: ``_refresh_deck`` sai cedo enquanto o painel
        # está em modo manual, e é justamente dele que se quer sair.
        self._refresh_deck(force=True)
        self._refresh_source_note()

    def load_deck(self, texto: str, nome: str = "") -> None:
        """Põe um deck vindo de fora no modo manual.

        É o caminho para simular algo que o SUPREM não gerou: um deck escrito
        à mão, um exemplo do manual do MINIMOS, ou um arquivo guardado de
        outra sessão.
        """
        self.deck.set_manual(texto.replace("\r\n", "\n"))
        self._mostrar_aba(self.deck)
        self._refresh_source_note(nome)

    def _refresh_source_note(self, nome: str = "") -> None:
        if self.deck.editing:
            origem = nome or "editado à mão"
            self._aviso.setText(f"deck {origem} — os campos à esquerda não "
                                f"afetam esta execução")
        elif self.bridge is not None:
            aviso = self.bridge.aviso
            if self._ponte_direta():
                aviso = bridge_mod.AVISO_MOSIM
            self._aviso.setText(aviso)
        else:
            self._aviso.setText("")

    def _refresh_deck(self, force: bool = False) -> None:
        if self.deck.editing and not force:
            return
        texto = minimos.build_deck(self.deck_params())
        linhas = [(ln, None) for ln in texto.replace("\r\n", "\n").split("\n")]
        self.deck.set_generated(linhas, "dispositivo.inp")

    def _on_motor(self, _indice=None) -> None:
        minimos.definir_motor(self._seg_motor.value())
        self._refresh_engine()
        self._refresh_source_note()
        self.motor_changed.emit()

    def _refresh_engine(self) -> None:
        motor = minimos.motor_escolhido()
        if self._seg_motor.value() != motor:
            self._seg_motor.blockSignals(True)
            self._seg_motor.set_value(motor)
            self._seg_motor.blockSignals(False)
        self._eyebrow_motor.setText(
            "mosim · motor aberto" if motor == minimos.MOTOR_ABERTO else "minimos 6.1")
        problema = minimos.problemas_motor(motor)
        if problema:
            self._motor.setText("; ".join(problema))
            self._btn_run.setEnabled(False)
        elif motor == minimos.MOTOR_ABERTO:
            self._motor.setText("motor aberto (MOSIM): lê o deck do MINIMOS e "
                                "segue os modelos do manual do MINIMOS 6")
            self._btn_run.setEnabled(True)
        else:
            self._motor.setText(f"MINIMOS em {minimos.find_dir().name}")
            self._btn_run.setEnabled(True)
        if self._install_worker is None:
            self._btn_instalar.setVisible(not minimos.minimos_instalado())

    def install_engine(self) -> None:
        """Pede o minimoswin6.1.zip e instala o motor a partir dele."""
        if self._install_worker is not None:
            return
        inicio = importar_minimos.procurar_zip()
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolha o minimoswin6.1.zip (TU Wien)",
            str(inicio or Path.home()), "Zip do MINIMOS (*.zip)")
        if not caminho:
            return
        self.erro.hide()
        self._btn_instalar.setEnabled(False)
        self._motor.setText("instalando o MINIMOS…")
        self._install_worker = _InstallWorker(caminho, self)
        self._install_worker.done.connect(self._on_installed)
        self._install_worker.failed.connect(self._on_install_failed)
        self._install_worker.start()

    def _install_finished(self) -> None:
        self._install_worker = None
        self._btn_instalar.setEnabled(True)
        self._refresh_engine()

    def _on_installed(self, _pasta: str) -> None:
        self._install_finished()
        self._andamento.setText("MINIMOS instalado — pronto para simular")

    def _on_install_failed(self, mensagem: str) -> None:
        self._install_finished()
        self.erro.show_error("Não foi possível instalar o MINIMOS", mensagem,
                             f"Portal da TU Wien (registro gratuito): "
                             f"{importar_minimos.PORTAL}")

    def recheck_engine(self) -> None:
        """Reexamina a pasta do motor (o usuário pode tê-la arrumado)."""
        self._refresh_engine()

    # ── trazer de fora ────────────────────────────────────────────────────

    def import_deck(self) -> None:
        """Abre um deck ``.inp`` do disco e passa a simular ele."""
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir deck do MINIMOS", "",
            "Decks do MINIMOS (*.inp *.in *.min);;Todos os arquivos (*)")
        if not caminho:
            return
        try:
            texto = Path(caminho).read_text(encoding="latin1", errors="replace")
        except OSError as exc:
            self.erro.show_error("Não foi possível ler o deck", str(exc), "")
            return
        self.load_deck(texto, Path(caminho).name)

    def import_result(self) -> None:
        """Abre um resultado do MINIMOS e mostra o que ele traz.

        Serve para rever uma execução antiga, ou para olhar o resultado de
        uma simulação feita fora daqui, sem rodar nada. Aceita o PIF
        (``fort.30``/``.asciipif``), a curva (``fort.61``/``.iv``) e a
        referência (``.ref``); o que estiver na mesma pasta é carregado junto.
        """
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Abrir resultado do MINIMOS", "",
            "Saídas do MINIMOS (fort.30 fort.61 *.asciipif *.iv *.ref);;"
            "Todos os arquivos (*)")
        if not caminho:
            return
        escolhido = Path(caminho)
        caixa: dict = {"returncode": 0, "stages": ["arquivo aberto"],
                       "files": [escolhido.name], "__dir__": str(escolhido.parent)}

        def ler(*nomes) -> str | None:
            for n in nomes:
                f = escolhido if escolhido.name == n else escolhido.parent / n
                try:
                    if f.is_file() and f.stat().st_size:
                        return f.read_text(encoding="latin1", errors="replace")
                except OSError:
                    continue
            return None

        bruto = ler(escolhido.name) or ""
        caixa["pif"] = (bruto if "coordinate" in bruto.lower()
                        or escolhido.name in ("fort.30",)
                        or escolhido.suffix == ".asciipif"
                        else ler("fort.30", f"{escolhido.stem}.asciipif"))
        caixa["iv"] = (bruto if escolhido.name == "fort.61"
                       or escolhido.suffix == ".iv"
                       else ler("fort.61", f"{escolhido.stem}.iv"))
        caixa["ref"] = ler(f"{escolhido.stem}.ref", "mm_run.ref")
        caixa["out"] = ler("fort.16", f"{escolhido.stem}.out")
        if not caixa["pif"] and not caixa["iv"]:
            self.erro.show_error(
                "Nada para mostrar nesse arquivo",
                "O MOS-Studio lê o PIF (fort.30, com os mapas 2-D) e a curva "
                "(fort.61). Escolha um dos dois, ou um arquivo ao lado deles "
                "na mesma pasta.", escolhido.name)
            return
        self.erro.hide()
        self._on_done(caixa)
        # Depois do _on_done: senão o texto da corrida sobrescreve, e nada na
        # tela diria que estes números vieram de um arquivo, não do motor.
        self._andamento.setText(f"arquivo aberto: {escolhido.name}")

    # ── execução ──────────────────────────────────────────────────────────

    def run(self) -> None:
        if self._worker is not None:
            return
        motor = minimos.motor_escolhido()
        problemas = minimos.problemas_motor(motor)
        if problemas:
            self.erro.show_error(
                f"O {minimos.NOMES_MOTOR[motor]} não está pronto",
                "; ".join(problemas), "")
            return
        self.erro.hide()
        self.result = None
        self.iv.clear()
        self.mapa.clear()
        self.superficie.clear()
        self._metricas["vt"].setText("—")
        self._metricas["id"].setText("—")
        self._andamento.setText(f"rodando o {minimos.NOMES_MOTOR[motor]}…")
        self._btn_run.setEnabled(False)
        deck, dopfile = self._deck_e_perfil(motor)
        self._worker = _RunWorker(deck, motor, self, dopfile=dopfile)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self.run_started.emit()

    def _on_failed(self, mensagem: str) -> None:
        self._worker = None
        self._btn_run.setEnabled(True)
        self._andamento.setText("a corrida falhou")
        self.erro.show_error(
            f"O {minimos.NOMES_MOTOR[minimos.motor_escolhido()]} não concluiu",
            mensagem, mensagem)

    def _on_done(self, caixa: dict) -> None:
        self._worker = None
        self._btn_run.setEnabled(True)
        self.result = caixa
        ref = caixa.get("ref") or ""
        headers, rows = parsers.parse_minimos_iv(caixa.get("iv") or "")

        tem_mapas = bool(caixa.get("pif"))
        if not rows and not tem_mapas:
            motivo = self._diagnose(ref)
            self._andamento.setText("a corrida não produziu curva")
            self.erro.show_error(
                f"O {minimos.NOMES_MOTOR[minimos.motor_escolhido()]} não produziu corrente", motivo,
                                 ref)
        elif rows:
            self._andamento.setText(
                f"{len(rows)} ponto de polarização" if len(rows) == 1
                else f"{len(rows)} pontos de polarização")
            self._fill_iv(headers, rows)

        self._fill_ib(headers, rows)
        vt = parsers.parse_minimos_vt(ref)
        self._metricas["vt"].setText(fmt_number(vt) if vt is not None else "—")
        self._fill_maps(caixa.get("pif") or "")
        # Mostra o que a corrida produziu. Uma corrida de mapas que terminava
        # na aba da curva deixava o usuário olhando um gráfico de um ponto só,
        # convencido de que não tinha saído nada.
        if tem_mapas and (not rows or self.params.get("mode") == "op"):
            self._mostrar_aba(self.mapa_host)
        elif rows:
            self._mostrar_aba(self.iv)
        self.run_finished.emit(caixa)

    def _diagnose(self, ref: str) -> str:
        """Traduz as falhas conhecidas deste motor para algo acionável."""
        alto = ref.upper()
        erros = [l.strip(" 0") for l in ref.splitlines() if "*ERROR*" in l.upper()]
        if erros:
            return "O deck foi recusado: " + erros[0].replace("*ERROR*", "").strip()
        if "SIGSEGV" in alto:
            return ("O motor abortou com falha de memória. Nesta compilação "
                    "isso acontece quando o recozimento é curto demais para "
                    "formar junção, ou quando a geometria do canal é pequena "
                    "demais para a malha. Tente um comprimento de canal maior "
                    "ou um recozimento mais longo na receita.")
        if "ABORT" in alto:
            return ("O motor interrompeu o cálculo. A referência completa "
                    "está abaixo — a linha com o número do módulo diz onde.")
        if "NOT FOUND" in alto:
            return ("O motor não localizou um dos contatos no perfil. "
                    "Verifique a dose de fonte/dreno vinda da receita.")
        if "ALOCAR" in alto or "ALLOCAT" in alto:
            return ("O motor pediu mais memória do que o sistema deu. Reduza "
                    "o número de passos da varredura.")
        return ("A corrida terminou sem escrever a tabela de correntes. A "
                "referência completa está abaixo.")

    def _fill_ib(self, headers: list[str], rows: list[tuple]) -> None:
        """Corrente de substrato (só existe com avalanche): no mostrador próprio,
        porque na escala do ID (mil vezes maior) ela sumiria no gráfico."""
        i_ib = headers.index("IB") if "IB" in headers else -1
        ibs = [abs(r[i_ib]) for r in rows if i_ib >= 0 and len(r) > i_ib]
        tem = any(v > 0 for v in ibs)
        self._bloco_ib.setVisible(tem)
        self._metricas["ib"].setText(fmt_number(max(ibs)) if tem else "—")

    def _fill_iv(self, headers: list[str], rows: list[tuple]) -> None:
        """Monta a curva a partir das colunas que o ``.iv`` trouxe."""
        def col(nome: str) -> int:
            return headers.index(nome) if nome in headers else -1

        i_id, i_ug, i_ud = col("ID"), col("UG"), col("UD")
        if i_id < 0:
            return
        varrendo_porta = self.params.get("step_var", "DG") == "DG"
        i_x = i_ug if varrendo_porta and i_ug >= 0 else i_ud
        if i_x < 0:
            i_x = 0
        pontos = [(r[i_x], r[i_id]) for r in rows
                  if len(r) > max(i_x, i_id)]
        rotulo = "UG (V)" if i_x == i_ug else "UD (V)"
        self.iv.set_curves([("ID", pontos)], rotulo)
        if pontos:
            self._metricas["id"].setText(
                fmt_number(max(abs(y) for _, y in pontos)))

    def _fill_maps(self, pif: str) -> None:
        lat, vert, campos = parsers.parse_minimos_pif(pif)
        self._campos = campos
        self._lat, self._vert = lat, vert
        antigo = self._seg_campo
        nomes = list(campos)
        novo = Segmented([(n, n.split(" (")[0]) for n in nomes],
                         nomes[0] if nomes else "")
        novo.changed.connect(lambda _i: self._show_field(novo.value()))
        pai = antigo.parentWidget()
        if pai is not None:
            lay = pai.layout()
            lay.replaceWidget(antigo, novo)
            # Mesmo motivo do _refresh_bridge: sem o setParent(None) o
            # seletor antigo fica desenhado em cima do novo até o laço de
            # eventos rodar.
            antigo.setParent(None)
            antigo.deleteLater()
        self._seg_campo = novo
        if nomes:
            self._show_field(nomes[0])
        else:
            self.mapa.clear()
            self.mapa.set_field([], [], [], "")
            self.superficie.clear()

    def _show_field(self, nome: str) -> None:
        """Põe o campo escolhido nas duas vistas: o mapa e a superfície."""
        valores = getattr(self, "_campos", {}).get(nome)
        if not valores:
            self.mapa.clear()
            self.superficie.clear()
            return
        log = "cm⁻³" in nome or "concentra" in nome.lower()
        self.mapa.set_field(self._lat, self._vert, valores, nome, log)
        # A superfície não usa escala logarítmica: a altura é o valor, e
        # achatar o eixo esconderia justamente o relevo que ela existe para
        # mostrar.
        self.superficie.set_field(self._lat, self._vert, valores, nome)
