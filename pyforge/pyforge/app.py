class Application(object):
    'base pyforge pluggable application'
    default_config = {}

    def __init__(self, config):
        self.config = config
