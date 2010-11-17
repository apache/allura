from collections import defaultdict
from pylons import c
from flyway import Migration
import ming
from ming.orm import mapper, ORMSession, session, state

from allura import model as M
from allura.lib import plugin
from allura.ext.project_home import model as PM
from forgetracker import model as TM
from forgewiki import model as WM
from forgediscussion import model as DM
from forgegit import model as GitM
from forgehg import model as HgM
from forgesvn import model as SVNM

STATS_COLLECTION_SIZE=100000

class MigrateFiles(Migration):
    version = 14

    def up(self):
        db = self.session.db
        for collection in db.collection_names():
            if collection.endswith('.files'):
                self.up_collection(db, collection)

    def down(self):
        # Nothing to do, really, as long as we don't update
        # any metadata while upgraded
        pass

    def _up_collection(self, db, collection_name):
        collection = db[collection_name]
        # First, create a 'root' collection, clearing it out as well
        root_collection = db[collection_name.split('.')[0]]
        root_collection.remove({})
        for doc in collection.find():
            newdoc = dict(doc)
            newdoc.update(doc['metadata'])
            newdoc.pop('metadata')
            newdoc['file_id'] = doc['_id']
            for aid_name in ('post_id', 'page_id', 'post_id', 'ticket_id'):
                if aid_name in newdoc:
                    newdoc['artifact_id'] = newdoc.pop(aid_name)
            root_collection.save(newdoc)

class CreateStatsCollection(Migration):
    version = 13

    def up(self):
        if self.session.db.name == 'allura':
            self.session.db.create_collection(
                M.Stats.__mongometa__.name,
                capped=True,
                size=STATS_COLLECTION_SIZE*10,
                max=STATS_COLLECTION_SIZE)

    def down(self):
        if self.session.db.name == 'allura':
            self.session.db.drop_collection(
                M.Stats.__mongometa__.name)

class DeleteFlashMailboxes(Migration):
    version = 12

    def up(self):
        if self.session.db.name == 'allura':
            self.ormsession.remove(
                M.Mailbox,
                {'type':'flash'})

    def down(self):
        raise NotImplementedError, 'ClearMailboxes.down'

class ClearMailboxes(Migration):
    version = 11

    def up(self):
        if self.session.db.name == 'allura':
            self.ormsession.remove(M.Mailbox, {})
            self.ormsession.ensure_indexes(M.Mailbox)

    def down(self):
        raise NotImplementedError, 'ClearMailboxes.down'

class AddMountLabels(Migration):
    version = 10

    def up(self):
        configs = self.ormsession.find(M.AppConfig).all()
        for config in configs:
            config.options['mount_label'] = config.options['mount_point']
        self.ormsession.flush()

    def down(self):
        configs = self.ormsession.find(M.AppConfig).all()
        for config in configs:
            del config.options['mount_label']
        self.ormsession.flush()

class UpdateThemeToOnyx(Migration):
    version = 9

    def up(self):
        if self.session.db.name == 'allura':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
            if not theme: return
            theme.color1='#295d78'
            theme.color2='#272727'
            theme.color3='#454545'
            theme.color4='#c3c3c3'
            theme.color5='#d7d7d7'
            theme.color6='#ebebeb'
            self.ormsession.update_now(theme, state(theme))
            self.ormsession.flush()

    def down(self):
        if self.session.db.name == 'allura':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
            if not theme: return
            theme.color1='#0088cc'
            theme.color2='#000000'
            theme.color3='#454545'
            theme.color4='#6c7681'
            theme.color5='#d8d8d8'
            theme.color6='#ececec'
            self.ormsession.update_now(theme, state(theme))
            self.ormsession.flush()

class RemoveOldInitProjects(Migration):
    version=8

    def __init__(self, *args, **kwargs):
        super(RemoveOldInitProjects, self).__init__(*args, **kwargs)
        try:
            c.project
        except TypeError:
            class EmptyClass(): pass
            c._push_object(EmptyClass())
            c.project = EmptyClass()
            c.project._id = None
            c.app = EmptyClass()
            c.app.config = EmptyClass()
            c.app.config.options = EmptyClass()
            c.app.config.options.mount_point = None

    def up(self):
        self.ormsession.remove(M.Project, {'shortname':'--init--'})
        self.ormsession.update(M.Project, {'shortname':'__init__'}, {'$set':{'shortname':'--init--'}})

    def down(self):
        pass # Do nothing

