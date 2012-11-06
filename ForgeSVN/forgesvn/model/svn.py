import sys
import re
import os
import shutil
import string
import logging
import subprocess
from subprocess import Popen, PIPE
from hashlib import sha1
from cStringIO import StringIO
from datetime import datetime
from glob import glob

import tg
import pysvn
from pymongo.errors import DuplicateKeyError
from pylons import tmpl_context as c, app_globals as g

from ming.base import Object
from ming.orm import Mapper, FieldProperty, session
from ming.utils import LazyProperty

from allura import model as M
from allura.lib import helpers as h
from allura.model.repository import GitLikeTree
from allura.model.auth import User
from allura.lib.utils import svn_path_exists

log = logging.getLogger(__name__)

class Repository(M.Repository):
    tool_name='SVN'
    repo_id='svn'
    type_s='SVN Repository'
    class __mongometa__:
        name='svn-repository'
    branches = FieldProperty([dict(name=str,object_id=str)])
    _refresh_precompute = False

    @LazyProperty
    def _impl(self):
        return SVNImplementation(self)

    def clone_command(self, category, username=''):
        '''Return a string suitable for copy/paste that would clone this repo locally
           category is one of 'ro' (read-only), 'rw' (read/write), or 'https' (read/write via https)
        '''
        if not username and c.user not in (None, User.anonymous()):
            username = c.user.username
        tpl = string.Template(tg.config.get('scm.clone.%s.%s' % (category, self.tool)) or
                              tg.config.get('scm.clone.%s' % self.tool))
        return tpl.substitute(dict(username=username,
                                   source_url=self.clone_url(category, username)+c.app.config.options.get('checkout_url'),
                                   dest_path=self.suggested_clone_dest_path()))

    def compute_diffs(self): return

    def count(self, *args, **kwargs):
        return super(Repository, self).count(None)

    def count_revisions(self, ci):
        # since SVN histories are inherently linear and the commit _id
        # contains the revision, just parse it out from there
        return int(self._impl._revno(ci._id))

    def log(self, branch='HEAD', offset=0, limit=10):
        return list(self._log(branch, offset, limit))

    def commitlog(self, commit_ids, skip=0, limit=sys.maxint):
        ci_id = commit_ids[0]
        if skip > 0:
            rid, rev = ci_id.split(':')
            rev = int(rev) - skip
            ci_id = '%s:%s' % (rid, rev)
        ci = self._impl.commit(ci_id)
        while ci is not None and limit > 0:
            yield ci._id
            limit -= 1
            ci = ci.parent()

    def latest(self, branch=None):
        if self._impl is None: return None
        if not self.heads: return None
        return self._impl.commit(self.heads[0].object_id)


class SVNCalledProcessError(Exception):
    def __init__(self, cmd, returncode, stdout, stderr):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return "Command: '%s' returned non-zero exit status %s\nSTDOUT: %s\nSTDERR: %s" % \
            (self.cmd, self.returncode, self.stdout, self.stderr)


