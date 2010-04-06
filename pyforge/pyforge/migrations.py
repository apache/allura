from pylons import c
from flyway import Migration
import ming
from ming.orm import mapper, ORMSession, session

from pyforge import model as M
from pyforge.ext.project_home import model as PM
from forgetracker import model as TM
from forgewiki import model as WM
from helloforge import model as HM
from forgediscussion import model as DM
from forgescm import model as SM


class V0(Migration):
    version = 0
    def up(self): pass
    def down(self):  pass

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
            n.name = n.name.lower()
            n.shortname_prefix = n.shortname_prefix.lower()
        # Fix Projects
        for p in self.ormsession.find(M.Project, {}):
            p.shortname = p.shortname.lower()
        # Fix AppConfigs
        for ac in self.ormsession.find(M.AppConfig, {}):
            ac.options.mount_point = ac.options.mount_point.lower()
            if ac.plugin_name == 'Forum':
                ac.plugin_name = 'Discussion'
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
                    w.mount_point = w.mount_point.lower()
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
            SM.Repository,
            SM.Commit,
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

def fix_aref(aref):
    if aref and aref.mount_point:
        aref.mount_point = aref.mount_point.lower()
