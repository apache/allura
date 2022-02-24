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

import re
import logging
from itertools import groupby
import typing

from ming.odm.property import FieldProperty
from six.moves.cPickle import dumps, loads
from collections import defaultdict
from six.moves.urllib.parse import unquote

import bson
import pymongo
from tg import tmpl_context as c

from ming import schema as S
from ming.utils import LazyProperty
from ming.odm import session, MappedClass
from ming.odm import ForeignIdProperty, RelationProperty

from allura.lib import helpers as h

from .session import main_orm_session
from .project import Project
import six

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


log = logging.getLogger(__name__)


class ArtifactReference(MappedClass):
    class __mongometa__:
        session = main_orm_session
        name = 'artifact_reference'
        indexes = [
            'references',
            'artifact_reference.project_id',  # used in ReindexCommand
        ]

    query: 'Query[ArtifactReference]'

    _id = FieldProperty(str)
    artifact_reference = FieldProperty(dict(
        cls=S.Binary(),
        project_id=S.ObjectId(),
        app_config_id=S.ObjectId(),
        artifact_id=S.Anything(if_missing=None),
    ))
    references = FieldProperty([str])

    @classmethod
    def from_artifact(cls, artifact):
        '''Upsert logic to generate an ArtifactReference object from an artifact'''
        obj = cls.query.get(_id=artifact.index_id())
        if obj is not None:
            return obj
        try:
            obj = cls(
                _id=artifact.index_id(),
                artifact_reference=dict(
                    cls=bson.Binary(dumps(artifact.__class__, protocol=2)),
                    project_id=artifact.app_config.project_id,
                    app_config_id=artifact.app_config._id,
                    artifact_id=artifact._id))
            session(obj).flush(obj)
            return obj
        except pymongo.errors.DuplicateKeyError:  # pragma no cover
            session(obj).expunge(obj)
            return cls.query.get(_id=artifact.index_id())

    @LazyProperty
    def artifact(self):
        '''Look up the artifact referenced'''
        aref = self.artifact_reference
        try:
            cls = loads(bytes(aref.cls))
            with h.push_context(aref.project_id):
                return cls.query.get(_id=aref.artifact_id)
        except Exception:
            log.exception('Error loading artifact for %s: %r',
                          self._id, aref)


