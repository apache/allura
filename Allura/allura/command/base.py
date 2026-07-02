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

import optparse
import os
import logging.config
import sys
import textwrap

import tg
from paste.deploy import appconfig
from paste.deploy.converters import asbool
from tg.support.registry import Registry
from tg.wsgiapp import RequestLocals

import activitystream
import ming
from allura.config.app_cfg import base_config
from allura.lib.decorators import task
from allura.lib import helpers as h
from allura.lib.utils import configure_ming

log = None


@task
def run_command(command, args):
    """Run an allura Command asynchronously"""
    mod, cls = command.rsplit('.', 1)
    mod = __import__(mod, fromlist=[str(cls)])
    command = getattr(mod, cls)
    command = command(command.__name__)
    arg_list = h.shlex_split(args or '')
    try:
        command.parser.parse_args(arg_list)
    except SystemExit:
        raise Exception("Error parsing args: '%s'" % args)
    return command.run(arg_list)


class EmptyClass:
    pass


class MetaParserDocstring(type):
    @property
    def __doc__(cls):
        return cls.parser.format_help()


class BadCommand(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


class Command(metaclass=MetaParserDocstring):
    # replacement for the old paste.script.command.Command, same API for the parts we use
    min_args = 1
    max_args = 1
    usage = '[<ini file>]'
    summary = ''
    description = None
    group_name = 'Allura'
    return_code = 0

    def __init__(self, name: str):
        self.command_name = name

    @classmethod
    def standard_parser(cls, verbose: bool = True) -> optparse.OptionParser:
        parser = optparse.OptionParser()
        if verbose:
            parser.add_option('-v', '--verbose', action='count', dest='verbose', default=0)
        return parser

    def run(self, args: list) -> int:
        self.parse_args(args)
        if self.min_args is not None and len(self.args) < self.min_args:
            raise BadCommand(f'You must provide at least {self.min_args} arguments')
        if self.max_args is not None and len(self.args) > self.max_args:
            raise BadCommand(f'You must provide no more than {self.max_args} arguments')
        self.verbose = getattr(self.options, 'verbose', 0)
        result = self.command()
        if result is None:
            return self.return_code
        else:
            return result

    def parse_args(self, args: list) -> None:
        usage = f' {self.usage}' if self.usage else ''
        self.parser.usage = f'%prog [options]{usage}\n{self.summary}'
        self.parser.prog = self._prog_name()
        if self.description:
            self.parser.description = textwrap.dedent(self.description)
        self.options, self.args = self.parser.parse_args(args)

    def _prog_name(self) -> str:
        return f'{os.path.basename(sys.argv[0])} {self.command_name}'

    @classmethod
    def post(cls, *args, **kw):
        cmd = f'{cls.__module__}.{cls.__name__}'
        return run_command.post(cmd, *args, **kw)

    @ming.utils.LazyProperty
    def registry(self):
        return Registry()

    @ming.utils.LazyProperty
    def globals(self):
        import allura.lib.app_globals
        return allura.lib.app_globals.Globals()

    @ming.utils.LazyProperty
    def config(self):
        import tg
        return tg.config

    def basic_setup(self):
        global log, M  # noqa: PLW0603
        if self.args[0]:
            # Probably being called from the command line - load the config
            # file
            self.config = conf = appconfig('config:%s' %
                                           self.args[0], relative_to=os.getcwd())
            # ... logging does not understand section#subsection syntax
            logging_config = self.args[0].split('#')[0]
            logging.config.fileConfig(
                logging_config, disable_existing_loggers=False)
            log = logging.getLogger('allura.command')
            log.info('Initialize command with config %r', self.args[0])
            conf = base_config.configure(conf.global_conf, conf.local_conf)
            base_config.setup(conf)
            self.setup_globals()
            from allura import model
            M = model
            configure_ming(conf)
            if asbool(conf.get('activitystream.recording.enabled', False)):
                activitystream.configure(**h.convert_bools(conf, prefix='activitystream.'))
            tg.tmpl_context.user = M.User.anonymous()
        else:
            # Probably being called from another script (websetup, perhaps?)
            log = logging.getLogger('allura.command')
            conf = tg.config

        self.tools = list(tg.app_globals.entry_points['tool'].values())

        conf['allura_command'] = self
        for ep in h.iter_entry_points('allura.command_init'):
            log.info('Running command_init for %s', ep.name)
            ep.load()(conf)
        log.info('Loaded tools')

    def setup_globals(self):
        import allura.lib.app_globals
        self.registry.prepare()
        self.registry.register(allura.credentials, allura.lib.security.Credentials())
        # turbogears has its own special magic wired up for its globals, can't use a regular Registry
        tgl = RequestLocals()
        tgl.tmpl_context = EmptyClass()
        tgl.app_globals = self.globals
        tg.request_local.context._push_object(tgl)

    def teardown_globals(self):
        self.registry.cleanup()
