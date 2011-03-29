import sys
from collections import defaultdict

from tg import c, g

from ming.orm import MappedClass, mapper

import allura.tasks.index_tasks
from allura.lib.exceptions import CompoundError
from allura.lib import utils
from . import base

class ShowModelsCommand(base.Command):
    min_args=1
    max_args=1
    usage = '<ini file>'
    summary = 'Show the inheritance graph of all Ming models'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        graph = build_model_inheritance_graph()
        for depth, cls in dfs(MappedClass, graph):
            for line in dump_cls(depth, cls):
                print line

class ReindexCommand(base.Command):
    min_args=0
    max_args=1
    usage = '<ini file>'
    summary = 'Reindex and re-shortlink all artifacts'
    parser = base.Command.standard_parser(verbose=True)
    parser.add_option('-p', '--project', dest='project',  default=None,
                      help='project to reindex')
    parser.add_option('-n', '--neighborhood', dest='neighborhood', default=None,
                      help='neighborhood to reindex (e.g. p)')

    parser.add_option('--solr', action='store_true', dest='solr',
                      help='Solr needs artifact references to already exist.')
    parser.add_option('--refs', action='store_true', dest='refs',
                      help='Update artifact references and shortlinks')

    def command(self):
        from allura import model as M
        self.basic_setup()
        graph = build_model_inheritance_graph()
        if self.options.project:
            q_project = dict(shortname=self.options.project)
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
                if self.options.solr:
                    g.solr.delete(q='project_id_s:%s' % p._id)
                if self.options.refs:
                    M.ArtifactReference.query.remove({'artifact_reference.project_id':p._id})
                    M.Shortlink.query.remove({'project_id':p._id})
                app_config_ids = [ ac._id for ac in p.app_configs ]
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
                            except:
                                base.log.exception('Making ArtifactReference/Shortlink from %s', a)
                                continue
                        ref_ids.append(a.index_id())
                    M.main_orm_session.flush()
                    M.artifact_orm_session.clear()
                    try:
                        allura.tasks.index_tasks.add_artifacts(ref_ids,
                                                               update_solr=self.options.solr,
                                                               update_refs=self.options.refs)
                    except CompoundError, err:
                        base.log.exception('Error indexing artifacts:\n%r', err)
                        base.log.error('%s', err.format_error())
                    M.main_orm_session.flush()
                    M.main_orm_session.clear()
        base.log.info('Reindex done')

class EnsureIndexCommand(base.Command):
    min_args=0
    max_args=1
    usage = '[<ini file>]'
    summary = 'Run ensure_index on all mongo objects'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        from allura import model as M
        self.basic_setup()
        # Collect indexes by collection name
        main_indexes = defaultdict(lambda: ([], []))
        project_indexes = defaultdict(lambda: ([], []))
        base.log.info('Collecting indexes...')
        for name, cls in MappedClass._registry.iteritems():
            cname = cls.__mongometa__.name
            if cname is None:
                base.log.info('... skipping abstract class %s', cls)
                continue
            base.log.info('... for class %s', cls)
            indexes = getattr(cls.__mongometa__, 'indexes', []) or []
            uindexes = getattr(cls.__mongometa__, 'unique_indexes', []) or []
            if cls.__mongometa__.session in (
                M.main_orm_session, M.repository_orm_session):
                idx = main_indexes[cname]
            else:
                idx = project_indexes[cname]
            idx[0].extend(indexes)
            idx[1].extend(uindexes)
        base.log.info('Updating indexes for main DB')
        db = M.main_doc_session.db
        for name, (indexes, uindexes) in main_indexes.iteritems():
            self._update_indexes(db[name], indexes, uindexes)
        base.log.info('Updating indexes for project DBs')
        projects = M.Project.query.find().all()
        configured_dbs = set()
        for p in projects:
            db = p.database_uri
            if db in configured_dbs: continue
            configured_dbs.add(db)
            c.project = p
            db = M.project_doc_session.db
            base.log.info('... DB: %s', db)
            for name, (indexes, uindexes) in project_indexes.iteritems():
                self._update_indexes(db[name], indexes, uindexes)

    def _update_indexes(self, collection, indexes, uindexes):
        indexes = set(map(tuple, indexes))
        uindexes = set(map(tuple, uindexes))
        prev_indexes = {}
        prev_uindexes = {}
        for iname, fields in collection.index_information().iteritems():
            if iname == '_id_': continue
            if fields.get('unique'):
                prev_uindexes[iname] = tuple(fields['key'])
            else:
                prev_indexes[iname] = tuple(fields['key'])
        # Drop obsolete indexes
        for iname, key in prev_indexes.iteritems():
            if key not in indexes:
                base.log.info('...... drop index %s:%s', collection.name, iname)
                collection.drop_index(iname)
        for iname, key in prev_uindexes.iteritems():
            if key not in uindexes:
                base.log.info('...... drop index %s:%s', collection.name, iname)
                collection.drop_index(iname)
        # Ensure all indexes
        for idx in map(list, indexes):
            base.log.info('...... ensure index %s:%s', collection.name, idx)
            collection.ensure_index(idx, background=True)
        for idx in map(list, uindexes):
            base.log.info('...... ensure unique index %s:%s', collection.name, idx)
            collection.ensure_index(idx, background=True, unique=True)

def build_model_inheritance_graph():
    graph = dict((c, ([], [])) for c in MappedClass._registry.itervalues())
    for cls, (parents, children)  in graph.iteritems():
        for b in cls.__bases__:
            if b not in graph: continue
            parents.append(b)
            graph[b][1].append(cls)
    return graph

def dump_cls(depth, cls):
    indent = ' '*4*depth
    yield indent + '%s.%s' % (cls.__module__, cls.__name__)
    m = mapper(cls)
    for p in m.properties:
        s = indent*2 + ' - ' + str(p)
        if hasattr(p, 'field_type'):
            s += ' (%s)' % p.field_type
        yield s

def dfs(root, graph, depth=0):
    yield depth, root
    for c in graph[root][1]:
        for r in dfs(c, graph, depth+1):
            yield r


def pm(etype, value, tb): # pragma no cover
    import pdb, traceback
    try:
        from IPython.ipapi import make_session; make_session()
        from IPython.Debugger import Pdb
        sys.stderr.write('Entering post-mortem IPDB shell\n')
        p = Pdb(color_scheme='Linux')
        p.reset()
        p.setup(None, tb)
        p.print_stack_trace()
        sys.stderr.write('%s: %s\n' % ( etype, value))
        p.cmdloop()
        p.forget()
        # p.interaction(None, tb)
    except ImportError:
        sys.stderr.write('Entering post-mortem PDB shell\n')
        traceback.print_exception(etype, value, tb)
        pdb.post_mortem(tb)
