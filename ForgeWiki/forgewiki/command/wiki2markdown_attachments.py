from forgewiki.command.wiki2markdown_base import BaseImportUnit

class AttachmentsImportUnit(BaseImportUnit):
    def extract(self):
        raise NotImplementedError('add here data extraction')

    def load(self):
        raise NotImplementedError('add here data loading')
