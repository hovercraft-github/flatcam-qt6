# ########################################################## ##
# FlatCAM: 2D Post-processing for Manufacturing            #
# http://flatcam.org                                       #
# Author: Juan Pablo Caram (c)                             #
# Date: 2/5/2014                                           #
# MIT Licence                                              #
# ########################################################## ##

from PyQt6 import QtCore
import traceback


class Worker(QtCore.QObject):
    """
    Implements a queue of tasks to be carried out in order
    in a single independent thread.
    """

    # avoid multiple tests  for debug availability
    pydevd_failed = False
    task_completed = QtCore.pyqtSignal(str)
    # Per-worker signal for direct dispatch (eliminates broadcast fan-out)
    worker_task_signal = QtCore.pyqtSignal(dict)

    def __init__(self, app, name=None):
        super(Worker, self).__init__()
        self.app = app
        self.name = name

    def allow_debug(self):
        """
         allow debuging/breakpoints in this threads
         should work from PyCharm and PyDev
        :return:
        """

        if not self.pydevd_failed:
            try:
                import pydevd
                pydevd.settrace(suspend=False, trace_only_current_thread=True)
            except ImportError:
                self.pydevd_failed = True

    def run(self):

        # self.app.log.debug("Worker Started!")

        self.allow_debug()

        # Connect to own per-worker signal (no broadcast, no worker_name check needed)
        self.worker_task_signal.connect(self.do_worker_task)

    def do_worker_task(self, task):

        # self.app.log.debug("Running task: %s" % str(task))

        self.allow_debug()

        # No need to check worker_name - only receives own tasks via direct dispatch
        try:
            task['fcn'](*task['params'])
        except Exception as e:
            self.app.thread_exception.emit(e)
            print(traceback.format_exc())
            # raise e
        finally:
            self.task_completed.emit(self.name)

        # self.app.log.debug("Task ignored.")
