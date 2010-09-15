import sys
from ming.orm import session
from pylons import c
from . import base
from allura.lib import helpers as h

class ScriptCommand(base.Command):
    min_args=2
    max_args=None
    usage = 'NAME <ini file> <script> ...'
    summary = 'Run a script as if it were being run at the paster shell prompt'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        with open(self.args[1]) as fp:
            ns = dict(__name__='__main__')
            sys.argv = self.args[1:]
            exec fp in ns

class SetToolAccessCommand(base.Command):
    min_args=3
    max_args=None
    usage = 'NAME <ini file> <project_shortname> <access_level>...'
    summary = ('Set the tool statuses that are permitted to be installed on a'
               ' given project')
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        h.set_context(self.args[1])
        extra_status = []
        for s in self.args[2:]:
            s = s.lower()
            if s=='production':
                print ('All projects always have access to prodcution tools,'
                       ' so removing from list.')
                continue
            if s not in ('alpha', 'beta'):
                print 'Unknown tool status %s' % s
                sys.exit(1)
            extra_status.append(s)
        print 'Setting project "%s" tool access to production + %r' % (
            self.args[1], extra_status)
        c.project._extra_tool_status = extra_status
        session(c.project).flush()
