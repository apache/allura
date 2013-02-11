"""
Provides ScriptTask, a base class for implementing a command-line script that
can be run as a task.

To use, subclass ScriptTask and implement two methods::

    class MyScript(ScriptTask):
        @classmethod
        def parser(cls):
            '''Define and return an argparse.ArgumentParser instance'''
            pass

        @classmethod
        def execute(cls, options):
            '''Your main code goes here.'''
            pass

To call as a script::

    if __name__ == '__main__':
        MyScript.main()

To call as a task::

    # post the task with cmd-line-style args
    MyScript.post('-p myproject --dry-run')

"""

import argparse
import copy_reg
import logging
import pickle
import sys
import types

from allura.lib.decorators import task


log = logging.getLogger(__name__)


# make methods picklable
def reduce_method(m):
    return (getattr, (m.__self__, m.__func__.__name__))
copy_reg.pickle(types.MethodType, reduce_method)


@task
def dispatcher(pickled_method, *args, **kw):
    method = pickle.loads(pickled_method)
    return method(*args, **kw)


class Writer(object):
    def __init__(self, func):
        self.func = func

    def write(self, buf):
        self.func(buf)


class ScriptTask(object):
    """Base class for a command-line script that is also executable as a task."""
    @classmethod
    def _execute_task(cls, arg_string):
        try:
            _stdout = sys.stdout
            _stderr = sys.stderr
            sys.stdout = Writer(log.info)
            sys.stderr = Writer(log.error)
            try:
                options = cls.parser().parse_args(arg_string.split(' '))
            except SystemExit:
                raise Exception("Error parsing args: '%s'" % arg_string)
            cls.execute(options)
        finally:
            sys.stdout = _stdout
            sys.stderr = _stderr

    @classmethod
    def execute(cls, options):
        """User code goes here."""
        pass

    @classmethod
    def parser(cls):
        """Return an argument parser appropriate for your script."""
        return argparse.ArgumentParser(description="Default no-op parser")

    @classmethod
    def post(cls, arg_string=''):
        pickled_method = pickle.dumps(cls._execute_task)
        return dispatcher.post(pickled_method, arg_string)

    @classmethod
    def main(cls):
        options = cls.parser().parse_args()
        cls.execute(options)
