from datetime import datetime
from random import randint

import pylons
pylons.c = pylons.tmpl_context
pylons.g = pylons.app_globals
from pylons import c, g
from pymongo.errors import DuplicateKeyError

from ming import schema
from ming.orm import FieldProperty, ForeignIdProperty, Mapper, session, state
from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

config = utils.ConfigProxy(
    common_suffix='forgemail.domain')

class MetricSnapshot(M.Snapshot):
    class __mongometa__:
        name='metric_snapshot'
    type_s='Metric Snapshot'

    def original(self):
        return Metric.query.get(_id=self.artifact_id)

    def shorthand_id(self):
        return '%s#%s' % (self.original().shorthand_id(), self.version)

    def url(self):
        return self.original().url() + '?version=%d' % self.version

    def index(self):
        result = super(MetricSnapshot, self).index()
        result.update(
            title_s='Version %d of %s' % (
                self.version, self.original().shorthand_id()),
            type_s=self.type_s,
            text=self.data.text)
        return result

    @property
    def html_text(self):
        """A markdown processed version of the page text"""
        return g.markdown_wiki.convert(self.data.text)

    @property
    def email_address(self):
        return self.original().email_address

class Metric(M.VersionedArtifact):
    class __mongometa__:
        name='metric'
        history_class = MetricSnapshot
        unique_indexes = [ ('project_id', 'app_config_id', 'slug') ]
    type_s = 'Metric'

    title = FieldProperty(str, if_missing='Untitled')
    text = FieldProperty(str, if_missing='')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)
    slug = FieldProperty(str)
    state = FieldProperty(schema.OneOf('draft', 'published'), if_missing='draft')
    neighborhood_id = ForeignIdProperty('Neighborhood', if_missing=None)

    def author(self):
        '''The author of the first snapshot of this Metric'''
        return M.User.query.get(_id=self.get_version(1).author.id) or M.User.anonymous()

    def _get_date(self):
        return self.timestamp.date()
    def _set_date(self, value):
        self.timestamp = datetime.combine(value, self.time)
    date = property(_get_date, _set_date)

    def _get_time(self):
        return self.timestamp.time()
    def _set_time(self, value):
        self.timestamp = datetime.combine(self.date, value)
    time = property(_get_time, _set_time)

    @property
    def html_text(self):
        return g.markdown.convert(self.text)


    @property
    def email_address(self):
        domain = '.'.join(reversed(self.app.url[1:-1].split('/'))).replace('_', '-')
        return '%s@%s%s' % (self.title.replace('/', '.'), domain, config.common_suffix)

    def make_slug(self):
        slugsafe = ''.join(
            ch.lower()
            for ch in self.title.replace(' ', '-')
            if ch.isalnum() or ch == '-')
        base = '%s/%s' % (
            self.timestamp.strftime('%Y/%m'),
            slugsafe)
        self.slug = base
        while True:
            try:
                session(self).insert_now(self, state(self))
                return self.slug
            except DuplicateKeyError:
                self.slug = base + '-%.3d' % randint(0,999)
                return self.slug

    def url(self):
        return self.app.url + self.slug + '/'

    def shorthand_id(self):
        return self.slug

    def index(self):
        result = super(Metric, self).index()
        result.update(
            title_s=self.slug,
            type_s=self.type_s,
            state_s=self.state,
            snippet_s='%s: %s' % (self.title, h.text.truncate(self.text, 200)),
            text=self.text)
        return result

    def get_version(self, version):
        HC = self.__mongometa__.history_class
        return HC.query.find({'artifact_id':self._id, 'version':int(version)}).one()

    def commit(self):
        self.subscribe()
        super(Metric, self).commit()
        description = self.text
        subject = '%s created metric %s' % (
            c.user.username, self.title)
        if self.state == 'published':
            M.Notification.post(
                artifact=self, topic='metadata', text=description, subject=subject)

Mapper.compile_all()
