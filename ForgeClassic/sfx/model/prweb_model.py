import logging
from pylons import c as context

from ming.utils import LazyProperty

from allura.lib import helpers as h
from .sfx_model import tables as T

log = logging.getLogger(__name__)
action_logger = h.log_action(log, 'SFX:')

class VHost(object):

    def __init__(self, name):
        self.name = name

    @classmethod
    def find(cls):
        q = T.prweb_vhost.select()
        q = q.where(
            T.prweb_vhost.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        for row in q.execute():
            obj = cls(row['vhost_name'])
            obj._row = row
            yield obj

    @classmethod
    def get(cls, vhostid):
        q = T.prweb_vhost.select()
        q = q.where(
            T.prweb_vhost.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        q = q.where(
            T.prweb_vhost.c.vhostid==vhostid)
        row = q.execute().fetchone()
        result = cls(row['vhost_name'])
        result._row = row
        return result

    @classmethod
    def create(cls, name):
        action_logger.info('CreateVHOST')
        stmt = T.prweb_vhost.insert()
        homedir = '/home/groups/%s/' % (
            h.sharded_path(context.project.get_tool_data('sfx', 'unix_group_name')))
        docdir = homedir + 'htdocs/'
        cgidir = homedir + 'cgi-bin/'
        group_id = context.project.get_tool_data('sfx', 'group_id')
        stmt.execute(
            vhost_name=name,
            docdir=docdir,
            cgidir=cgidir,
            group_id=group_id)
        return cls(name)

    def delete(self):
        action_logger.info('DelVHOST')
        stmt = T.prweb_vhost.delete()
        stmt = stmt.where(
            T.prweb_vhost.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        stmt = stmt.where(
            T.prweb_vhost.c.vhostid==self.vhostid)
        stmt.execute()

    @LazyProperty
    def _row(self):
        q = T.prweb_vhost.select(T.prweb_vhost.c.vhostid==self.name)
        q = q.where(
            T.prweb_vhost.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        return q.execute().first()

    def __getattr__(self, name):
        try:
            return self._row[name]
        except KeyError:
            raise AttributeError, name

class MySQL(object):

    @classmethod
    def create(cls, passwd_rouser, passwd_rwuser, passwd_adminuser):
        action_logger.info('CreateMySQL')
        stmt = T._mysql_auth.insert()
        stmt.execute(
            passwd_rouser=passwd_rouser,
            passwd_rwuser=passwd_rwuser,
            passwd_adminuser=passwd_adminuser,
            modified_by_uid=context.user.get_tool_data('sfx', 'userid'),
            group_id=context.project.get_tool_data('sfx', 'group_id'))
        return cls()

    @classmethod
    def update(cls, passwd_rouser, passwd_rwuser, passwd_adminuser):
        action_logger.info('UpdateMySQL')
        group_id=context.project.get_tool_data('sfx', 'group_id')
        stmt = T._mysql_auth.update(
            whereclause=T._mysql_auth.c.group_id==group_id)
        stmt.execute(
            passwd_rouser=passwd_rouser,
            passwd_rwuser=passwd_rwuser,
            passwd_adminuser=passwd_adminuser,
            modified_by_uid=context.user.get_tool_data('sfx', 'userid'))

    @property
    def prefix(self):
        gid = context.project.get_tool_data('sfx', 'group_id')
        name = str(context.project.get_tool_data('sfx', 'unix_group_name'))
        return name[0] + str(gid)

    @property
    def hostname(self):
        name = str(context.project.get_tool_data('sfx', 'unix_group_name'))
        return 'mysql-' + name[0]

    @property
    def url(self):
        return 'https://%s.sourceforge.net' % self.hostname

    @LazyProperty
    def _row(self):
        q = T.mysql_auth.select()
        q = q.where(
            T.mysql_auth.c.group_id==context.project.get_tool_data('sfx', 'group_id'))
        return q.execute().first()

    def __getattr__(self, name):
        if name == '_row':
            raise AttributeError, name
        elif self._row is None:
            return None
        try:
            return self._row[name]
        except KeyError:
            raise AttributeError, name
