from forgewiki.command.wiki2markdown_base import BaseImportUnit

class HistoryImportUnit(BaseImportUnit):
    def __init__(self, options):
        self.options = options

    def extract(self):
        raise NotImplementedError('add here data extraction')

    def load(self):
        raise NotImplementedError('add here data loading')
