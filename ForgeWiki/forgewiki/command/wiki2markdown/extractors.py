import MySQLdb
import os
import shutil
import json
from allura.command import base as allura_base


class MediawikiExtractor(object):

    def __init__(self, options):
        self.options = options
        if os.path.exists(self.options.dump_dir):
            # clear dump_dir before extraction (there may be an old data)
            shutil.rmtree(self.options.dump_dir)
        os.makedirs(self.options.dump_dir)

    def extract(self):
        self.extract_pages()
        self.extract_history()
        self.extract_talk()
        self.extract_attachments()

    def extract_pages(self):
        raise NotImplementedError("subclass must override this")

    def extract_history(self):
        raise NotImplementedError("subclass must override this")

    def extract_talk(self):
        raise NotImplementedError("subclass must override this")

    def extract_attachments(self):
        raise NotImplementedError("subclass must override this")


class MySQLExtractor(MediawikiExtractor):

    def __init__(self, options):
        super(MySQLExtractor, self).__init__(options)
        self._connection = None
        self.db_options = {
            'host': self.options.host or 'localhost',
            'user': self.options.user,
            'passwd': self.options.password,
            'db': self.options.db_name,
            'port': self.options.port or 3306
        }

    def connection(self):
        if not self._connection:
            self._connection = MySQLdb.connect(**self.db_options)
        return self._connection

    def _save(self, content, *paths):
        out_file = os.path.join(self.options.dump_dir, *paths)
        if not os.path.exists(os.path.dirname(out_file)):
            os.makedirs(os.path.dirname(out_file))
        with open(out_file, 'w') as out:
            out.write(content.encode('utf-8'))

    def extract_pages(self):
        allura_base.log.info('Extracting pages...')
        c = self.connection().cursor()
        c.execute('select page.page_id, page.page_title, text.old_text '
                  'from page '
                  'left join revision on revision.rev_id = page.page_latest '
                  'left join text on text.old_id = revision.rev_text_id '
                  'where page.page_namespace = 0')
        for row in c:
            _id, title, text = row
            page = {
                'title': title,
                'text': text or ''
            }
            self._save(json.dumps(page), 'pages', str(_id) + '.json')

        allura_base.log.info('Extracting pages done')

    def extract_history(self):
        allura_base.log.info('extract_history not implemented yet. Skip.')

    def extract_talk(self):
        allura_base.log.info('extract_talk not implemented yet. Skip.')

    def extract_attachments(self):
        allura_base.log.info('extract_attachments not implemented yet. Skip.')
