import logging
from base64 import b64encode
from random import randint
from hashlib import sha256

from pylons import c

from ming import Document, Session, Field
from ming import schema as S

from pyforge.lib.helpers import push_config
from .session import ProjectSession

log = logging.getLogger(__name__)

SALT_LENGTH=8

def encode_password(password, salt=None):
    if salt is None:
        salt = ''.join(chr(randint(1, 0x7f))
                       for i in xrange(SALT_LENGTH))
    hashpass = sha256(salt + password.encode('utf-8')).digest()
    return 'sha256' + salt + b64encode(hashpass)

class User(Document):
    SALT_LEN=8
    class __mongometa__:
        name='user'
        session = Session.by_name('main')

    _id=Field(S.ObjectId)
    username=Field(str)
    display_name=Field(str)
    open_ids=Field([str])
    password=Field(str)
    projects=Field([str])

    @classmethod
    def new_user(cls, username):
        u = cls.m.insert(dict(username=username,
                              display_name=username,
                              password='foo'))
        return u

    @classmethod
    def register(cls, doc, make_project=True):
        result = cls.make(doc)
        result.m.insert()
        if make_project:
            result.register_project(result.username, 'users')
        return result

    def _make_project(self):
        from .project import Project
        # Register user project
        up = Project.m.get(_id='users/')
        p = up.new_subproject(self.username, install_apps=False)
        p.database='user:' + self.username
        is_root=True
        with push_config(c, project=p, user=self):
            pr = self.project_role()
            for roles in p.acl.itervalues():
                roles.append(pr._id)
            anon = ProjectRole.make(dict(name='*anonymous'))
            auth = ProjectRole.make(dict(name='*authenticated'))
            anon.m.save()
            auth.m.save()
            p.acl['read'].append(anon._id)
            p.install_app('admin', 'admin')
            p.install_app('search', 'search')
        p.m.save()
        return self

    def private_project(self):
        from .project import Project
        return Project.m.get(_id='users/%s/' % self.username)

    @property
    def script_name(self):
        return '/projects/users/' + self.username + '/'

    def my_projects(self):
        from .project import Project
        for p in self.projects:
            yield Project.m.get(_id=p)

    def role_iter(self):
        yield ProjectRole.m.get(name='*anonymous')
        if self._id:
            yield ProjectRole.m.get(name='*authenticated')
        if self._id:
            pr = self.project_role()
            for role in pr.role_iter():
                yield role

    def project_role(self):
        if self._id is None:
            return ProjectRole.m.get(name='*anonymous')
        obj = ProjectRole.m.get(user_id=self._id)
        if obj is None:
            obj = ProjectRole.make(dict(user_id=self._id))
            self.projects.append(c.project._id)
            self.m.save()
            obj.m.save()
        return obj

    def set_password(self, password):
        self.password = encode_password(password)

    def validate_password(self, password):
        if not self.password: return False
        salt = str(self.password[6:6+self.SALT_LEN])
        check = encode_password(password, salt)
        return check == self.password

    def register_project(self, pid, prefix='projects'):
        from .project import Project
        database = prefix + ':' + pid
        project_id = prefix + '/' + pid + '/'
        p = Project.make(dict(
                _id=project_id,
                name=pid,
                database=database,
                is_root=True))
        c.project = p
        pr = self.project_role()
        for roles in p.acl.itervalues():
            roles.append(pr._id)
        ProjectRole.make(dict(name='*anonymous')).m.save()
        ProjectRole.make(dict(name='*authenticated')).m.save()
        p.install_app('admin', 'admin')
        p.install_app('search', 'search')
        p.m.insert()
        return p

User.anonymous = User.make(dict(
        _id=None, username='*anonymous', display_name='Anonymous Coward'))

class ProjectRole(Document):
    class __mongometa__:
        session = ProjectSession(Session.by_name('main'))
        name='user'
    
    _id = Field(S.ObjectId)
    name = Field(str)
    user_id = Field(S.ObjectId, if_missing=None) # if role is a user
    roles = Field([S.ObjectId])

    def display(self):
        if self.name: return self.name
        if self.user_id:
            u = self.user
            if u.username: uname = u.username
            elif u.display_name: uname = u.display_name
            else: uname = u._id
            return '*user-%s' % uname
        return '**unknown name role: %s' % self._id

    @property
    def special(self):
        if self.name: return '*' == self.name[0]
        if self.user_id: return True
        return False

    @classmethod
    def for_user(cls, user):
        obj = cls.m.get(user_id=user._id)
        if obj is None:
            obj = cls.make(user_id=user._id)
            obj.m.save()
        return obj

    @property
    def user(self):
        return User.m.get(_id=self.user_id)

    def role_iter(self, visited=None):
        if visited is None: visited = set()
        if self._id not in visited: 
            yield self
            visited.add(self._id)
            for rid in self.roles:
                pr = ProjectRole.m.get(_id=rid)
                if pr is None: continue
                for rr in pr.role_iter(visited):
                    yield rr

