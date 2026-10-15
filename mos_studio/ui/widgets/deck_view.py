"""Visualização e edição manual do deck gerado pela receita.

Dois modos, como no design:

* **gerado** — somente leitura, com número de linha, destaque por tipo de
  token e clique na linha para selecionar a etapa que a originou;
* **editado à mão** — texto livre. Nesse modo a receita deixa de acompanhar o
  deck, e o aviso diz isso: ao rodar, o texto vai ao motor como está.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (QPainter, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor)
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QVBoxLayout,
                               QWidget)

from .. import theme
from .common import button, eyebrow, hline, label, row, stretch


class DeckHighlighter(QSyntaxHighlighter):
    """Destaque de sintaxe do deck: comando, parâmetro, valor, continuação."""

    def __init__(self, document) -> None:
        super().__init__(document)
        self._cache_theme = ""
        self._cmd = self._key = self._eq = self._val = QTextCharFormat()
        self._ensure_formats()

    def _ensure_formats(self) -> None:
        """(Re)constrói os formatos quando o tema em vigor muda.

        Os formatos guardam a cor resolvida, então precisam ser refeitos ao
        trocar de tema — senão o deck fica escrito na cor do tema anterior.
        """
        if self._cache_theme == theme.current():
            return
        self._cache_theme = theme.current()
        self._cmd = self._fmt("accent-ink", "semibold")
        self._key = self._fmt("ink-dim")
        self._eq = self._fmt("ink-faint")
        self._val = self._fmt("ink", "medium")

    @staticmethod
    def _fmt(color_key: str, weight: str = "regular") -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(theme.qcolor(color_key))
        f.setFontWeight(theme.FONT_WEIGHTS[weight])
        return f

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - API do Qt
        self._ensure_formats()
        pos = 0
        primeiro = True
        if text.startswith("+"):
            self.setFormat(0, 1, self._cmd)
            pos = 1
            primeiro = False
        for token in self._tokens(text[pos:]):
            inicio, fim = pos + token[0], pos + token[1]
            palavra = token[2]
            if not palavra.strip():
                continue
            if primeiro:
                self.setFormat(inicio, fim - inicio, self._cmd)
                primeiro = False
                continue
            eq = palavra.find("=")
            if eq > 0:
                self.setFormat(inicio, eq, self._key)
                self.setFormat(inicio + eq, 1, self._eq)
                self.setFormat(inicio + eq + 1, len(palavra) - eq - 1, self._val)
            else:
                self.setFormat(inicio, fim - inicio, self._val)

    @staticmethod
    def _tokens(text: str):
        i = 0
        for parte in text.split(" "):
            if parte:
                yield i, i + len(parte), parte
            i += len(parte) + 1


class _LineNumbers(QWidget):
    """Faixa de números de linha, à esquerda do deck."""

    def __init__(self, editor: "DeckView") -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802 - API do Qt
        return QSize(self._editor.gutter_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        self._editor.paint_gutter(self, event)


class DeckView(QPlainTextEdit):
    """O deck em si, com faixa de números e clique por linha."""

    line_clicked = Signal(int)      # número de linha, base 1

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(theme.font("mono", "small"))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameShape(QPlainTextEdit.Shape.NoFrame)
        theme.mark(self, surface="code", role="mono")
        self._gutter = _LineNumbers(self)
        self._highlighter = DeckHighlighter(self.document())
        self.blockCountChanged.connect(lambda _n: self._update_gutter_width())
        self.updateRequest.connect(self._on_update_request)
        self._update_gutter_width()

    # ── faixa de números ──────────────────────────────────────────────────

    def gutter_width(self) -> int:
        digitos = max(2, len(str(max(1, self.blockCount()))))
        largura = self.fontMetrics().horizontalAdvance("9") * digitos
        return largura + theme.space("10")

    def _update_gutter_width(self) -> None:
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(),
                                       self.gutter_width(), cr.height()))

    def paint_gutter(self, gutter: QWidget, event) -> None:
        p = QPainter(gutter)
        p.fillRect(event.rect(), theme.qcolor("code-bg"))
        p.setFont(theme.font("mono", "tiny"))
        bloco = self.firstVisibleBlock()
        numero = bloco.blockNumber()
        top = self.blockBoundingGeometry(bloco).translated(
            self.contentOffset()).top()
        atual = self.textCursor().blockNumber()
        while bloco.isValid() and top <= event.rect().bottom():
            altura = self.blockBoundingRect(bloco).height()
            if bloco.isVisible() and top + altura >= event.rect().top():
                p.setPen(theme.qcolor("ink" if numero == atual else "ink-faint"))
                p.drawText(QRect(0, int(top), gutter.width() - theme.space("7"),
                                 int(altura)),
                           int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                           str(numero + 1))
            bloco = bloco.next()
            top += altura
            numero += 1
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().mousePressEvent(event)
        self.line_clicked.emit(self.textCursor().blockNumber() + 1)


class DeckPanel(QWidget):
    """Painel do deck: cabeçalho, aviso de edição manual, texto e rodapé."""

    step_requested = Signal(int)        # uid da etapa clicada
    edit_started = Signal()
    edit_discarded = Signal()
    run_literal_requested = Signal()
    hide_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        theme.mark(self, surface="code")
        self._line_uids: list[int | None] = []
        self._editing = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)

        # cabeçalho
        cabeca = QWidget()
        cabeca.setFixedHeight(theme.dimension("header-height") - 4)
        hl = QHBoxLayout(cabeca)
        hl.setContentsMargins(theme.space("9"), 0, theme.space("6"), 0)
        hl.setSpacing(theme.space("5"))
        hl.addWidget(eyebrow("deck"))
        self._nome = label("", "mono")
        hl.addWidget(self._nome)
        hl.addStretch(1)
        self._b_editar = button("Editar à mão", "small",
                                on_click=self.edit_started.emit)
        self._b_copiar = button("Copiar", "small", on_click=self._copy)
        hl.addWidget(self._b_editar)
        hl.addWidget(self._b_copiar)
        hl.addWidget(button("×", "small", tooltip="Ocultar deck",
                            on_click=self.hide_requested.emit))
        raiz.addWidget(cabeca)
        raiz.addWidget(hline())

        # aviso do modo manual
        self._aviso = QWidget()
        theme.mark(self._aviso, surface="accent-soft")
        av = QVBoxLayout(self._aviso)
        av.setContentsMargins(theme.space("9"), theme.space("6"),
                              theme.space("9"), theme.space("6"))
        av.setSpacing(theme.space("5"))
        av.addWidget(label(
            "Edição manual. A receita não acompanha estas mudanças; ao rodar, "
            "o deck vai ao motor exatamente como está.", "hint", wrap=True))
        av.addWidget(row(
            button("Rodar este deck", "primary",
                   on_click=self.run_literal_requested.emit),
            button("Descartar e voltar à receita", "small",
                   on_click=self.edit_discarded.emit),
            stretch(), spacing="3"))
        raiz.addWidget(self._aviso)
        self._aviso.hide()

        self.view = DeckView()
        self.view.setReadOnly(True)
        self.view.line_clicked.connect(self._on_line_clicked)
        raiz.addWidget(self.view, 1)

        raiz.addWidget(hline())
        rodape = QWidget()
        rodape.setFixedHeight(theme.space("16") + theme.space("1"))
        rl = QHBoxLayout(rodape)
        rl.setContentsMargins(theme.space("9"), 0, theme.space("9"), 0)
        self._origem = label("", "eyebrow")
        self._contagem = label("", "eyebrow")
        rl.addWidget(self._origem)
        rl.addStretch(1)
        rl.addWidget(self._contagem)
        raiz.addWidget(rodape)

    # ── conteúdo ──────────────────────────────────────────────────────────

    def set_generated(self, lines: list[tuple[str, int | None]],
                      filename: str = "") -> None:
        """Mostra o deck gerado pela receita (somente leitura)."""
        self._editing = False
        self._line_uids = [uid for _t, uid in lines]
        texto = "\n".join(t for t, _u in lines)
        self.view.setReadOnly(True)
        self.view.setPlainText(texto)
        self._aviso.hide()
        self._b_editar.show()
        self._nome.setText(filename or "DECK.IN")
        self._origem.setText("Gerado da receita")
        self._contagem.setText(f"ASCII · CRLF · {len(lines)} linhas")

    def set_manual(self, text: str) -> None:
        """Entra no modo de edição manual com o texto dado."""
        self._editing = True
        self._line_uids = []
        self.view.setReadOnly(False)
        self.view.setPlainText(text)
        self._aviso.show()
        self._b_editar.hide()
        self._origem.setText("Editado à mão")
        self._contagem.setText(
            f"ASCII · CRLF · {len(text.splitlines())} linhas")

    @property
    def editing(self) -> bool:
        return self._editing

    def text(self) -> str:
        """Texto atual do deck, com fim de linha CRLF como o motor espera."""
        bruto = self.view.toPlainText().replace("\r\n", "\n").replace("\r", "\n")
        return bruto.replace("\n", "\r\n") + "\r\n"

    def highlight_step(self, uid: int | None) -> None:
        """Põe o cursor na primeira linha da etapa pedida."""
        if uid is None or self._editing or uid not in self._line_uids:
            return
        linha = self._line_uids.index(uid)
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.Down,
                            QTextCursor.MoveMode.MoveAnchor, linha)
        self.view.setTextCursor(cursor)
        self.view.centerCursor()

    def _on_line_clicked(self, numero: int) -> None:
        indice = numero - 1
        if 0 <= indice < len(self._line_uids):
            uid = self._line_uids[indice]
            if uid is not None:
                self.step_requested.emit(uid)

    def _copy(self) -> None:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self.text())
        self._b_copiar.setText("Copiado")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1400, lambda: self._b_copiar.setText("Copiar"))