class UnderToDash(Migration):
    version = 7

    def __init__(self, *args, **kwargs):
        super(UnderToDash, self).__init__(*args, **kwargs)
        try:
            c.project
        except TypeError:
            class EmptyClass(): pass
            c._push_object(EmptyClass())
            c.project = EmptyClass()
            c.project._id = None
            c.app = EmptyClass()
            c.app.config = EmptyClass()
            c.app.config.options = EmptyClass()
            c.app.config.options.mount_point = None

    def up(self):
        def fixup(s):
            return s.replace('_', '-')
        fix_pathnames(self.ormsession,fixup)

    def down(self):
        pass # Do nothing

class MergeDuplicateRoles(Migration):
    version = 6

    def up(self):
        if self.session.db.name == 'allura': self.up_allura()
        else: self.up_project()

    def down(self):
        pass

    def up_allura(self):
        # Uniquify User.projects list
        for u in self.session.find(self.User):
            u.projects = list(set(u.projects))
            self.session.save(u)

    def up_project(self):
        # Consolidate roles by user_id
        roles_by_user = defaultdict(list)
        for role in self.session.find(self.Role):
            if role.get('user_id') is None: continue
            roles_by_user[role.user_id].append(role)
        for user_id, roles in roles_by_user.iteritems():
            if len(roles) <= 1: continue
            main_role = roles[0]
            subroles = set()
            for r in roles:
                for sr_id in r.get('roles', []):
                    subroles.add(sr_id)
            main_role.roles = list(subroles)
            self.session.save(main_role)
            for r in roles[1:]:
                self.session.delete(r)
        # Add index
        try:
            self.session.drop_indexes(self.Role)
        except:
            pass
        self.session.ensure_indexes(self.Role)

    class User(ming.Document):
        class __mongometa__:
            name='user'

    class Role(ming.Document):
        class __mongometa__:
            name='user'
            unique_indexes = [ ('user_id', 'name') ]

class UnifyPermissions(Migration):
    version = 5

    def up(self):
        perm_owner = self.ormsession.find(M.ProjectRole, dict(name='owner')).first()
        perm_Owner = self.ormsession.find(M.ProjectRole, dict(name='Owner')).first()
        if perm_owner:
            perm_owner.name = 'Admin'
        elif perm_Owner:
            perm_Owner.name = 'Admin'
        perm_member = self.ormsession.find(M.ProjectRole, dict(name='member')).first()
        if perm_member:
            perm_member.name = 'Member'
        perm_developer = self.ormsession.find(M.ProjectRole, dict(name='developer')).first()
        if perm_developer:
            perm_developer.name = 'Developer'
        if self.session.db.name != 'allura':
            role_names = [r.name for r in self.ormsession.find(M.ProjectRole)]
            if len(role_names) and 'Admin' not in role_names:
                new_admin = M.ProjectRole(name='Admin')
            if len(role_names) and 'Developer' not in role_names:
                new_admin = M.ProjectRole(name='Developer')

        self.ormsession.flush()

    def down(self):
        perm_Admin = self.ormsession.find(M.ProjectRole, dict(name='Admin')).first()
        if perm_Admin:
            perm_Admin.name = 'Owner'

        self.ormsession.flush()

