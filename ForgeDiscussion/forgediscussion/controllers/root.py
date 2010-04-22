import logging

from tg import expose, validate, redirect
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import session

from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole
from pyforge.lib.search import search
from pyforge.lib import helpers as h

from .forum import ForumController
from forgediscussion import model
from forgediscussion import widgets as FW
from pyforge.lib.widgets import discuss as DW

log = logging.getLogger(__name__)

class RootController(object):

    class W(object):
        forum_subscription_form=FW.ForumSubscriptionForm()
        subscription_form=DW.SubscriptionForm(show_discussion_email=True, allow_create_thread=True, show_subject=True)
        announcements_table=FW.AnnouncementsTable()

    @expose('forgediscussion.templates.index')
    def index(self):
        c.subscription_form = self.W.subscription_form
        c.announcements_table = self.W.announcements_table
        announcements=model.ForumThread.query.find(dict(
                flags='Announcement')).all()
        return dict(forums=model.Forum.query.find(dict(
                app_config_id=c.app.config._id,
                parent_id=None)).all(),
                    announcements=announcements)
                  
    @expose('forgediscussion.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local plugin search'
        results = []
        count=0
        if not q:
            q = ''
        else:
            search_query = '''%s
            AND is_history_b:%s
            AND mount_point_s:%s''' % (
                q, history, c.app.config.options.mount_point)
            results = search(search_query)
            if results: count=results.hits
        return dict(q=q, history=history, results=results or [], count=count)

    @expose('forgediscussion.templates.markdown_syntax')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @expose('forgediscussion.templates.help')
    def help(self):
        'Static help page.'
        return dict()

    @expose()
    def _lookup(self, id, *remainder):
        return ForumController(id), remainder

    @h.vardec
    @expose()
    @validate(W.forum_subscription_form)
    def subscribe(self, **kw):
        forum = kw.pop('forum', [])
        thread = kw.pop('thread', [])
        objs = []
        for data in forum:
            objs.append(dict(obj=model.Forum.query.get(shortname=data['shortname']),
                             subscribed=bool(data.get('subscribed'))))
        for data in thread:
            objs.append(dict(obj=model.Thread.query.get(_id=data['id']),
                             subscribed=bool(data.get('subscribed'))))
        for obj in objs:
            if obj['subscribed']:
                obj['obj'].subscriptions[str(c.user._id)] = True
            else:
                obj['obj'].subscriptions.pop(str(c.user._id), None)
        redirect(request.referer)