class Shortlink(MappedClass):
    '''Collection mapping shorthand_ids for artifacts to ArtifactReferences'''

    class __mongometa__:
        session = main_orm_session
        name = 'shortlink'
        indexes = [
            'ref_id',  # for from_artifact() and index_tasks.py:del_artifacts
            ('project_id', 'link',)  # used by from_links()  More helpful to have project_id first, for other queries
        ]

    query: 'Query[Shortlink]'

    _id = FieldProperty(S.ObjectId())
    ref_id: str = ForeignIdProperty(ArtifactReference)
    ref = RelationProperty(ArtifactReference)
    project_id = ForeignIdProperty('Project')
    project = RelationProperty('Project')
    app_config_id = ForeignIdProperty('AppConfig')
    app_config = RelationProperty('AppConfig')
    link = FieldProperty(str)
    url = FieldProperty(str)

    # Regexes used to find shortlinks
    _core_re = r'''(\[
            (?:(?P<project_id>.*?):)?      # optional project ID
            (?:(?P<app_id>.*?):)?      # optional tool ID
            (?P<artifact_id>.*)             # artifact ID
    \])'''
    re_link_1 = re.compile(r'\s' + _core_re, re.VERBOSE)
    re_link_2 = re.compile(r'^' + _core_re, re.VERBOSE)

    def __repr__(self):
        return '<Shortlink {} {} {} -> {}>'.format(
            self.project_id,
            self.app_config_id,
            self.link,
            self.ref_id)

    @classmethod
    def lookup(cls, link):
        return cls.from_links(link)[link]

    @classmethod
    def from_artifact(cls, a):
        result = cls.query.get(ref_id=a.index_id())
        if result is None:
            try:
                result = cls(
                    ref_id=a.index_id(),
                    project_id=a.app_config.project_id,
                    app_config_id=a.app_config._id)
                session(result).flush(result)
            except pymongo.errors.DuplicateKeyError:  # pragma no cover
                session(result).expunge(result)
                result = cls.query.get(ref_id=a.index_id())
        result.link = a.shorthand_id()
        result.url = a.url()
        if result.link is None:
            result.delete()
            return None
        return result

    @classmethod
    def from_links(cls, *links):
        '''Convert a sequence of shortlinks to the matching Shortlink objects'''
        if len(links):
            result = {}
            # Parse all the links
            parsed_links = {link: cls._parse_link(link)
                                for link in links}
            links_by_artifact = defaultdict(list)
            project_ids = set()
            for link, d in list(parsed_links.items()):
                if d:
                    project_ids.add(d['project_id'])
                    links_by_artifact[unquote(d['artifact'])].append(d)
                else:
                    result[link] = parsed_links.pop(link)
            q = cls.query.find(
                dict(
                    link={'$in': list(links_by_artifact.keys())},
                    project_id={'$in': list(project_ids)}
                ),
                validate=False,
                sort=[('_id', pymongo.DESCENDING)],  # if happen to be multiple (ticket move?) have newest first
            )
            matches_by_artifact = {
                link: list(matches)
                for link, matches in groupby(q, key=lambda s: unquote(s.link))}
            for link, d in parsed_links.items():
                matches = matches_by_artifact.get(unquote(d['artifact']), [])
                matches = (
                    m for m in matches
                    if m.project.shortname == d['project'] and
                    m.project.neighborhood_id == d['nbhd'] and
                    m.app_config is not None and
                    m.project.app_instance(m.app_config.options.mount_point))
                if d['app']:
                    matches = (
                        m for m in matches
                        if m.app_config.options.mount_point == d['app'])
                result[link] = cls._get_correct_match(link, list(matches))
            return result
        else:
            return {}

    @classmethod
    def _get_correct_match(cls, link, matches):
        result = None
        if len(matches) == 1:
            result = matches[0]
        elif len(matches) > 1 and getattr(c, 'app', None):
            # use current app's link
            for m in matches:
                if m.app_config_id == c.app.config._id:
                    result = m
                    break
            if not result:
                cls.log_ambiguous_link('Can not remove ambiguity for link %s with c.app %s', matches, link, c.app)
                result = matches[0]
        elif len(matches) > 1 and not getattr(c, 'app', None):
            cls.log_ambiguous_link('Ambiguous link to %s and c.app is not present to remove ambiguity', matches, link)
            result = matches[0]
        return result

    @classmethod
    def log_ambiguous_link(cls, msg, matches, *args):
        log.warn(msg, *args)
        for m in matches:
            log.warn('... %r', m)

    @classmethod
    def _parse_link(cls, s):
        '''Parse a shortlink into its nbhd/project/app/artifact parts'''
        s = s.strip()
        if s.startswith('['):
            s = s[1:]
        if s.endswith(']'):
            s = s[:-1]
        parts = s.split(':')
        p_shortname = None
        p_id = None
        p_nbhd = None
        if getattr(c, 'project', None):
            p_shortname = getattr(c.project, 'shortname', None)
            p_id = getattr(c.project, '_id', None)
            p_nbhd = c.project.neighborhood_id
        if len(parts) == 3:
            p = Project.query.get(shortname=parts[0], neighborhood_id=p_nbhd)
            if p:
                p_id = p._id
            return dict(
                nbhd=p_nbhd,
                project=parts[0],
                project_id=p_id,
                app=parts[1],
                artifact=parts[2])
        elif len(parts) == 2:
            return dict(
                nbhd=p_nbhd,
                project=p_shortname,
                project_id=p_id,
                app=parts[0],
                artifact=parts[1])
        elif len(parts) == 1:
            return dict(
                nbhd=p_nbhd,
                project=p_shortname,
                project_id=p_id,
                app=None,
                artifact=parts[0])
        else:
            return None
