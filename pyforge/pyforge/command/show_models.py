import sys

from . import base
from pylons import c

from ming.orm import MappedClass, mapper, ThreadLocalORMSession, session, state

class ShowModelsCommand(base.Command):
    min_args=1
    max_args=1
    usage = 'NAME <ini file>'
    summary = 'Show the inheritance graph of all Ming models'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        self.basic_setup()
        graph = build_model_inheritance_graph()
        for depth, cls in dfs(MappedClass, graph):
            for line in dump_cls(depth, cls):
                print line

class ReindexCommand(base.Command):
    min_args=1
    max_args=1
    usage = 'NAME <ini file>'
    summary = 'Reindex and re-shortlink all artifacts'
    parser = base.Command.standard_parser(verbose=True)

    def command(self):
        from pyforge import model as M
        self.basic_setup()
        graph = build_model_inheritance_graph()
        # Clear shortlinks
        for p in M.Project.query.find():
            base.log.info('Reindex project %s', p.shortname)
            c.project = p
            M.ArtifactLink.query.remove({})
            for _, acls in dfs(M.Artifact, graph):
                base.log.info('  %s', acls)
                for a in acls.query.find():
                    state(a).soil()
                session(acls).flush()
                session(acls).clear()

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

def dump(root, graph):
    for depth, cls in dfs(MappedClass, graph):
        indent = ' '*4*depth


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

sys.excepthook = pm

