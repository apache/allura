class BaseImportUnit(object):
    def __init__(self, options):
        self.options = options

    def extract(self):
        raise NotImplementedError('subclass must override this method')

    def load(self):
        raise NotImplementedError('subclass must override this method')
