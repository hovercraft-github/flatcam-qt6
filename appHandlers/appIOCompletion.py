import time
from typing import runtime_checkable, Protocol, _ProtocolMeta
from abc import abstractmethod
from collections.abc import Callable
import uuid

from PyQt6 import QtCore
from PyQt6.QtCore import QMutexLocker, QThread, QCoreApplication, QWaitCondition, QMutex


@runtime_checkable
class Stopable(Protocol):
    """
    Protocol for objects that can be stopped.
    """

    @abstractmethod
    def stop(self):
        raise NotImplementedError


@runtime_checkable
class SupportsCompeletionWaiting(Protocol):
    completion_task_signal: QtCore.pyqtSignal

    @abstractmethod
    def check_condition(self) -> bool:
        """
        Checks a condition and returns True if the condition is met, indicating that the waiting can stop.
        """
        raise NotImplementedError

    @abstractmethod
    def __call__(self) -> bool:
        """
        Use check_condition to determine if the waiting should stop, then trigger the completion task if the condition is met
        and return the result of check_condition.  
        """
        raise NotImplementedError

    @abstractmethod
    def do_completion_task(self) -> None:
        raise NotImplementedError

    def wait(self, granularity_ms: int = 100, timeout_ms: int | None = None) -> bool:
        """
        Waits for the completion condition to be met by periodically checking it with the specified granularity.
        """
        start_time = time.perf_counter()
        while True:
            result = self()
            if result:
                return True
            QCoreApplication.processEvents()
            if timeout_ms is not None and (time.perf_counter() - start_time) * 1000 > timeout_ms:
                break
            QThread.msleep(granularity_ms)
        return False

class CombinedMeta(_ProtocolMeta, type(QtCore.QObject)):
    pass


class appIOCompletion(
    QtCore.QObject, Stopable, SupportsCompeletionWaiting, metaclass=CombinedMeta
):
    """
    Manages waiting for a condition to be met and triggering a completion task when it is.
    """

    completion_task_signal = QtCore.pyqtSignal()

    def __init__(
        self,
        check_condition_func: Callable[[], bool | None],
        on_completion_func: Callable[[], None] | None = None,
    ):
        super().__init__()
        if not callable(check_condition_func):
            raise ValueError("check_condition_func must be callable")
        self.check_condition_func = check_condition_func
        self.on_completion_func = on_completion_func
        self.completion_task_signal.connect(self.do_completion_task)
        self.done = False
        self.condition_met = False
        self.mutex = QMutex()

    def check_condition(self) -> bool:
        """
        Checks a condition and returns True if the condition is met, indicating that the waiting can stop.</br>  
        Note that in this implementation if check_condition_func returns None, it will be treated as True. 
        This done for ease of use when the condition is simply a side effect and does not need to return a value.
        Returns:
            bool: True if the condition is met, False otherwise.
        """
        ret = self.check_condition_func()
        if ret is None:
            ret = True
        return ret

    def __call__(self) -> bool:
        if self.condition_met:
            return True
        if self.check_condition():
            self.condition_met = True
            self.completion_task_signal.emit()
            return True
        return False

    def do_completion_task(self) -> None:
        if self.done:
            return
        if self.on_completion_func is not None:
            self.on_completion_func()
        self.stop()
        with QMutexLocker(self.mutex):
            self.done = True

    def stop(self):
        # Implement any necessary cleanup here
        pass

    def wait(self, granularity_ms: int = 100, timeout_ms: int | None = None) -> bool:
        """
        Waits for the completion condition to be met by periodically checking it with the specified granularity.
        """
        start_time = time.perf_counter()
        while True:
            with QMutexLocker(self.mutex):
                result = self.done
            if result:
                return True
            self.__call__()
            QCoreApplication.processEvents()
            if timeout_ms is not None and (time.perf_counter() - start_time) * 1000 > timeout_ms:
                break
            QThread.msleep(granularity_ms)
        return False

class appIOCompletionTimer(appIOCompletion):
    """
    An appIOCompletion that uses a QTimer to periodically run check_condition_func until it returns True or None.  
    IF target_thread is specified, the timer will run in that thread, otherwise it will run in the thread where the appIOCompletionTimer was created.
    """

    start_signal = QtCore.pyqtSignal()
    stop_signal = QtCore.pyqtSignal()

    def __init__(
        self,
        check_condition_func: Callable[[], bool | None],
        on_completion_func: Callable[[], None] | None = None,
        interval_ms: int = 100,
        target_thread: QtCore.QThread | None = None,
    ):
        super().__init__(check_condition_func, on_completion_func)
        if target_thread is not None:
            self.moveToThread(target_thread)
        self.interval_ms = interval_ms
        self.timer: QtCore.QTimer | None = None
        self.start_signal.connect(self._start)
        self.stop_signal.connect(self._stop)
        self.started = False

    def start(self):
        self.start_signal.emit()
        QCoreApplication.processEvents()
        QThread.msleep(100)

    def stop(self):
        self.stop_signal.emit()
        QCoreApplication.processEvents()
        QThread.msleep(100)

    def wait(self, granularity_ms: int = 100, timeout_ms: int | None = None) -> bool:
        """
        Waits for the completion condition to be met by periodically checking it with the specified granularity.
        """
        start_time = time.perf_counter()
        sleep = granularity_ms
        if timeout_ms is not None and timeout_ms >= 100:
            sleep = min(granularity_ms, timeout_ms // 10)
        if not self.started:
            self.start()
            self.started = True
        while True:
            with QMutexLocker(self.mutex):
                result = self.done
            if result:
                return True
            QCoreApplication.processEvents()
            if timeout_ms is not None and (time.perf_counter() - start_time) * 1000 > timeout_ms:
                break
            QThread.msleep(sleep)
        return False

    def _start(self):
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.__call__)
        self.timer.start(self.interval_ms)

    def _stop(self):
        if self.timer is not None:
            self.timer.stop()
        self.started = False


class appIOCompletionManager(QtCore.QObject):
    """
    Manages multiple appIOCompletion instances and their waiters.
    """

    def __init__(self):
        super().__init__()
        self.completions: dict[str, appIOCompletion] = {}
        self.mutex = QMutex()

    def add(self, completion: appIOCompletion):
        with QMutexLocker(self.mutex):
            key = uuid.uuid4().hex
            self.completions[key] = completion

    def clear(self):
        """
        Clears all completions from the manager.
        """
        with QMutexLocker(self.mutex):
            self.completions.clear()

    def wait_all(self, granularity_ms: int = 100, timeout_ms: int | None = None):
        cnt_completed = 0
        completions_shallow_copy = {}
        with QMutexLocker(self.mutex):
            completions_shallow_copy = self.completions.copy()
        for key, completion in completions_shallow_copy.items():
            if completion.wait(granularity_ms=granularity_ms, timeout_ms=timeout_ms):   
                cnt_completed += 1
                with QMutexLocker(self.mutex):
                    if key in self.completions:
                        del self.completions[key]
        return cnt_completed, len(completions_shallow_copy)
