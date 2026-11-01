"""Выполнение тяжёлых расчётов и сетевых запросов в фоновых потоках.

Результат всегда возвращается в главный поток через _Dispatcher, поэтому в
обработчиках on_done/on_error можно безопасно менять интерфейс.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import shiboken6
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from astronomy.context import EphemerisUnavailable

log = logging.getLogger(__name__)


class _Dispatcher(QObject):
    call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.call.connect(self._run)

    @Slot(object)
    def _run(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:
            log.exception("Ошибка в обработчике результата фоновой задачи")


_dispatcher: _Dispatcher | None = None


def _get_dispatcher() -> _Dispatcher:
    global _dispatcher
    # Создаётся в главном потоке; пересоздаётся, если QApplication уже был уничтожен (тесты).
    if _dispatcher is None or not shiboken6.isValid(_dispatcher):
        _dispatcher = _Dispatcher()
    return _dispatcher


class _Task(QRunnable):
    def __init__(self, fn, args, kwargs, on_done, on_error, dispatcher):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.on_done, self.on_error, self.dispatcher = on_done, on_error, dispatcher

    def _emit(self, fn: Callable[[], None]) -> None:
        if not shiboken6.isValid(self.dispatcher):
            return      # приложение уже закрыто — результат никому не нужен
        try:
            self.dispatcher.call.emit(fn)
        except RuntimeError:
            pass

    def run(self) -> None:
        try:
            result = self.fn(*self.args, **self.kwargs)
        except EphemerisUnavailable as exc:      # ожидаемая ситуация, не авария
            log.warning("Фоновая задача: %s", exc)
            message = str(exc)
            if self.on_error:
                self._emit(lambda: self.on_error(message))
            return
        except Exception as exc:
            log.exception("Ошибка фоновой задачи")
            message = str(exc) or exc.__class__.__name__
            if self.on_error:
                self._emit(lambda: self.on_error(message))
            return
        if self.on_done:
            self._emit(lambda: self.on_done(result))


def run_async(fn: Callable[..., Any], on_done: Callable[[Any], None] | None = None,
              on_error: Callable[[str], None] | None = None, *args, **kwargs) -> None:
    """Запускает fn(*args, **kwargs) в пуле потоков. Вызывать из главного потока."""
    task = _Task(fn, args, kwargs, on_done, on_error, _get_dispatcher())
    QThreadPool.globalInstance().start(task)
