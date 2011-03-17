import re
import logging
from itertools import groupby
from cPickle import dumps, loads
from datetime import datetime
from collections import defaultdict

import pymongo
from pylons import c, g

import ming
from ming import schema as S
from ming.utils import LazyProperty
from ming.orm import MappedClass, session
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty

from allura.lib import helpers as h
from allura.lib.search import find_shortlinks, solarize

from .session import main_orm_session

log = logging.getLogger(__name__)

class ArtifactReference(MappedClass):
    '''ArtifactReference manages the artifact graph.

    fields are all strs, corresponding to Solr index_ids
    '''
    class __mongometa__:
        session = main_orm_session
        name = 'artifact_reference'
        indexes = [ 'references' ]

    _id = FieldProperty(str)
    artifact_reference = S.Object(dict(
            cls=S.Binary,
            project_id=S.ObjectId,
            app_config_id=S.ObjectId,
            artifact_id=S.Anything(if_missing=None)))
    references = FieldProperty([str])

    @classmethod
    def from_artifact(cls, artifact):
        '''Upsert logic to generate an ArtifactReference object from an artifact'''
        cls = dumps(artifact.__class__)
        obj = cls.query.get(_id=artifact.index_id())
        if obj is not None: return obj
        try:
            obj = cls(
                _id=artifact.index_id(),
                artifact_reference=dict(
                    cls=dumps(artifact.__class__),
                    project_id=artifact.app_config.project_id,
                    app_config_id=artifact.app_config._id,
                    artifact_id=artifact._id))
            session(obj).flush_now(obj)
            return obj
        except pymongo.errors.DuplicateKeyError: # pragma no cover
            session(obj).expunge(obj)
            return cls.query.get(_id=artifact.index_id())

    @LazyProperty
    def artifact(self):
        '''Look up the artifact referenced'''
        aref = self.artifact_reference
        try:
            cls = loads(str(aref.artifact_type))
            with h.push_context(aref.project_id):
                return cls.query.get(_id=aref.artifact_id)
        except:
            log.exception('Error loading artifact for %s: %r',
                          self._id, aref)

class Shortlink(MappedClass):
    '''Collection mapping shorthand_ids for artifacts to ArtifactReferences'''
    class __mongometa__:
        session = main_orm_session
        name = 'shortlink'
        indexes = [ ('link', 'project_id', 'app_config_id') ]

    # Stored properties
    _id = FieldProperty(S.ObjectId)
    ref_id = ForeignIdProperty(ArtifactReference)
    project_id = ForeignIdProperty('Project')
    app_config_id = ForeignIdProperty('AppConfig')
    link = FieldProperty(str)

    # Relation Properties
    project = RelationProperty('Project')
    app_confit = RelationProperty('AppConfig')
    ref = RelationProperty('ArtifactReference')

    # Regexes used to find shortlinks
    _core_re = r'''(\[
            (?:(?P<project_id>.*?):)?      # optional project ID
            (?:(?P<app_id>.*?):)?      # optional tool ID
            (?P<artifact_id>.*)             # artifact ID
    \])'''
    re_link_1 = re.compile(r'\s' + _core_re, re.VERBOSE)
    re_link_2 = re.compile(r'^' +  _core_re, re.VERBOSE)

    def __repr__(self):
        return '[%s:%s:%s]' % (
            self.project.shortname,
            self.app_config.options.mount_point)

    @classmethod
    def lookup(cls, link):
        return cls.from_links(link)[link]

    @classmethod
    def from_artifact(cls, a):
        return cls(
            ref_id = a.index_id(),
            project_id = a.app_config.project_id,
            app_config_id = a.app_config._id,
            link = a.shorthand_id())

    @classmethod
    def from_links(cls, *links):
        '''Convert a sequence of shortlinks to the matching Shortlink objects'''
        # Parse all the links
        parsed_links = dict((link, cls._parse_link(link)) for link in links)
        links_by_artifact = defaultdict(list)
        for link, d in parsed_links.iteritems():
            links_by_artifact[d['artifact']].append(d)

        q = cls.query.find(dict(
                link={'$in': links_by_artifact.keys()}))
        q = q.sort('link')
        result = {}
        matches_by_artifact = dict(
            (link, list(matches))
            for link, matches in groupby(q, keyfunc=lambda s:s.link))
        result = {}
        for link, d in parsed_links.iteritems():
            matches = matches_by_artifact[d['artifact']]
            matches = (
                m for m in matches
                if m.project.shortname == d['project'] )
            if d['app']:
                matches = (
                    m for m in matches
                    if m.app_config.options.mount_point == d['app'])
            matches = list(matches)
            if matches:
                result[link] = matches[0]
            else:
                result[link] = None
            if len(matches) > 1:
                log.warn('Ambiguous link to %s', link)
                for m in matches:
                    log.warn('... %r', m)
        return result

    @classmethod
    def _parse_link(cls, s):
        '''Parse a shortlink into its project/app/artifact parts'''
        s = s.strip()
        if s.startswith('['):
            s = s[1:]
        if s.endswith(']'):
            s = s[:-1]
        parts = s.split(':')
        if len(parts) == 3:
            return dict(
                project=parts[0],
                app=parts[1],
                artifact=parts[2])
        elif len(parts) == 2:
            return dict(
                project=c.project.shortname,
                app=parts[0],
                artifact=parts[1])
        elif len(parts) == 1:
            return dict(
                project=c.project.shortname,
                app=None,
                artifact=parts[0])
        else:
            return None

