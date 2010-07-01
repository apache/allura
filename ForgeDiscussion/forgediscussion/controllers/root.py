import logging
import pymongo
from urllib import urlencode, unquote

from tg import expose, validate, redirect
from tg.decorators import with_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import session

from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.security import require, has_artifact_access, has_project_access, require_authenticated
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

    def _check_security(self):
        require(has_artifact_access('read'))

    @expose('forgediscussion.templates.index')
    def index(self):
        c.subscription_form = self.W.subscription_form
        c.announcements_table = self.W.announcements_table
        announcements=model.ForumThread.query.find(dict(
                flags='Announcement')).all()
        forums = model.Forum.query.find(dict(
                        app_config_id=c.app.config._id,
                        parent_id=None)).all()
        threads = dict()
        for forum in forums:
            threads[forum._id] = model.ForumThread.query.find(dict(
                            discussion_id=forum._id)).sort('mod_date', pymongo.DESCENDING).limit(3).all()
        return dict(forums=forums,
                    threads=threads,
                    announcements=announcements)
                  
    @with_trailing_slash
    @expose('forgediscussion.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False),
                   project=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=False, project=False):
        'local tool search'
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=history)))
        results = []
        count=0
        if not q:
            q = ''
        else:
            results = search(
                q,
                fq=[
                    'is_history_b:%s' % history,
                    'project_id_s:%s' % c.project._id,
                    'mount_point_s:%s'% c.app.config.options.mount_point ])
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
        id = unquote(id)
        return ForumController(id), remainder

    @h.vardec
    @expose()
    @validate(W.forum_subscription_form)
    def subscribe(self, **kw):
        require_authenticated()
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

