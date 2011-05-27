import os
import sys
import struct
import logging

from pylons import c
from bson import BSON

from ming.orm import Mapper, state

from allura import model as M

log = logging.getLogger(__name__)

def main():
    if len(sys.argv) not in (2,3):
        log.error('Usage: %s <shortname> [<backup_dir>]', sys.argv[0])
        return 1
    pname = sys.argv[1]
    project = M.Project.query.get(shortname=pname)
    if project is None:
        log.fatal('Project %s not found', pname)
        print 'Project %s not found' % pname
        return 2
    if len(sys.argv) == 3:
        backup_dir = sys.argv[2]
    else:
        pname = project.shortname
        gid = project.tool_data.get('sfx', {}).get('group_id', project._id)
        dirname = '%s-%s.purge' % (pname, gid)
        backup_dir = os.path.join(
            os.getcwd(), dirname)
    log.info('Backing up %s to %s', pname, backup_dir)
    dump_project(project, backup_dir)
    return 0

def _write_bson(fp, doc):
    bson = BSON.from_dict(doc)
    fp.write(struct.pack('!l', len(bson)))
    fp.write(bson)

def dump_project(project, dirname):
    if not os.path.exists(dirname):
        os.mkdir(dirname)
    with open(os.path.join(dirname, 'project.bson'), 'w') as fp:
        _write_bson(fp, state(project).document)
    c.project = project
    app_config_ids = [
        ac._id for ac in M.AppConfig.query.find(dict(project_id=c.project._id)) ]
    visited_collections = {}
    for m in Mapper.all_mappers():
        cls = m.mapped_class
        cname = cls.name
        sess = m.session
        if sess is None:
            log.info('Skipping %s which has no session', cls)
            continue
        dbname = sess.impl.db.name
        fqname = cname + '/' + dbname
        if fqname in visited_collections:
            log.info('Skipping %s (already dumped collection %s in %s)',
                     cls, fqname, visited_collections[fqname])
            continue
        visited_collections[fqname] = cls
        if 'project_id' in m.property_index:
            # Dump the things directly related to the project
            oq = cls.query.find(dict(project_id=project._id))
        elif 'app_config_id' in m.property_index:
            # ... and the things related to its apps
            oq = cls.query.find(dict(app_config_id={'$in':app_config_ids}))
        else:
            # Don't dump other things
            continue
        num_objs = oq.count()
        if num_objs == 0: continue
        if not os.path.exists(os.path.join(dirname, dbname)):
            os.mkdir(os.path.join(dirname, dbname))
        fname = os.path.join(
            dirname,
            dbname,
            '%s.bson' % (cls.__mongometa__.name))
        log.info('%s: dumping %s objects to %s',
                 name, num_objs, fname)
        with open(os.path.join(dirname, fname), 'w') as fp:
            for obj in oq.ming_cursor: _write_bson(fp, obj)

if __name__ == '__main__':
    sys.exit(main())
