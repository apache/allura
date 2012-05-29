import base
from allura.command import base as allura_base

from pylons import c

from allura import model as M
from allura.lib import exceptions

class BaseImportUnit(object):
    def __init__(self, options):
        self.options = options

    def extract(self):
        raise NotImplementedError('subclass must override this method')

    def load(self):
        raise NotImplementedError('subclass must override this method')

class Wiki2MarkDown(base.WikiCommand):
    min_args=2
    max_args=None
    summary = 'Export mediawiki to markdown'
    all_import_units = [
        "pages",
        "history",
        "attachments",
        "talk"
    ]
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-e', '--extract-only', action='store_true', dest='extract',
                      help='Store data from the Allura mediawiki content on the local filesystem; not load into Allura')
    parser.add_option('-l', '--load-only', action='store_true', dest='load',
                      help='Load into Allura previously-extracted data')
    parser.add_option('-o', '--output-dir', dest='output_dir', default='',
                      help='directory for dump files')

    def command(self):
        self.basic_setup()

        if self.options.output_dir == '':
            allura_base.log.error("You must specify output directory")
            exit(2)

        if self.options.load is None and self.options.extract is None:
            allura_base.log.error('You must set action. Extract or load the data')
            exit(2)

        import_units = self.args[1:]
        if len(import_units) == 0:
            import_units = self.all_import_units
        else:
            for el in import_units:
                if el not in self.all_import_units:
                    allura_base.log.error("%s import unit was not found" % el)
                    exit(2)

        for uname in import_units:
            if uname == "pages":
                from forgewiki.command.wiki2markdown_pages import PagesImportUnit
                iu = PagesImportUnit(self.options)

            elif uname == "history":
                from forgewiki.command.wiki2markdown_history import HistoryImportUnit
                iu = HistoryImportUnit(self.options)

            elif uname == "attachments":
                from forgewiki.command.wiki2markdown_attachments import AttachmentsImportUnit
                iu = AttachmentsImportUnit(self.options)

            elif uname == "talk":
                from forgewiki.command.wiki2markdown_talk import TalkImportUnit
                iu = TalkImportUnit(self.options)

            if self.options.extract:
                iu.extract()
            elif self.options.load:
                iu.load()