class UpdateProjectsToTools(Migration):
    version = 4

    def up(self):
        # if self.session.db.name == 'allura':
        # import pdb; pdb.set_trace()
        rename_key(self.session,M.User,'plugin_preferences','tool_preferences')
        rename_key(self.session,M.AppConfig,'plugin_name','tool_name')
        rename_key(self.session,M.ArtifactLink,'plugin_name','tool_name')
        rename_key(self.session,M.Project,'plugin','tool',inside='acl')
        if c.app:
            c.app.__version__ = '0.1'
            c.app.config.tool_name = 'project_home'
        for pc in self.ormsession.find(PM.PortalConfig, {}):
            for div in pc.layout:
                for widget in div.content:
                    if widget.widget_name == 'plugin_status':
                        widget.widget_name = 'tool_status'
        self.ormsession.flush()
        # fix artifacts
        for cls in (
            M.Artifact,
            M.VersionedArtifact,
            M.Snapshot,
            M.Message,
            M.Post,
            M.AwardGrant,
            M.Discussion,
            M.Award,
            M.Thread,
            M.Post,
            M.PostHistory,
            DM.Forum,
            DM.ForumPost,
            DM.forum.ForumPostHistory,
            DM.ForumThread,
            WM.Page,
            WM.wiki.PageHistory,
            TM.Bin,
            TM.Ticket,
            TM.ticket.TicketHistory,
            PM.PortalConfig,
            GitM.GitRepository,
            HgM.HgRepository,
            SVNM.SVNRepository,
            ):
            rename_key(self.session,cls,'plugin_verson','tool_version')

    def down(self):
        # if self.session.db.name == 'allura':
        rename_key(self.session,M.User,'tool_preferences','plugin_preferences')
        rename_key(self.session,M.AppConfig,'tool_name','plugin_name')
        rename_key(self.session,M.ArtifactLink,'tool_name','plugin_name')
        rename_key(self.session,M.Project,'tool','plugin',inside='acl')
        if c.app:
            c.app.__version__ = '0.1'
            c.app.config.tool_name = 'project_home'
        for pc in self.ormsession.find(PM.PortalConfig, {}):
            for div in pc.layout:
                for widget in div.content:
                    if widget.widget_name == 'tool_status':
                        widget.widget_name = 'plugin_status'
        self.ormsession.flush()
        # fix artifacts
        for cls in (
            M.Artifact,
            M.VersionedArtifact,
            M.Snapshot,
            M.Message,
            M.Post,
            M.AwardGrant,
            M.Discussion,
            M.Award,
            M.Thread,
            M.Post,
            M.PostHistory,
            DM.Forum,
            DM.ForumPost,
            DM.forum.ForumPostHistory,
            DM.ForumThread,
            WM.Page,
            WM.wiki.PageHistory,
            GitM.GitRepository,
            HgM.HgRepository,
            SVNM.SVNRepository,
            TM.Bin,
            TM.Ticket,
            TM.ticket.TicketHistory,
            PM.PortalConfig,
            ):
            rename_key(self.session,cls,'tool_version','plugin_verson')

class UpdateThemeToShinyBook(Migration):
    version = 3

    def up(self):
        if self.session.db.name == 'allura':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
            if not theme: return
            theme.color1='#0088cc'
            theme.color2='#000000'
            theme.color3='#454545'
            theme.color4='#6c7681'
            theme.color5='#d8d8d8'
            theme.color6='#ececec'
            self.ormsession.update_now(theme, state(theme))
            self.ormsession.flush()

    def down(self):
        if self.session.db.name == 'allura':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
            if not theme: return
            theme.color1='#104a75'
            theme.color2='#aed0ea'
            theme.color3='#EDF3FB'
            theme.color4='#D7E8F5'
            theme.color5='#000'
            theme.color6='#000'
            self.ormsession.update_now(theme, state(theme))
            self.ormsession.flush()

class RenameNeighborhoods(Migration):
    version = 2

    def up(self):
        n_users = self.ormsession.find(M.Neighborhood, dict(name='Users')).first()
        n_projects = self.ormsession.find(M.Neighborhood, dict(name='Projects')).first()
        if n_users:
            n_users.url_prefix = '/u/'
            n_users.shortname_prefix = 'u/'
        if n_projects:
            n_projects.url_prefix = '/p/'
        for p in self.ormsession.find(M.Project, {}):
            if p.shortname.startswith('users/'):
                p.shortname = p.shortname.replace('users/', 'u/')
        self.ormsession.flush()

    def down(self):
        n_users = self.ormsession.find(M.Neighborhood, dict(name='Users')).first()
        n_projects = self.ormsession.find(M.Neighborhood, dict(name='Projects')).first()
        if n_users:
            n_users.url_prefix = '/users/'
            n_users.shortname_prefix = 'users/'
        if n_projects:
            n_projects.url_prefix = '/projects/'
        for p in self.ormsession.find(M.Project, {}):
            if p.shortname.startswith('u/'):
                p.shortname = p.shortname.replace('u/', 'users/')
        self.ormsession.flush()

