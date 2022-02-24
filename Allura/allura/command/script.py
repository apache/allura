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

import sys
import os.path
import cProfile
import warnings

from tg import tmpl_context as c
import tg
import webob

from ming.orm import session
from allura.lib import helpers as h
from allura.lib import utils
from . import base


class ScriptCommand(base.Command):
    min_args = 2
    max_args = None
    usage = '<ini file> <script> ...'
    summary = 'Run a script as if it were being run at the paster shell prompt'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('--profile', action='store_true', dest='profile',
                      help='Dump profiling data to <script>.profile')
    parser.add_option('--pdb', action='store_true', dest='pdb',
                      help='Drop to a debugger on error')

    def command(self):
        with warnings.catch_warnings():
            try:
                from sqlalchemy import exc
            except ImportError:
                pass
            else:
                warnings.simplefilter("ignore", category=exc.SAWarning)
            self.basic_setup()
            request = webob.Request.blank('--script--', environ={
                'paste.registry': self.registry})
            tg.request_local.context.request = request
            if self.options.pdb:
                base.log.info('Installing exception hook')
                sys.excepthook = utils.postmortem_hook
            filename = self.args[1]
            with open(filename) as fp:
                ns = dict(__name__='__main__')
                sys.argv = self.args[1:]
                if self.options.profile:
                    cProfile.run(fp.read(), '%s.profile' %
                                 os.path.basename(filename))
                else:
                    exec(compile(fp.read(), filename, 'exec'), ns)


class SetToolAccessCommand(base.Command):
    min_args = 3
    max_args = None
    usage = '<ini file> <project_shortname> <neighborhood_name> <access_level>...'
    summary = ('Set the tool statuses that are permitted to be installed on a'
               ' given project')
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        h.set_context(self.args[1], neighborhood=self.args[2])
        extra_status = []
        for s in self.args[3:]:
            s = s.lower()
            if s == 'production':
                print ('All projects always have access to prodcution tools,'
                       ' so removing from list.')
                continue
            if s not in ('alpha', 'beta'):
                print('Unknown tool status %s' % s)
                sys.exit(1)
            extra_status.append(s)
        print('Setting project "{}" tool access to production + {!r}'.format(
            self.args[1], extra_status))
        c.project._extra_tool_status = extra_status
        session(c.project).flush()
