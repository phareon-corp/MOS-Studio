"""Ponte entre o motor (que é síncrono e não conhece Qt) e a interface.

O núcleo roda numa thread de trabalho; a interface recebe sinais: etapa em
curso, tempo decorrido, fim, falha ou cancelamento. O cancelamento chega ao
binário em execução pelo ``cancel()`` do executor.

Qual motor roda vem do registro em :mod:`mos_studio.core.engines`, não de um
``import`` fixo: o SUPREM-III e o SUPREM-IV têm executores diferentes, com
exceções de cancelamento diferentes, e a interface só precisa saber o
identificador do motor do projeto.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..core import engines


class _Worker(QObject):
    """Executa o deck fora da thread da interface."""

    stage = Signal(str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, runner, cancelled: type[Exception]) -> None:
        super().__init__()
        self._runner = runner
        self._cancelled = cancelled

    def run(self) -> None:
        try:
            result = self._runner.execute(on_stage=self.stage.emit)
        except self._cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - a mensagem vai para a interface
            self.failed.emit(str(exc))
        else:
            self.finished.emit(result)


class RunController(QObject):
    """Estado de uma execução, visto pela interface.

    Sinais: ``started``, ``tick`` (segundos decorridos), ``stage_changed``,
    ``succeeded`` (o ``RunResult`` do motor), ``failed`` (mensagem),
    ``was_cancelled``.
    """

    started = Signal()
    tick = Signal(float)
    stage_changed = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    was_cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._runner = None
        self._engine_id = engines.SUPREM3
        self._t0 = 0.0
        self._elapsed = 0.0
        self._stage = ""
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_tick)

    # ── consulta ──────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    @property
    def elapsed(self) -> float:
        return self._elapsed

    @property
    def stage(self) -> str:
        return self._stage

    @property
    def engine_id(self) -> str:
        """Motor da execução em curso, ou da última."""
        return self._engine_id

    # ── controle ──────────────────────────────────────────────────────────

    def start(self, deck: str, engine_id: str = "") -> None:
        """Começa uma execução no motor pedido.

        Ignorado se já houver uma em curso — duas execuções ao mesmo tempo
        disputariam a pasta de trabalho.
        """
        if self.running:
            return
        self._engine_id = engine_id or engines.default_id()
        motor = engines.get(self._engine_id)
        self._runner = motor.runner(deck)
        self._worker = _Worker(self._runner, motor.cancelled)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.stage.connect(self._on_stage)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._t0 = time.monotonic()
        self._elapsed = 0.0
        self._stage = ""
        self._timer.start()
        self._thread.start()
        self.started.emit()

    def cancel(self) -> None:
        """Pede o cancelamento da execução em curso."""
        if self._runner is not None:
            self._runner.cancel()

    # ── interno ───────────────────────────────────────────────────────────

    def _on_tick(self) -> None:
        self._elapsed = time.monotonic() - self._t0
        self.tick.emit(self._elapsed)

    def _on_stage(self, stage: str) -> None:
        self._stage = stage
        self.stage_changed.emit(stage)

    def _finish(self) -> None:
        self._timer.stop()
        self._elapsed = time.monotonic() - self._t0
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(5000)
        self._thread = None
        self._worker = None
        self._runner = None

    def _on_finished(self, result) -> None:
        self._finish()
        self.succeeded.emit(result)

    def _on_failed(self, message: str) -> None:
        self._finish()
        self.failed.emit(message)

    def _on_cancelled(self) -> None:
        self._finish()
        self.was_cancelled.emit()


def format_elapsed(seconds: float) -> str:
    """``mm:ss,s`` como no design (``00:04,8``)."""
    minutos = int(seconds // 60)
    resto = seconds - minutos * 60
    return f"{minutos:02d}:{resto:04.1f}".replace(".", ",")