class DowncaseMountPoints(Migration):
    version = 1

    def __init__(self, *args, **kwargs):
        super(DowncaseMountPoints, self).__init__(*args, **kwargs)
        try:
            c.project
        except TypeError:
            class EmptyClass(): pass
            c._push_object(EmptyClass())
            c.project = EmptyClass()
            c.project._id = None
            c.app = EmptyClass()
            c.app.config = EmptyClass()
            c.app.config.options = EmptyClass()
            c.app.config.options.mount_point = None

    def up_requires(self):
        yield ('ForgeWiki', 0)
        yield ('ForgeTracker', 0)
        yield ('pyforge', 0)

    def up(self):
        fix_pathnames(self.ormsession, lambda s:s.lower().replace(' ', '_'))

    def down(self):
        pass # Do nothing

class V0(Migration):
    version = 0
    def up(self): pass
    def down(self):  pass

def rename_key(session, cls, old_key, new_key, inside=None):
    pm = session._impl(mapper(cls).doc_cls)
    for item in pm.find():
        if inside:
            if inside in item and old_key in item[inside]:
                item[inside][new_key] = item[inside][old_key]
                del item[inside][old_key]
        else:
            if old_key in item:
                item[new_key] = item[old_key]
                del item[old_key]
        pm.save(item)

def fix_pathnames(ormsession, mutator):
    def fix_aref(aref):
        if aref and aref.mount_point:
            aref.mount_point = mutator(aref.mount_point)
     # Fix neigborhoods
    for n in ormsession.find(M.Neighborhood, {}):
        n.shortname_prefix = mutator(n.shortname_prefix)
   # Fix Projects
    for p in ormsession.find(M.Project, {}):
        p.shortname = mutator(p.shortname)
    # Fix AppConfigs
    for ac in ormsession.find(M.AppConfig, {}):
        ac.options.mount_point = mutator(ac.options.mount_point)
        if ac.tool_name == 'Forum':
            ac.tool_name = 'Discussion'
    ormsession.flush(); ormsession.clear()
    # Fix ArtifactLinks
    for al in ormsession.find(M.ArtifactLink, {}):
        fix_aref(al.artifact_reference)
    # Fix feeds
    for f in ormsession.find(M.Feed, {}):
        fix_aref(f.artifact_reference)
    # Fix notifications
    for n in ormsession.find(M.Notification, {}):
        fix_aref(n.artifact_reference)
    # Fix tags
    for n in ormsession.find(M.TagEvent, {}):
        fix_aref(n.artifact_ref)
    for n in ormsession.find(M.UserTags, {}):
        fix_aref(n.artifact_reference)
    for n in ormsession.find(M.Tag, {}):
        fix_aref(n.artifact_ref)
    # fix PortalConfig
    for pc in ormsession.find(PM.PortalConfig):
        for layout in pc.layout:
            for w in layout.content:
                w.mount_point = mutator(w.mount_point)
    # Fix thread (has explicit artifact_reference property)
    for t in ormsession.find(M.Thread, {}):
        fix_aref(t.artifact_reference)
    for t in ormsession.find(DM.ForumThread, {}):
        fix_aref(t.artifact_reference)
    ormsession.flush(); ormsession.clear()
    # fix artifacts
    for cls in (
        M.Artifact,
        M.VersionedArtifact,
        M.Snapshot,
        M.Message,
        M.Post,
        M.AwardGrant,
        M.Discussion,
        M.Award,
        M.Thread,
        M.Post,
        M.PostHistory,
        DM.Forum,
        DM.ForumPost,
        DM.forum.ForumPostHistory,
        DM.ForumThread,
        WM.Page,
        WM.wiki.PageHistory,
        GitM.GitRepository,
        HgM.HgRepository,
        SVNM.SVNRepository,
        TM.Bin,
        TM.Ticket,
        TM.ticket.TicketHistory,
        PM.PortalConfig,
        ):
        for obj in ormsession.find(cls, {}):
            for ref in obj.references:
                fix_aref(ref)
            for ref in obj.backreferences.itervalues():
                fix_aref(ref)
            ormsession.flush(); ormsession.clear()

