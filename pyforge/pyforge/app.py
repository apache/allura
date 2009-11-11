class Application(object):
    'base pyforge pluggable application'
    default_config = {}

    def __init__(self, config):
        self.config = config

    def install(self, project):
        'Whatever logic is required to initially set up a plugin'
        pass

    def uninstall(self, project):
        'Whatever logic is required to tear down a plugin'
        pass
