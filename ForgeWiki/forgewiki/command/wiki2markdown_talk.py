from forgewiki.command.wiki2markdown import BaseImportUnit

class TalkImportUnit(BaseImportUnit):
    def __init__(self, options):
        self.options = options

    def extract(self):
        print "extract"

    def load(self):
        print "load"
