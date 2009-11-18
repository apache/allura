class Application(object):
    'base pyforge pluggable application'
    __version__ = None
    default_config = {}
    templates=None

    def __init__(self, config):
        self.config = config

    def install(self, project):
        'Whatever logic is required to initially set up a plugin'
        pass

    def uninstall(self, project):
        'Whatever logic is required to tear down a plugin'
        pass