class SVNImplementation(M.RepositoryImplementation):
    post_receive_template = string.Template(
        '#!/bin/bash\n'
        '# The following is required for site integration, do not remove/modify.\n'
        '# Place user hook code in post-commit-user and it will be called from here.\n'
        'curl -s $url\n'
        '\n'
        'DIR="$$(dirname "$${BASH_SOURCE[0]}")"\n'
        'if [ -x $$DIR/post-commit-user ]; then'
        '  exec $$DIR/post-commit-user "$$@"\n'
        'fi')

    def __init__(self, repo):
        self._repo = repo

    @LazyProperty
    def _svn(self):
        return pysvn.Client()

    @LazyProperty
    def _url(self):
        return 'file://%s%s' % (self._repo.fs_path, self._repo.name)

    def shorthand_for_commit(self, oid):
        return '[r%d]' % self._revno(oid)

    def url_for_commit(self, commit):
        if isinstance(commit, basestring):
            object_id = commit
        else:
            object_id = commit._id
        return '%s%d/' % (
            self._repo.url(), self._revno(object_id))

    def init(self, default_dirs=True, skip_special_files=False):
        fullname = self._setup_paths()
        log.info('svn init %s', fullname)
        if os.path.exists(fullname):
            shutil.rmtree(fullname)
        subprocess.call(['svnadmin', 'create', self._repo.name],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=self._repo.fs_path)
        if not skip_special_files:
            self._setup_special_files()
        self._repo.status = 'ready'
        # make first commit with dir structure
        if default_dirs:
            self._repo._impl._svn.checkout('file://'+fullname, fullname+'/tmp')
            os.mkdir(fullname+'/tmp/trunk')
            os.mkdir(fullname+'/tmp/tags')
            os.mkdir(fullname+'/tmp/branches')
            self._repo._impl._svn.add(fullname+'/tmp/trunk')
            self._repo._impl._svn.add(fullname+'/tmp/tags')
            self._repo._impl._svn.add(fullname+'/tmp/branches')
            self._repo._impl._svn.checkin([fullname+'/tmp/trunk',fullname+'/tmp/tags',fullname+'/tmp/branches'],'Initial commit')
            shutil.rmtree(fullname+'/tmp')

    def clone_from(self, source_url):
        '''Initialize a repo as a clone of another using svnsync'''
        self.init(default_dirs=False, skip_special_files=True)
        # Need a pre-revprop-change hook for cloning
        fn = os.path.join(self._repo.fs_path, self._repo.name,
                          'hooks', 'pre-revprop-change')
        with open(fn, 'wb') as fp:
            fp.write('#!/bin/sh\n')
        os.chmod(fn, 0755)

        def check_call(cmd):
            p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
            stdout, stderr = p.communicate(input='p\n')
            if p.returncode != 0:
                self._repo.status = 'ready'
                session(self._repo).flush(self._repo)
                raise SVNCalledProcessError(cmd, p.returncode, stdout, stderr)

        self._repo.status = 'importing'
        session(self._repo).flush(self._repo)
        log.info('Initialize %r as a clone of %s',
                 self._repo, source_url)
        check_call(['svnsync', 'init', self._url, source_url])
        check_call(['svnsync', '--non-interactive', 'sync', self._url])
        log.info('... %r cloned', self._repo)
        if not svn_path_exists("file://%s%s/%s" %
                         (self._repo.fs_path,
                          self._repo.name,
                          c.app.config.options['checkout_url'])):
            c.app.config.options['checkout_url'] = ""
        self._setup_special_files(source_url)
        g.post_event('repo_cloned', source_url)
        self._repo.refresh(notify=False)

    def refresh_heads(self):
        info = self._svn.info2(
            self._url,
            revision=pysvn.Revision(pysvn.opt_revision_kind.head),
            recurse=False)[0][1]
        oid = self._oid(info.rev.number)
        self._repo.heads = [ Object(name=None, object_id=oid) ]
        # Branches and tags aren't really supported in subversion
        self._repo.branches = []
        self._repo.repo_tags = []
        session(self._repo).flush(self._repo)

    def commit(self, rev):
        if rev in ('HEAD', None):
            if not self._repo.heads: return None
            oid = self._repo.heads[0].object_id
        elif isinstance(rev, int) or rev.isdigit():
            oid = self._oid(rev)
        else:
            oid = rev
        result = M.repo.Commit.query.get(_id=oid)
        if result is None: return None
        result.set_context(self._repo)
        return result

    def all_commit_ids(self):
        """Return a list of commit ids, starting with the head (most recent
        commit) and ending with the root (first commit).
        """
        if not self._repo.heads:
            return []
        head_revno = self._revno(self._repo.heads[0].object_id)
        return map(self._oid, range(head_revno, 0, -1))

    def new_commits(self, all_commits=False):
        head_revno = self._revno(self._repo.heads[0].object_id)
        oids = [ self._oid(revno) for revno in range(1, head_revno+1) ]
        if all_commits:
            return oids
        # Find max commit id -- everything greater than that will be "unknown"
        prefix = self._oid('')
        q = M.repo.Commit.query.find(
            dict(
                type='commit',
                _id={'$gt':prefix},
                ),
            dict(_id=True)
            )
        seen_oids = set()
        for d in q.ming_cursor.cursor:
            oid = d['_id']
            if not oid.startswith(prefix): break
            seen_oids.add(oid)
        return [
            oid for oid in oids if oid not in seen_oids ]

    def refresh_commit_info(self, oid, seen_object_ids, lazy=True):
        from allura.model.repo import CommitDoc, DiffInfoDoc
        ci_doc = CommitDoc.m.get(_id=oid)
        if ci_doc and lazy: return False
        revno = self._revno(oid)
        rev = self._revision(oid)
        try:
            log_entry = self._svn.log(
                self._url,
                revision_start=rev,
                limit=1,
                discover_changed_paths=True)[0]
        except pysvn.ClientError:
            log.info('ClientError processing %r %r, treating as empty', oid, self._repo, exc_info=True)
            log_entry = Object(date='', message='', changed_paths=[])
        log_date = None
        if hasattr(log_entry, 'date'):
            log_date = datetime.utcfromtimestamp(log_entry.date)
        user = Object(
            name=log_entry.get('author', '--none--'),
            email='',
           date=log_date)
        args = dict(
            tree_id=None,
            committed=user,
            authored=user,
            message=log_entry.get("message", "--none--"),
            parent_ids=[],
            child_ids=[])
        if revno > 1:
            args['parent_ids'] = [ self._oid(revno-1) ]
        if ci_doc:
            ci_doc.update(**args)
            ci_doc.m.save()
        else:
            ci_doc = CommitDoc(dict(args, _id=oid))
            try:
                ci_doc.m.insert(safe=True)
            except DuplicateKeyError:
                if lazy: return False
        # Save diff info
        di = DiffInfoDoc.make(dict(_id=ci_doc._id, differences=[]))
        for path in log_entry.changed_paths:
            if path.action in ('A', 'M', 'R'):
                try:
                    rhs_info = self._svn.info2(
                        self._url + h.really_unicode(path.path),
                        revision=self._revision(ci_doc._id),
                        recurse=False)[0][1]
                    rhs_id = self._obj_oid(ci_doc._id, rhs_info)
                except pysvn.ClientError, e:
                    # pysvn will sometimes misreport deleted files (D) as
                    # something else (like A), causing info2() to raise a
                    # ClientError since the file doesn't exist in this
                    # revision. Set lrhs_id = None to treat like a deleted file
                    log.info('This error was handled gracefully and logged '
                             'for informational purposes only:\n' + str(e))
                    rhs_id = None
            else:
                rhs_id = None
            if ci_doc.parent_ids and path.action in ('D', 'M', 'R'):
                try:
                    lhs_info = self._svn.info2(
                        self._url + h.really_unicode(path.path),
                        revision=self._revision(ci_doc.parent_ids[0]),
                        recurse=False)[0][1]
                    lhs_id = self._obj_oid(ci_doc._id, lhs_info)
                except pysvn.ClientError, e:
                    # pysvn will sometimes report new files as 'M'odified,
                    # causing info2() to raise ClientError since the file
                    # doesn't exist in the parent revision. Set lhs_id = None
                    # to treat like a newly added file.
                    log.info('This error was handled gracefully and logged '
                             'for informational purposes only:\n' + str(e))
                    lhs_id = None
            else:
                lhs_id = None
            di.differences.append(dict(
                    name=h.really_unicode(path.path),
                    lhs_id=lhs_id,
                    rhs_id=rhs_id))
        di.m.save()
        return True

    def compute_tree_new(self, commit, tree_path='/'):
        from allura.model import repo as RM
        tree_path = tree_path[:-1]
        tree_id = self._tree_oid(commit._id, tree_path)
        tree, isnew = RM.Tree.upsert(tree_id)
        if not isnew: return tree_id
        log.debug('Computing tree for %s: %s',
                 self._revno(commit._id), tree_path)
        rev = self._revision(commit._id)
        try:
            infos = self._svn.info2(
                self._url + tree_path,
                revision=rev,
                depth=pysvn.depth.immediates)
        except pysvn.ClientError:
            log.exception('Error computing tree for %s: %s(%s)',
                          self._repo, commit, tree_path)
            tree.delete()
            return None
        log.debug('Compute tree for %d paths', len(infos))
        for path, info in infos[1:]:
            last_commit_id = self._oid(info['last_changed_rev'].number)
            last_commit = M.repo.Commit.query.get(_id=last_commit_id)
            M.repo_refresh.set_last_commit(
                self._repo._id,
                re.sub(r'/?$', '/', tree_path),  # force it to end with /
                path,
                self._tree_oid(commit._id, path),
                M.repo_refresh.get_commit_info(last_commit))
            if info.kind == pysvn.node_kind.dir:
                tree.tree_ids.append(Object(
                        id=self._tree_oid(commit._id, path),
                        name=path))
            elif info.kind == pysvn.node_kind.file:
                tree.blob_ids.append(Object(
                        id=self._tree_oid(commit._id, path),
                        name=path))
            else:
                assert False
        session(tree).flush(tree)
        trees_doc = RM.TreesDoc.m.get(_id=commit._id)
        if not trees_doc:
            trees_doc = RM.TreesDoc(dict(
                _id=commit._id,
                tree_ids=[]))
        trees_doc.tree_ids.append(tree_id)
        trees_doc.m.save(safe=False)
        return tree_id

    def _tree_oid(self, commit_id, path):
        data = 'tree\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

    def _blob_oid(self, commit_id, path):
        data = 'blob\n%s\n%s' % (commit_id, h.really_unicode(path))
        return sha1(data.encode('utf-8')).hexdigest()

    def _obj_oid(self, commit_id, info):
        path = info.URL[len(info.repos_root_URL):]
        if info.kind == pysvn.node_kind.dir:
            return self._tree_oid(commit_id, path)
        else:
            return self._blob_oid(commit_id, path)

    def log(self, object_id, skip, count):
        revno = self._revno(object_id)
        result = []
        while count and revno:
            if skip == 0:
                result.append(self._oid(revno))
                count -= 1
            else:
                skip -= 1
            revno -= 1
        if revno:
            return result, [ self._oid(revno) ]
        else:
            return result, []

    def open_blob(self, blob):
        data = self._svn.cat(
            self._url + blob.path(),
            revision=self._revision(blob.commit._id))
        return StringIO(data)

    def blob_size(self, blob):
        try:
            data = self._svn.list(
                   self._url + blob.path(),
                   revision=self._revision(blob.commit._id),
                   dirent_fields=pysvn.SVN_DIRENT_SIZE)
        except pysvn.ClientError:
            log.info('ClientError getting filesize %r %r, returning 0', blob.path(), self._repo, exc_info=True)
            return 0

        try:
            size = data[0][0]['size']
        except (IndexError, KeyError):
            log.info('Error getting filesize: bad data from svn client %r %r, returning 0', blob.path(), self._repo, exc_info=True)
            size = 0

        return size

    def _setup_hooks(self, source_path=None):
        'Set up the post-commit and pre-revprop-change hooks'
        # setup a post-commit hook to notify Allura of changes to the repo
        # the hook should also call the user-defined post-commit-user hook
        text = self.post_receive_template.substitute(
            url=tg.config.get('base_url', 'http://localhost:8080')
            + '/auth/refresh_repo' + self._repo.url())
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'post-commit')
        with open(fn, 'wb') as fp:
            fp.write(text)
        os.chmod(fn, 0755)
        # create a blank pre-revprop-change file if one doesn't
        # already exist to allow remote modification of revision
        # properties (see http://svnbook.red-bean.com/en/1.1/ch05s02.html)
        fn = os.path.join(self._repo.fs_path, self._repo.name, 'hooks', 'pre-revprop-change')
        if not os.path.exists(fn):
            with open(fn, 'wb') as fp:
                fp.write('#!/bin/sh\n')
            os.chmod(fn, 0755)

    def _revno(self, oid):
        return int(oid.split(':')[1])

    def _revision(self, oid):
        return pysvn.Revision(
            pysvn.opt_revision_kind.number,
            self._revno(oid))

    def _oid(self, revno):
        return '%s:%s' % (self._repo._id, revno)

Mapper.compile_all()
