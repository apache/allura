class Application(object):
    'base pyforge pluggable application'
    __version__ = None
    default_config = {}
    templates=None
    root=None  # root controller
    admin=None # admin controller

    def __init__(self, config):
        self.config = config # pragma: no cover

    def install(self, project):
        'Whatever logic is required to initially set up a plugin'
        pass # pragma: no cover

    def uninstall(self, project):
        'Whatever logic is required to tear down a plugin'
        pass # pragma: no cover