class IndexOp(MappedClass):
    '''Queued operations for offline indexing.
    '''
    class __mongometa__:
        session = main_orm_session
        name = 'monq_task'
        indexes = [
           [ ('worker', ming.ASCENDING),
             ('ref_id', ming.ASCENDING),
             ('timestamp', ming.DESCENDING),
             ],
           ]

    _id = FieldProperty(S.ObjectId)
    op = FieldProperty(S.OneOf('add', 'del'))
    worker = FieldProperty(str, if_missing=None)
    ref_id = ForeignIdProperty('ArtifactReference')
    timestamp = FieldProperty(datetime, if_missing=datetime.utcnow)

    ref = RelationProperty('ArtifactReference')

    def __repr__(self):
        return '<%s %s (%s) @%s>' % (
            self.op, self.ref_id, self.worker, self.timestamp.isoformat())

    @classmethod
    def add_op(cls, artifact):
        return cls(op='add', ref_id=artifact.index_id())

    @classmethod
    def del_op(cls, artifact):
        return cls(op='del', ref_id=artifact.index_id())

    @classmethod
    def lock_ops(cls, worker):
        '''Lock all the outstanding indexops to the given worker'''
        cls.query.update(
            dict(worker=None),
            {'$set': dict(worker=worker)},
            multi=True)

    @classmethod
    def remove_ops(cls, worker):
        '''Remove all the ops locked by the given worker'''
        cls.query.remove(dict(worker=worker))

    @classmethod
    def unlock_ops(cls, worker):
        '''Unlock all the outstanding indexops to the given worker

        Generally only used if the worker dies.
        '''
        cls.query.update(
            dict(worker=worker),
            {'$set': dict(worker=None)},
            multi=True)

    @classmethod
    def find_ops(cls, worker):
        '''Return the most relevant ops locked by worker

        This method will only return the most recent op for a particular
        artifact (which is what you actually want).
        '''
        q = (cls
             .find(dict(worker=worker))
             .sort('ref_id')
             .sort('timestamp', ming.DESCENDING))
        for ref_id, ops in groupby(q, keyfunc=lambda o: o.ref_id):
            yield ops.next()

    def __call__(self):
        from allura.model.artifact import Snapshot
        try:
            if self.op == 'add':
                artifact = self.ref.artifact
                s = solarize(artifact)
                if s is not None: g.solr.add([s])
                if not isinstance(artifact, Snapshot):
                    self.ref.references = [
                        link.ref_id for link in find_shortlinks(s['text']) ]
                Shortlink.from_artifact(artifact)
            else:
                g.solr.delete(id=self.ref_id)
                ArtifactReference.query.remove(dict(_id=self.ref_id))
                Shortlink.query.remove(dict(ref_id=self.ref_id))
        except:
            log.exception('Error with %r', self)
            self.worker = 'ERROR'
            session(self).flush(self)
