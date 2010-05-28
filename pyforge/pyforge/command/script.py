from . import base

class ScriptCommand(base.Command):
    min_args=2
    max_args=2
    usage = 'NAME <ini file> <script>'
    summary = 'Run a script as if it were being run at the paster shell prompt'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        with open(self.args[1]) as fp:
            exec fp
