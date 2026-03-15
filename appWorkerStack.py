
from PyQt6 import QtCore
from appWorker import Worker


class WorkerStack(QtCore.QObject):
    """
    Manages a pool of Worker threads with load-balanced task dispatch.

    HIGH and NORMAL priority tasks are dispatched IMMEDIATELY to the
    least-loaded worker (pre-queued in the worker's signal queue for
    maximum throughput — zero inter-task delay).

    LOW priority tasks have BARRIER semantics: they are held in a
    deferred list and only dispatched when ALL high/normal tasks
    have completed. This guarantees finalization tasks (like plot_all)
    run after all regular work is done.

    Priority levels:
        'high'   (0)  — Dispatched immediately, same as normal
        'normal' (5)  — Default. Dispatched immediately to least-loaded worker
        'low'    (10) — Barrier: deferred until all high/normal tasks complete

    Usage:
        # Normal (default — no 'priority' key needed):
        app.worker_task.emit({'fcn': my_func, 'params': [arg1, arg2]})

        # Low priority — waits for ALL normal tasks to complete first:
        app.worker_task.emit({'fcn': cleanup_func, 'params': [], 'priority': 'low'})
    """

    thread_exception = QtCore.pyqtSignal(object)

    # Priority constants (lower number = higher priority)
    PRIORITY_HIGH = 0
    PRIORITY_NORMAL = 5
    PRIORITY_LOW = 10  # Barrier: deferred until all other tasks complete

    # Map string names to numeric values
    _PRIORITY_MAP = {
        'high': PRIORITY_HIGH,
        'normal': PRIORITY_NORMAL,
        'low': PRIORITY_LOW
    }

    def __init__(self, workers_number):
        super(WorkerStack, self).__init__()

        self.workers = []
        self.threads = []
        self.load = {}                              # {'worker_name': queued_task_count}
        self.worker_map = {}                        # 'worker_name' -> Worker instance

        self._pending_count = 0                     # In-flight high/normal tasks (not yet completed)
        self._deferred_tasks = []                   # LOW priority tasks waiting for barrier

        # Create workers crew
        for i in range(0, workers_number):
            worker = Worker(self, 'Slogger-' + str(i))
            thread = QtCore.QThread()

            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.task_completed.connect(self.on_task_completed)

            thread.start(QtCore.QThread.Priority.LowPriority)

            self.workers.append(worker)
            self.threads.append(thread)
            self.load[worker.name] = 0
            self.worker_map[worker.name] = worker

    def add_task(self, task):
        """
        Add a task for execution.

        HIGH/NORMAL tasks are dispatched immediately to the least-loaded worker.
        LOW tasks are deferred until all high/normal tasks complete (barrier).

        :param task: dict with keys:
            'fcn'      — callable to execute (required)
            'params'   — list of arguments (required)
            'priority' — 'high', 'normal' (default), 'low', or numeric 0-10 (optional)
        """
        priority = task.get('priority', 'normal')

        # Accept both string names and numeric values
        if isinstance(priority, str):
            priority = self._PRIORITY_MAP.get(priority, self.PRIORITY_NORMAL)

        if priority >= self.PRIORITY_LOW:
            # LOW priority: defer until all normal/high tasks complete
            self._deferred_tasks.append(task)
            # If nothing is running, flush immediately
            if self._pending_count == 0:
                self._flush_deferred()
        else:
            # HIGH/NORMAL: dispatch immediately to least-loaded worker
            self._dispatch_to_worker(task)

    def _dispatch_to_worker(self, task):
        """Dispatch a task immediately to the least-loaded worker."""
        worker_name = min(self.load, key=self.load.get)
        self.load[worker_name] += 1
        self._pending_count += 1
        self.worker_map[worker_name].worker_task_signal.emit(
            {'worker_name': worker_name, 'fcn': task['fcn'], 'params': task['params']}
        )

    def on_task_completed(self, worker_name):
        """Called via signal when a worker finishes its current task."""
        self.load[str(worker_name)] -= 1
        self._pending_count -= 1

        # When all normal/high tasks are done, flush deferred (LOW) tasks
        if self._pending_count == 0 and self._deferred_tasks:
            self._flush_deferred()

    def _flush_deferred(self):
        """Dispatch all deferred LOW tasks. Called only when no normal/high tasks remain."""
        tasks = self._deferred_tasks[:]
        self._deferred_tasks.clear()
        for task in tasks:
            worker_name = min(self.load, key=self.load.get)
            self.load[worker_name] += 1
            self._pending_count += 1  # Track deferred tasks so completion decrements correctly
            self.worker_map[worker_name].worker_task_signal.emit(
                {'worker_name': worker_name, 'fcn': task['fcn'], 'params': task['params']}
            )

    def __del__(self):
        self.quit()

    def quit(self):
        """Gracefully stop all worker threads."""
        for thread in self.threads:
            thread.quit()
            thread.wait()
