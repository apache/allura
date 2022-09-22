#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

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

Or using the `defopt library <https://defopt.readthedocs.io/>`_ (must be installed),
subclass `DefOptScriptTask` and implement one method::

    class MyScript(DefOptScriptTask):
        @classmethod
        def execute(cls, *, limit: int = 10, dry_run: bool = False):
            '''
            Description/usage of this script

            :param limit:
                Explanation of parametes, if desired
            '''
            pass

To call as a script::

    if __name__ == '__main__':
        MyScript.main()

To run as a background task::

    # post the task with cmd-line-style args
    MyScript.post('-p myproject --dry-run')

"""

import argparse
import contextlib
import io
import logging

from allura.lib.decorators import task
from allura.lib.helpers import shlex_split


log = logging.getLogger(__name__)


class MetaParserDocstring(type):
    @property
    def __doc__(cls):
        return cls.parser().format_help()

    def __new__(meta, classname, bases, classDict):
        # make it look like a task
        return task(type.__new__(meta, classname, bases, classDict))


class ScriptTask(metaclass=MetaParserDocstring):

    """Base class for a command-line script that is also executable as a task."""

    def __new__(cls, arg_string=''):
        # when taskd calls SomeTaskClass(), then this runs.  Not really the normal way to use __new__
        # and can't use __init__ since we want to return a value
        return cls._execute_task(arg_string)

    @classmethod
    def _execute_task(cls, arg_string):
        try:
            options = cls.parser().parse_args(shlex_split(arg_string or ''))
        except SystemExit:
            raise Exception("Error parsing args: '%s'" % arg_string)
        return cls.execute(options)

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


try:
    import defopt
except ModuleNotFoundError:
    pass
else:

    class MetaDefOpt(type):
        def __new__(meta, classname, bases, classDict):
            return task(type.__new__(meta, classname, bases, classDict))

        @property
        def __doc__(cls):
            with contextlib.redirect_stdout(io.StringIO()) as stderr:
                try:
                    cls.main(argv=['--help'])
                except SystemExit:
                    pass
            return stderr.getvalue()


    class DefOptScriptTask(metaclass=MetaDefOpt):
        """Base class for a command-line script that is also executable as a task."""

        def __new__(cls, arg_string=''):
            # when taskd calls SomeTaskClass(), then this runs.  Not really the normal way to use __new__
            # and can't use __init__ since we want to return a value
            return cls._execute_task(arg_string)

        @classmethod
        def _execute_task(cls, arg_string):
            try:
                return cls.main(argv=shlex_split(arg_string or ''))
            except SystemExit:
                raise Exception("Error parsing args: '%s'" % arg_string)

        @classmethod
        def main(cls, **extra_kwargs):
            return defopt.run(cls.execute, no_negated_flags=True, **extra_kwargs)

        @classmethod
        def execute(cls, *args, **kwargs):
            """User code goes here, using defopt kwargs with type annotations"""
            raise NotImplementedError

