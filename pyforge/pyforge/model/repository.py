import os
import mimetypes
import cPickle as pickle

import pylons
from tg import config
import pymongo.bson

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.lib.patience import SequenceMatcher

from .artifact import Artifact
from .types import ArtifactReference

def on_import():
    Repository.CommitClass = Commit
    Commit.TreeClass = Tree
    Tree.BlobClass = Blob

class Repository(Artifact):
    CommitClass=None
    class __mongometa__:
        name='generic-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''
    additional_viewable_extensions=FieldProperty(str)

    def __init__(self, **kw):
        if 'name' in kw and 'tool' in kw:
            if 'fs_path' not in kw:
                kw['fs_path'] = '/' + os.path.join(
                    kw['tool'],
                    pylons.c.project.url()[1:])
            if 'url_path' not in kw:
                kw['url_path'] = pylons.c.project.url()
        super(Repository, self).__init__(**kw)

    def log(self, branch, offset, limit):
        return []

    def commit(self, revision):
        raise NotImplementedError, 'commit'

    def url(self):
        return self.app_config.url()

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name)
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

    def scm_host(self):
        return self.tool + config.get('scm.host', '.' + pylons.request.host)

    @property
    def scm_url_path(self):
        return self.scm_host() + self.url_path + self.name

    def init(self):
        raise NotImplementedError, 'init'

class MockQuery(object):
    def __init__(self, cls):
        self._cls = cls

    def get(self, _id):
        return self._cls(_id, repo=pylons.c.app.repo)

class Commit(object):
    TreeClass=None
    type_s='Generic Commit'

    class __metaclass__(type):
         def __new__(meta, name, bases, dct):
             result = type.__new__(meta, name, bases, dct)
             result.query = MockQuery(result)
             return result

    def __init__(self, id, repo):
        self._id = id
        self._repo = repo

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__, self._id)

    def tree(self):
        return self.TreeClass(self._repo, self)

    def from_repo_object(self, repo, obj):
        raise NotImplementedError, 'from_repo_object'

    def context(self):
        '''Returns {'prev':Commit, 'next':Commit}'''
        raise NotImplementedError, 'context'

    def dump_ref(self):
        '''Return a pickle-serializable reference to an artifact'''
        try:
            d = ArtifactReference(dict(
                    project_id=self._repo.project_id,
                    mount_point=self._repo.app_config.options.mount_point,
                    artifact_type=pymongo.bson.Binary(pickle.dumps(self.__class__)),
                    artifact_id=self._id))
            return d
        except AttributeError: # pragma no cover
            return None

    def url(self):
        return self._repo.url() + self._id + '/'

    def primary(self, *args):
        return self

    def shorthand_id(self):
        raise NotImplementedError, 'shorthand_id'

class Tree(object):
    BlobClass=None

    def __init__(self, repo, commit, parent=None, name=None):
        self._repo = repo
        self._commit = commit
        self._parent = parent
        self._name = name

    def url(self):
        return self._commit.url() + 'tree' + self.path()

    def path(self):
        if self._parent:
            return self._parent.path() + self._name + '/'
        else:
            return '/'

    def is_blob(self, name):
        return False

    def get_tree(self, name):
        return self.__class__(self._repo, self._commit, self, name)

    def get_blob(self, name, path=None):
        if not path:
            return self.BlobClass(self._repo, self._commit, self, name)
        else:
            return self.get_tree(path[0]).get_blob(name, path[1:])

class Blob(object):

    def __init__(self, repo, commit, tree, filename):
        self._repo = repo
        self._commit = commit
        self._tree = tree
        self.filename = filename
        ext_list = getattr(repo, 'additional_viewable_extensions', '')
        if ext_list:
            ext_list = ext_list.split(',')
        else:
            ext_list = []
        additional_viewable_extensions = [ext.strip() for ext in ext_list if ext]
        additional_viewable_extensions.extend([ '.ini', '.gitignore', '.svnignore'])
        content_type, encoding = mimetypes.guess_type(filename)
        fn, ext = os.path.splitext(filename)
        if ext in additional_viewable_extensions:
            content_type, encoding = 'text/plain', None
        if content_type is None:
            self.content_type = 'application/octet-stream'
            self.content_encoding = None
        else:
            self.content_type = content_type
            self.content_encoding = encoding

    def url(self):
        return self._tree.url() + self.filename

    def __repr__(self):
        return '<%s %s of %r>' % (
            self.__class__.__name__, self.path(), self._commit)

    def path(self):
        return self._tree.path() + self.filename

    @property
    def has_html_view(self):
        return self.content_type.startswith('text/')

    @property
    def has_image_view(self):
        return self.content_type.startswith('image/')

    def context(self):
        '''Returns {'prev':Blob, 'next':Blob}'''
        raise NotImplementedError, 'context'

    def __iter__(self):
        return iter([])

    @classmethod
    def diff(cls, v0, v1):
        differ = SequenceMatcher(v0, v1)
        return differ.get_opcodes()

on_import()
MappedClass.compile_all()
