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
import logging
import shlex
import sys

from allura.lib.decorators import task


log = logging.getLogger(__name__)


class Writer(object):
    def __init__(self, func):
        self.func = func

    def write(self, buf):
        self.func(buf)


class ScriptTask(object):
    """Base class for a command-line script that is also executable as a task."""

    class __metaclass__(type):
        @property
        def __doc__(cls):
            return cls.parser().format_help()
        def __new__(meta, classname, bases, classDict):
            return task(type.__new__(meta, classname, bases, classDict))

    def __new__(cls, arg_string):
        cls._execute_task(arg_string)

    @classmethod
    def _execute_task(cls, arg_string):
        try:
            _stdout = sys.stdout
            _stderr = sys.stderr
            sys.stdout = Writer(log.info)
            sys.stderr = Writer(log.error)
            try:
                options = cls.parser().parse_args(shlex.split(arg_string or ''))
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
    def main(cls):
        options = cls.parser().parse_args()
        cls.execute(options)
