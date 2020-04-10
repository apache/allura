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

To call as a script::

    if __name__ == '__main__':
        MyScript.main()

To call as a task::

    # post the task with cmd-line-style args
    MyScript.post('-p myproject --dry-run')

"""

from __future__ import unicode_literals
from __future__ import absolute_import
import argparse
import logging

import six

from allura.lib.decorators import task
from allura.lib.helpers import shlex_split


log = logging.getLogger(__name__)


class MetaParserDocstring(type):
    @property
    def __doc__(cls):
        return cls.parser().format_help()

    def __new__(meta, classname, bases, classDict):
        return task(type.__new__(meta, classname, bases, classDict))


class ScriptTask(six.with_metaclass(MetaParserDocstring, object)):

    """Base class for a command-line script that is also executable as a task."""

    def __new__(cls, arg_string=''):
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
