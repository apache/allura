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

import sys
from collections import defaultdict
from contextlib import contextmanager
from itertools import groupby

from paste.deploy.converters import asbool
from tg import tmpl_context as c, app_globals as g
from pymongo.errors import DuplicateKeyError, InvalidDocument, OperationFailure

from ming.orm import mapper, session, Mapper
from ming.orm.declarative import MappedClass

from allura.tasks.index_tasks import add_artifacts
from allura.lib.exceptions import CompoundError
from allura.lib import helpers as h
from allura.lib import utils
from . import base
import six


class ShowModelsCommand(base.Command):
    min_args = 1
    max_args = 1
    usage = '<ini file>'
    summary = 'Show the inheritance graph of all Ming models'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        graph = build_model_inheritance_graph()
        for depth, cls in dfs(MappedClass, graph):
            for line in dump_cls(depth, cls):
                print(line)


class ReindexCommand(base.Command):
    min_args = 1
    max_args = 1
    usage = '<ini file>'
    summary = 'Reindex into solr and re-shortlink all artifacts\n' \
              'By default both --refs and --tasks are enabled, but if you specify just one, the other will be disabled'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--project', dest='project',  default=None,
                      help='project to reindex')
    parser.add_option('--project-regex', dest='project_regex', default='',
                      help='Restrict reindex to projects for which the shortname matches '
                      'the provided regex.')
    parser.add_option(
        '-n', '--neighborhood', dest='neighborhood', default=None,
        help='neighborhood to reindex (e.g. p)')

    parser.add_option('--solr', action='store_true', dest='solr',
                      help='Solr needs artifact references to already exist.')
    parser.add_option(
        '--skip-solr-delete', action='store_true', dest='skip_solr_delete',
        help='Skip clearing solr index.')
    parser.add_option('--refs', action='store_true', dest='refs',
                      help='Update artifact references and shortlinks')
    parser.add_option('--tasks', action='store_true', dest='tasks',
                      help='Run each individual index operation as a background task.  '
                           'Note: this is often better, since tasks have "request" objects '
                           'which are needed for some markdown macros to run properly')
    parser.add_option('--solr-hosts', dest='solr_hosts',
                      help='Override the solr host(s) to post to.  Comma-separated list of solr server URLs')
    parser.add_option(
        '--max-chunk', dest='max_chunk', type=int, default=100 * 1000,
        help='Max number of artifacts to index in one Solr update command')
    parser.add_option('--ming-config', dest='ming_config', help='Path (absolute, or relative to '
                      'Allura root) to .ini file defining ming configuration.')

    def command(self):
        from allura import model as M
        self.basic_setup()
        graph = build_model_inheritance_graph()
        if self.options.project:
            q_project = dict(shortname=self.options.project)
        elif self.options.project_regex:
            q_project = dict(shortname={'$regex': self.options.project_regex})
        elif self.options.neighborhood:
            neighborhood_id = M.Neighborhood.query.get(
                url_prefix='/%s/' % self.options.neighborhood)._id
            q_project = dict(neighborhood_id=neighborhood_id)
        else:
            q_project = {}

        # if none specified, do all
        if not self.options.solr and not self.options.refs:
            self.options.solr = self.options.refs = True

        for projects in utils.chunked_find(M.Project, q_project):
            for p in projects:
                c.project = p
                base.log.info('Reindex project %s', p.shortname)
                # Clear index for this project
                if self.options.solr and not self.options.skip_solr_delete:
                    g.solr.delete(q='project_id_s:%s' % p._id)
                if self.options.refs:
                    M.ArtifactReference.query.remove(
                        {'artifact_reference.project_id': p._id})
                    M.Shortlink.query.remove({'project_id': p._id})
                app_config_ids = [ac._id for ac in p.app_configs]
                # Traverse the inheritance graph, finding all artifacts that
                # belong to this project
                for _, a_cls in dfs(M.Artifact, graph):
                    base.log.info('  %s', a_cls)
                    ref_ids = []
                    # Create artifact references and shortlinks
                    for a in a_cls.query.find(dict(app_config_id={'$in': app_config_ids})):
                        if self.options.verbose:
                            base.log.info('      %s', a.shorthand_id())
                        if self.options.refs:
                            try:
                                M.ArtifactReference.from_artifact(a)
                                M.Shortlink.from_artifact(a)
                            except Exception:
                                base.log.exception(
                                    'Making ArtifactReference/Shortlink from %s', a)
                                continue
                        ref_ids.append(a.index_id())
                    M.main_orm_session.flush()
                    M.artifact_orm_session.clear()
                    try:
                        self._chunked_add_artifacts(ref_ids)
                    except CompoundError as err:
                        base.log.exception(
                            'Error indexing artifacts:\n%r', err)
                        base.log.error('%s', err.format_error())
                    M.main_orm_session.flush()
                    M.main_orm_session.clear()
        base.log.info('Reindex %s', 'queued' if self.options.tasks else 'done')

    @property
    def add_artifact_kwargs(self):
        if self.options.solr_hosts:
            return {'solr_hosts': self.options.solr_hosts.split(',')}
        return {}

    def _chunked_add_artifacts(self, ref_ids):
        # ref_ids contains solr index ids which can easily be over
        # 100 bytes. Here we allow for 160 bytes avg, plus
        # room for other document overhead.
        for chunk in utils.chunked_list(ref_ids, self.options.max_chunk):
            if self.options.tasks:
                self._post_add_artifacts(chunk)
            else:
                add_artifacts(chunk,
                              update_solr=self.options.solr,
                              update_refs=self.options.refs,
                              **self.add_artifact_kwargs)

    def _post_add_artifacts(self, chunk):
        """
        Post task, recursively splitting and re-posting if the resulting
        mongo document is too large.
        """
        try:
            with self.ming_config(self.options.ming_config):
                add_artifacts.post(chunk,
                                   update_solr=self.options.solr,
                                   update_refs=self.options.refs,
                                   **self.add_artifact_kwargs)
        except InvalidDocument as e:
            # there are many types of InvalidDocument, only recurse if its
            # expected to help
            if e.args[0].startswith('BSON document too large'):
                self._post_add_artifacts(chunk[:len(chunk) // 2])
                self._post_add_artifacts(chunk[len(chunk) // 2:])
            else:
                raise

    @property
    def ming_config(self):
        """Return a contextmanager for the provided ming config, if there is
        one.

        Otherwise return a no-op contextmanager.

        """
        def noop_cm(*args):
            yield

        if self.options.ming_config:
            return h.ming_config_from_ini
        return contextmanager(noop_cm)


class EnsureIndexCommand(base.Command):
    min_args = 1
    max_args = 1
    usage = '[<ini file>]'
    summary = 'Create all the Mongo indexes specified by Ming models'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('--clean', action='store_true', dest='clean',
                      help='Drop any unneeded indexes')

    def command(self):
        from allura import model as M
        main_session_classes = [M.main_orm_session, M.repository_orm_session,
                                M.task_orm_session, M.main_explicitflush_orm_session]
        if asbool(self.config.get('activitystream.recording.enabled', False)):
            from activitystream.storage.mingstorage import activity_odm_session
            main_session_classes.append(activity_odm_session)
        self.basic_setup()
        # by db, then collection name
        main_indexes = defaultdict(lambda: defaultdict(list))
        project_indexes = defaultdict(list)  # by collection name
        base.log.info('Collecting indexes...')
        for m in Mapper.all_mappers():
            mgr = m.collection.m
            cname = mgr.collection_name
            cls = m.mapped_class
            if cname is None:
                base.log.info('... skipping abstract class %s', cls)
                continue
            base.log.info('... for class %s', cls)
            if session(cls) in main_session_classes:
                idx = main_indexes[session(cls)][cname]
            else:
                idx = project_indexes[cname]
            idx.extend(mgr.indexes)
        base.log.info('Updating indexes for main DB')
        for odm_session, db_indexes in main_indexes.items():
            db = odm_session.impl.db
            for name, indexes in db_indexes.items():
                self._update_indexes(db[name], indexes)
        base.log.info('Updating indexes for project DB')
        db = M.project_doc_session.db
        base.log.info('... DB: %s', db)
        for name, indexes in project_indexes.items():
            self._update_indexes(db[name], indexes)
        base.log.info('Done updating indexes')

    def _update_indexes(self, collection, indexes):
        uindexes = {
            # convert list to tuple so it's hashable for 'set'
            tuple(i.index_spec): i
            for i in indexes
            if i.unique}
        indexes = {
            tuple(i.index_spec): i
            for i in indexes
            if not i.unique}
        prev_indexes = {}
        prev_uindexes = {}
        unique_flag_drop = {}
        unique_flag_add = {}
        try:
            existing_indexes = collection.index_information().items()
        except OperationFailure:
            # exception is raised if db or collection doesn't exist yet
            existing_indexes = {}
        for iname, fields in existing_indexes:
            if iname == '_id_':
                continue
            keys = tuple(fields['key'])
            if fields.get('unique'):
                if keys in indexes:
                    unique_flag_drop[iname] = keys
                else:
                    prev_uindexes[iname] = keys
            else:
                if keys in uindexes:
                    unique_flag_add[iname] = keys
                else:
                    prev_indexes[iname] = keys

        for iname, keys in unique_flag_drop.items():
            self._recreate_index(collection, iname, list(keys), unique=False)
        for iname, keys in unique_flag_add.items():
            self._recreate_index(collection, iname, list(keys), unique=True)

        # Ensure all indexes
        for keys, idx in uindexes.items():
            base.log.info('...... ensure %s:%s', collection.name, idx)
            while True:
                try:
                    index_options = idx.index_options.copy()
                    if idx.fields == ('_id',):
                        # as of mongo 3.4 _id fields can't have these options set
                        # _id is always non-sparse and unique anyway
                        del index_options['sparse']
                        del index_options['unique']
                    collection.ensure_index(idx.index_spec, **index_options)
                    break
                except DuplicateKeyError as err:
                    base.log.info('Found dupe key(%s), eliminating dupes', err)
                    self._remove_dupes(collection, idx.index_spec)
        for keys, idx in indexes.items():
            base.log.info('...... ensure %s:%s', collection.name, idx)
            collection.ensure_index(idx.index_spec, background=True, **idx.index_options)
        # Drop obsolete indexes
        for iname, keys in prev_indexes.items():
            if keys not in indexes:
                if self.options.clean:
                    base.log.info('...... drop index %s:%s', collection.name, iname)
                    collection.drop_index(iname)
                else:
                    base.log.info('...... potentially unneeded index, could be removed by running with --clean %s:%s',
                                  collection.name, iname)
        for iname, keys in prev_uindexes.items():
            if keys not in uindexes:
                if self.options.clean:
                    base.log.info('...... drop index %s:%s', collection.name, iname)
                    collection.drop_index(iname)
                else:
                    base.log.info('...... potentially unneeded index, could be removed by running with --clean %s:%s',
                                  collection.name, iname)

    def _recreate_index(self, collection, iname, keys, **creation_options):
        '''Recreate an index with new creation options, using a temporary index
        so that at no time is an index missing from the specified keys'''
        superset_keys = keys + [('temporary_extra_field_for_indexing', 1)]
        base.log.info('...... ensure index %s:%s',
                      collection.name, superset_keys)
        superset_index = collection.ensure_index(superset_keys)
        base.log.info('...... drop index %s:%s', collection.name, iname)
        collection.drop_index(iname)
        base.log.info('...... ensure index %s:%s %s',
                      collection.name, keys, creation_options)
        collection.ensure_index(keys, **creation_options)
        base.log.info('...... drop index %s:%s',
                      collection.name, superset_index)
        collection.drop_index(superset_index)

    def _remove_dupes(self, collection, spec):
        iname = collection.create_index(spec)
        fields = [f[0] for f in spec]
        q = collection.find({}, projection=fields).sort(spec)

        def keyfunc(doc):
            return tuple(doc.get(f, None) for f in fields)
        dupes = []
        for key, doc_iter in groupby(q, key=keyfunc):
            docs = list(doc_iter)
            if len(docs) > 1:
                base.log.info('Found dupes with %s', key)
                dupes += [doc['_id'] for doc in docs[1:]]
        collection.drop_index(iname)
        collection.remove(dict(_id={'$in': dupes}))


def build_model_inheritance_graph():
    graph = {m.mapped_class: ([], []) for m in Mapper.all_mappers()}
    for cls, (parents, children) in graph.items():
        for b in cls.__bases__:
            if b not in graph:
                continue
            parents.append(b)
            graph[b][1].append(cls)
    return graph


def dump_cls(depth, cls):
    indent = ' ' * 4 * depth
    yield indent + f'{cls.__module__}.{cls.__name__}'
    m = mapper(cls)
    for p in m.properties:
        s = indent * 2 + ' - ' + str(p)
        if hasattr(p, 'field_type'):
            s += ' (%s)' % p.field_type
        yield s


def dfs(root, graph, depth=0):
    yield depth, root
    for node in graph[root][1]:
        yield from dfs(node, graph, depth + 1)
