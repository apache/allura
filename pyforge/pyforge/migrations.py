from pylons import c
from flyway import Migration
import ming
from ming.orm import mapper, ORMSession, session, state

from pyforge import model as M
from pyforge.ext.project_home import model as PM
from forgetracker import model as TM
from forgewiki import model as WM
from helloforge import model as HM
from forgediscussion import model as DM
from forgegit import model as GitM
from forgehg import model as HgM
from forgesvn import model as SVNM


class UpdateProjectsToTools(Migration):
    version = 4

    def up_requires(self):
        yield ('pyforge', 3)
        # yield ('ForgeWiki', 3)
        # yield ('ForgeTracker', 3)

    def up(self):
        # if self.session.db.name == 'pyforge':
        # import pdb; pdb.set_trace()
        rename_key(self.session,M.User,'plugin_preferences','tool_preferences')
        rename_key(self.session,M.AppConfig,'plugin_name','tool_name')
        rename_key(self.session,M.ArtifactLink,'plugin_name','tool_name')
        rename_key(self.session,M.Project,'plugin','tool',inside='acl')
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
            SM.Repository,
            SM.Commit,
            TM.Bin,
            TM.Ticket,
            TM.ticket.TicketHistory,
            PM.PortalConfig,
            ):
            rename_key(self.session,cls,'plugin_verson','tool_version')

    def down(self):
        # if self.session.db.name == 'pyforge':
        rename_key(self.session,M.User,'tool_preferences','plugin_preferences')
        rename_key(self.session,M.AppConfig,'tool_name','plugin_name')
        rename_key(self.session,M.ArtifactLink,'tool_name','plugin_name')
        rename_key(self.session,M.Project,'tool','plugin',inside='acl')
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
            SM.Repository,
            SM.Commit,
            TM.Bin,
            TM.Ticket,
            TM.ticket.TicketHistory,
            PM.PortalConfig,
            ):
            rename_key(self.session,cls,'tool_version','plugin_verson')

class UpdateThemeToShinyBook(Migration):
    version = 3

    def up_requires(self):
        yield ('pyforge', 2)

    def up(self):
        if self.session.db.name == 'pyforge':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
            theme.color1='#0088cc'
            theme.color2='#000000'
            theme.color3='#454545'
            theme.color4='#6c7681'
            theme.color5='#d8d8d8'
            theme.color6='#ececec'
            self.ormsession.update_now(theme, state(theme))
            self.ormsession.flush()

    def down(self):
        if self.session.db.name == 'pyforge':
            theme = self.ormsession.find(M.Theme, {'name':'forge_default'}).first()
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

    def up_requires(self):
        yield ('pyforge', 1)

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
        # Fix neigborhoods
        for n in self.ormsession.find(M.Neighborhood, {}):
            n.name = n.name.lower().replace(' ', '_')
            n.shortname_prefix = n.shortname_prefix.lower().replace(' ', '_')
       # Fix Projects
        for p in self.ormsession.find(M.Project, {}):
            p.shortname = p.shortname.lower().replace(' ', '_')
        # Fix AppConfigs
        for ac in self.ormsession.find(M.AppConfig, {}):
            ac.options.mount_point = ac.options.mount_point.lower().replace(' ', '_')
            if ac.tool_name == 'Forum':
                ac.tool_name = 'Discussion'
        self.ormsession.flush(); self.ormsession.clear()
        # Fix ArtifactLinks
        for al in self.ormsession.find(M.ArtifactLink, {}):
            fix_aref(al.artifact_reference)
        # Fix feeds
        for f in self.ormsession.find(M.Feed, {}):
            fix_aref(f.artifact_reference)
        # Fix notifications
        for n in self.ormsession.find(M.Notification, {}):
            fix_aref(n.artifact_reference)
        # Fix tags
        for n in self.ormsession.find(M.TagEvent, {}):
            fix_aref(n.artifact_ref)
        for n in self.ormsession.find(M.UserTags, {}):
            fix_aref(n.artifact_reference)
        for n in self.ormsession.find(M.Tag, {}):
            fix_aref(n.artifact_ref)
        # fix PortalConfig
        for pc in self.ormsession.find(PM.PortalConfig):
            for layout in pc.layout:
                for w in layout.content:
                    w.mount_point = w.mount_point.lower().replace(' ', '_')
        # Fix thread (has explicit artifact_reference property)
        for t in self.ormsession.find(M.Thread, {}):
            fix_aref(t.artifact_reference)
        for t in self.ormsession.find(DM.ForumThread, {}):
            fix_aref(t.artifact_reference)
        self.ormsession.flush(); self.ormsession.clear()
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
            self.fix_artifact_cls(cls)

    def down(self):
        pass # Do nothing

    def fix_artifact_cls(self, cls):
        for obj in self.ormsession.find(cls, {}):
            for ref in obj.references:
                fix_aref(ref)
            for ref in obj.backreferences.itervalues():
                fix_aref(ref)
            self.ormsession.flush(); self.ormsession.clear()

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

def fix_aref(aref):
    if aref and aref.mount_point:
        aref.mount_point = aref.mount_point.lower().replace(' ', '_')
