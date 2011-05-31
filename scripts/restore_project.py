import os
import sys
import struct
import logging

from ming.orm import state, session, Mapper

from pylons import c
from bson import BSON
from allura import model as M
from allura.command import ReindexCommand

log = logging.getLogger(__name__)

def main():
    if len(sys.argv) != 4:
        log.error('Usage: %s <dirname> <new_shortname> <new_unix_group_name>', sys.argv[0])
        return 2
    dirname = sys.argv[1]
    new_pname = sys.argv[2]
    new_ug_name = sys.argv[3]
    return restore_project(dirname, new_pname, new_ug_name)

def restore_project(dirname, new_shortname, new_unix_group_name):
    log.info('Reloading %s into %s', dirname, new_shortname)
    with open(os.path.join(dirname, 'project.bson')) as fp:
        project_doc = _read_bson(fp)
    project = M.Project.query.get(_id=project_doc['_id'])
    st = state(project)
    st.document = project_doc
    if project is None:
        log.fatal('Project not found')
        return 2
    project.shortname = new_shortname
    project.set_tool_data('sfx', unix_group_name=new_unix_group_name)
    project.deleted = False
    c.project = project
    conn = M.main_doc_session.db.connection
    repo_collections = get_repo_collections()
    for dbname in os.listdir(dirname):
        if dbname.endswith('.bson'): continue
        for fname in os.listdir(os.path.join(dirname, dbname)):
            cname = os.path.splitext(fname)[0]
            collection = conn[dbname][cname]
            with open(os.path.join(dirname, dbname, fname), 'rb') as fp:
                num_objects = 0
                while True:
                    doc = _read_bson(fp)
                    if doc is None: break
                    if cname in repo_collections:
                        cls = repo_collections[cname]
                        doc['fs_path'] = cls.default_fs_path(project, doc['tool'])
                        doc['url_path'] = cls.default_url_path(project, doc['tool'])
                    collection.insert(doc)
                    num_objects += 1
                log.info('%s: loaded %s objects from %s',
                         dbname, num_objects, fname)
    session(project).flush()
    reindex= ReindexCommand('reindex')
    reindex.run(['--project', new_shortname])
    return 0

def get_repo_collections():
    res = {}
    for m in Mapper.all_mappers():
        cls = m.mapped_class
        cname = cls.__mongometa__.name
        if issubclass(cls, M.Repository): res[cname] = cls
    return res

def _read_bson(fp):
    slen = fp.read(4)
    if not slen: return None
    bson = BSON(fp.read(struct.unpack('!l', slen)[0]))
    return bson.to_dict()

if __name__ == '__main__':
    sys.exit(main())
