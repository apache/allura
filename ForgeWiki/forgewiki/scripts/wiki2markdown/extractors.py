#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging
import os
import shutil
import json
import hashlib

log = logging.getLogger(__name__)


class MediawikiExtractor(object):
    """Base class for MediaWiki data provider"""

    def __init__(self, options):
        self.options = options
        if os.path.exists(self.options.dump_dir):
            # clear dump_dir before extraction (there may be an old data)
            shutil.rmtree(self.options.dump_dir)
        os.makedirs(self.options.dump_dir)

    def extract(self):
        """Extract pages with history, attachments, talk-pages, etc"""
        raise NotImplementedError("subclass must override this")


class MySQLExtractor(MediawikiExtractor):
    """Extract MediaWiki data to json.

    Use connection to MySQL database as a data source.
    """

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
        try:
            import MySQLdb
        except ImportError:
            raise ImportError('GPL library MySQL-python is required for this operation')

        if not self._connection:
            self._connection = MySQLdb.connect(**self.db_options)
        return self._connection

    def _save(self, content, *paths):
        """Save json to file in local filesystem"""
        out_file = os.path.join(self.options.dump_dir, *paths)
        if not os.path.exists(os.path.dirname(out_file)):
            os.makedirs(os.path.dirname(out_file))
        with open(out_file, 'w') as out:
            out.write(content.encode('utf-8'))

    def _save_attachment(self, filepath, *paths):
        """Save attachment in dump directory.

        Copy from mediawiki dump directory to our internal dump directory.

        args:
        filepath - path to attachment in mediawiki dump.
        *paths - path to internal dump directory.
        """
        out_dir = os.path.join(self.options.dump_dir, *paths)
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        shutil.copy(filepath, out_dir)

    def _pages(self):
        """Yield page_data for next wiki page"""
        c = self.connection().cursor()
        c.execute('select page.page_id, page.page_title '
                  'from page where page.page_namespace = 0')
        for row in c:
            _id, title = row
            page_data = {
                'page_id': _id,
                'title': title,
            }
            yield page_data

    def _history(self, page_id):
        """Yield page_data for next revision of wiki page"""
        c = self.connection().cursor()
        c.execute('select revision.rev_timestamp, text.old_text, '
                  'revision.rev_user_text '
                  'from revision '
                  'left join text on revision.rev_text_id = text.old_id '
                  'where revision.rev_page = %s', page_id)
        for row in c:
            timestamp, text, username = row
            page_data = {
                'timestamp': timestamp,
                'text': text or '',
                'username': username
            }
            yield page_data

    def _talk(self, page_title):
        """Return page_data for talk page with `page_title` title"""
        c = self.connection().cursor()
        query_attrs = (page_title, 1)  # page_namespace == 1 - talk pages
        c.execute('select text.old_text, revision.rev_timestamp, '
                  'revision.rev_user_text '
                  'from page '
                  'left join revision on revision.rev_id = page.page_latest '
                  'left join text on text.old_id = revision.rev_text_id '
                  'where page.page_title = %s and page.page_namespace = %s '
                  'limit 1', query_attrs)

        row = c.fetchone()
        if row:
            text, timestamp, username = row
            return {'text': text, 'timestamp': timestamp, 'username': username}

    def _attachments(self, page_id):
        """Yield path to next file attached to wiki page"""
        c = self.connection().cursor()
        c.execute('select il_to from imagelinks '
                  'where il_from = %s' % page_id)
        for row in c:
            name = row[0]
            # mediawiki stores attachmets in subdirectories
            # based on md5-hash of filename
            # so we need to build path to file as follows
            md5 = hashlib.md5(name).hexdigest()
            path = os.path.join(self.options.attachments_dir,
                               md5[:1], md5[:2], name)
            if os.path.isfile(path):
                yield path

    def extract(self):
        self.extract_pages()

    def extract_pages(self):
        log.info('Extracting pages...')
        for page in self._pages():
            self.extract_history(page)
            self.extract_talk(page)
            self.extract_attachments(page)
        log.info('Extracting pages done')

    def extract_history(self, page):
        page_id = page['page_id']
        for page_data in self._history(page_id):
            page_data.update(page)
            self._save(json.dumps(page_data), 'pages', str(page_id),
                       'history', str(page_data['timestamp']) + '.json')
        log.info('Extracted history for page %s (%s)', page_id, page['title'])

    def extract_talk(self, page):
        page_id = page['page_id']
        talk_page_data = self._talk(page['title'])
        if talk_page_data:
            self._save(json.dumps(talk_page_data), 'pages', str(page_id),
                       'discussion.json')
            log.info('Extracted talk for page %s (%s)', page_id, page['title'])
        else:
            log.info('No talk for page %s (%s)', page_id, page['title'])

    def extract_attachments(self, page):
        page_id = page['page_id']
        for filepath in self._attachments(page_id):
            self._save_attachment(filepath, 'pages', str(page_id),
                                  'attachments')
        log.info('Extracted attachments for page %s (%s)', page_id, page['title'])
