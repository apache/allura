import sys
from . import base

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
