#-*- python -*-
import logging
from mimetypes import guess_type
import json, urllib, re
from datetime import datetime, timedelta
from urllib import urlencode, unquote

# Non-stdlib imports
import pkg_resources
import Image
import tg
from tg import tmpl_context
from tg import expose, validate, redirect, flash
from tg import request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import session
from ming.orm.ormsession import ThreadLocalORMSession

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib import helpers as h
from pyforge.lib.search import search_artifact
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, TagEvent, UserTags, ArtifactReference, Feed, User
from pyforge.model import Subscriptions
from pyforge.lib import widgets as w
from pyforge.lib.widgets import form_fields as ffw
from pyforge.lib.widgets.subscriptions import SubscribeForm
from pyforge.controllers import AppDiscussionController, AppDiscussionRestController

# Local imports
from forgetracker import model
from forgetracker import version

from forgetracker.widgets.ticket_form import TicketForm, EditTicketForm
from forgetracker.widgets.bin_form import BinForm

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        offset=None, limit=None, page_size=None, total=None,
        style='linear')
    markdown_editor = ffw.MarkdownEdit()
    user_tag_edit = ffw.UserTagEdit()
    label_edit = ffw.LabelEdit()
    attachment_list = ffw.AttachmentList()
    bin_form = BinForm()
    ticket_form = TicketForm()
    edit_ticket_form = EditTicketForm()
    subscribe_form = SubscribeForm()
    ticket_subscribe_form = SubscribeForm(thing='ticket')

class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    searchable=True

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.api_root = RootRestController()
        self.admin = TrackerAdminController(self)

    def has_access(self, user, topic):
        return has_artifact_access('post', user=user)

    @audit('Tickets.msg.#')
    def message_auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)
        log.info('Headers are: %s', data['headers'])
        try:
            ticket_num = routing_key.split('.')[-1]
            t = model.Ticket.query.get(ticket_num=int(ticket_num))
        except:
            log.exception('Unexpected error routing tkt msg: %s', routing_key)
            return
        if t is None:
            log.error("Can't find ticket %s (routing key was %s)",
                      ticket_num, routing_key)
        super(ForgeTrackerApp, self).message_auditor(routing_key, data, t)

    @react('Tickets.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Field Management', admin_url + 'fields', className='nav_child')]
        # if self.permissions and has_artifact_access('configure', app=self)():
        #     links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

    def sidebar_menu(self):
        related_artifacts = []
        search_bins = []
        related_urls = []
        ticket = request.path_info.split(self.url)[-1].split('/')[0]
        tracker_globals = model.Globals.for_current_tracker()
        for bin in model.Bin.query.find().sort('summary'):
            label = '%s: (%s)' % (
                bin.shorthand_id(), tracker_globals.bin_counts.get(bin.shorthand_id(), 0))
            search_bins.append(SitemapEntry(label, bin.url(), className='nav_child'))
        if ticket.isdigit():
            ticket = model.Ticket.query.find(dict(app_config_id=self.config._id,ticket_num=int(ticket))).first()
        else:
            ticket = None
        links = [
            SitemapEntry('Create New Ticket', self.config.url() + 'new/', ui_icon='plus')]
        if ticket:
            links.append(SitemapEntry('Update this Ticket',ticket.url() + 'edit/', ui_icon='check'))
            for aref in ticket.references+ticket.backreferences.values():
                artifact = ArtifactReference(aref).to_artifact().primary(model.Ticket)
                if artifact.url() not in related_urls:
                    related_urls.append(artifact.url())
                    title = '%s: %s' % (artifact.type_s, artifact.shorthand_id())
                    related_artifacts.append(SitemapEntry(title, artifact.url(), className='nav_child'))
            if ticket.super_id:
                links.append(SitemapEntry('Supertask'))
                super = model.Ticket.query.get(_id=ticket.super_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('[#{0}]'.format(super.ticket_num), super.url(), className='nav_child'))
            if ticket.sub_ids:
                links.append(SitemapEntry('Subtasks'))
            for sub_id in ticket.sub_ids or []:
                sub = model.Ticket.query.get(_id=sub_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('[#{0}]'.format(sub.ticket_num), sub.url(), className='nav_child'))
            #links.append(SitemapEntry('Create New Subtask', '{0}new/?super_id={1}'.format(self.config.url(), ticket._id), className='nav_child'))
        if len(search_bins):
            links.append(SitemapEntry('Saved Searches'))
            links.append(SitemapEntry('All Searches', self.config.url() + 'bins', className='nav_child'))
            links = links + search_bins
        if len(related_artifacts):
            links.append(SitemapEntry('Related Artifacts'))
            links = links + related_artifacts
        links.append(SitemapEntry('Help'))
        links.append(SitemapEntry('Ticket Help', self.config.url() + 'help', className='nav_child'))
        links.append(SitemapEntry('Markdown Syntax', self.config.url() + 'markdown_syntax', className='nav_child'))
        links.append(SitemapEntry('Ticket Statistics'))
        links.append(SitemapEntry('Basic Stats', self.config.url() + 'stats', className='nav_child'))
        return links

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgetracker', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        super(ForgeTrackerApp, self).install(project)
        # Setup permissions
        role_developer = ProjectRole.query.get(name='Developer')._id
        role_auth = ProjectRole.query.get(name='*authenticated')._id
        role_anon = ProjectRole.query.get(name='*anonymous')._id
        self.config.acl.update(
            configure=c.project.acl['tool'],
            read=c.project.acl['read'],
            write=[role_auth],
            unmoderated_post=[role_auth],
            post=[role_anon],
            moderate=[role_developer],
            admin=c.project.acl['tool'])
        model.Globals(app_config_id=c.app.config._id,
            last_ticket_num=0,
            status_names='open unread accepted pending closed',
            milestone_names='',
            custom_fields=[])

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        model.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        app_config_id = {'app_config_id':c.app.config._id}
        model.Ticket.query.remove(app_config_id)
        # model.Comment.query.remove(app_config_id)
        model.Globals.query.remove(app_config_id)
        super(ForgeTrackerApp, self).uninstall(project)

class RootController(object):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        self._discuss = AppDiscussionController()
        self.bins = BinController()

    def paged_query(self, q, limit=None, page=0, sort=None, **kw):
        """Query tickets, sorting and paginating the result.

        We do the sorting and skipping right in SOLR, before we ever ask
        Mongo for the actual tickets.  Other keywords for
        search_artifact (e.g., history) or for SOLR are accepted through
        kw.  The output is intended to be used directly in templates,
        e.g., exposed controller methods can just:

            return paged_query(q, ...)

        If you want all the results at once instead of paged you have
        these options:
          - don't call this routine, search directly in mongo
          - call this routine with a very high limit and TEST that
            count<=limit in the result
        limit=-1 is NOT recognized as 'all'.  500 is a reasonable limit.
        """

        if limit:
            if c.user in (None, User.anonymous()):
                tg.session['results_per_page'] = limit
                tg.session.save()
            else:
                c.user.preferences.results_per_page = limit
        else:
            if c.user in (None, User.anonymous()):
                limit = 'results_per_page' in tg.session and tg.session['results_per_page'] or 25
            else:
                limit = c.user.preferences.results_per_page or 25
        sort = sort or 'ticket_num_i desc'
        page = max(page, 0)
        start = page * limit
        count = 0
        tickets = []
        refined_sort = sort if sort else 'ticket_num_i asc'
        if  'ticket_num_i' not in refined_sort:
            refined_sort += ',ticket_num_i asc'
        try:
            matches = search_artifact(model.Ticket, q, rows=limit, sort=refined_sort, start=start, fl='ticket_num_i', **kw) if q else None
            solr_error = None
        except ValueError, e:
            solr_error = e.args[0]
            matches = []
        if matches:
            count = matches.hits
            # ticket_numbers is in sorted order
            ticket_numbers = [match['ticket_num_i'] for match in matches.docs]
            # but query, unfortunately, returns results in arbitrary order
            query = model.Ticket.query.find(dict(app_config_id=c.app.config._id, ticket_num={'$in':ticket_numbers}))
            # so stick all the results in a dictionary...
            ticket_for_num = {}
            for t in query.all():
                ticket_for_num[t.ticket_num] = t
            # and pull them out in the order given by ticket_numbers
            tickets = [ticket_for_num[tn] for tn in ticket_numbers
                       if has_artifact_access('read', ticket_for_num[tn])()]
        tracker_globals = model.Globals.for_current_tracker()
        return dict(tickets=tickets,
                    sortable_custom_fields=tracker_globals.sortable_custom_fields_shown_in_search(),
                    count=count, q=q, limit=limit, page=page, sort=sort,
                    solr_error=solr_error, **kw)

    def ordered_history(self, limit=None):
        q = []
        tickets = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num')
        for ticket in tickets:
            q.append(dict(change_type='ticket',change_date=ticket.mod_date,
                          ticket_num=ticket.ticket_num,change_text=ticket.summary))
            for comment in ticket.discussion_thread().find_posts(limit=limit, style='linear'):
                # for comment in ticket.ordered_comments(limit):
                q.append(dict(change_type='comment',
                              change_date=comment.timestamp,
                              ticket_num=ticket.ticket_num,
                              change_text=comment.text))
        q.sort(reverse=True, key=lambda d:d['change_date'])
        return q[:limit]

    @with_trailing_slash
    @expose('forgetracker.templates.index')
    def index(self):
        require(has_artifact_access('read'))
        result = self.paged_query('!status:closed', sort='ticket_num_i desc', limit=500)
        result['changes'] = self.ordered_history(5)
        c.subscribe_form = W.subscribe_form
        result['subscribed'] = Subscriptions.upsert().subscribed()
        return result

    @with_trailing_slash
    @expose('forgetracker.templates.search')
    @validate(validators=dict(
            q=validators.UnicodeString(if_empty=None),
            history=validators.StringBool(if_empty=False),
            project=validators.StringBool(if_empty=False),
            limit=validators.Int(if_invalid=None),
            page=validators.Int(if_empty=0),
            sort=validators.UnicodeString(if_empty=None)))
    def search(self, q=None, project=None, **kw):
        require(has_artifact_access('read'))
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=kw.get('history'))))
        result = self.paged_query(q, **kw)
        result['allow_edit'] = has_artifact_access('write')()
        return result

    @expose()
    def _lookup(self, ticket_num, *remainder):
        return TicketController(ticket_num), remainder

    @with_trailing_slash
    @expose('forgetracker.templates.new_ticket')
    def new(self, super_id=None, **kw):
        require(has_artifact_access('write'))
        c.ticket_form = W.ticket_form
        return dict(action=c.app.config.url()+'save_ticket',
                    super_id=super_id)

    @expose('forgetracker.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose('forgetracker.templates.markdown_syntax')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @expose('forgetracker.templates.help')
    def help(self):
        'Static help page.'
        return dict()

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None),
            until=h.DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        require(has_artifact_access('read'))
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = Feed.feed(
            {'artifact_reference.mount_point':c.app.config.options.mount_point,
             'artifact_reference.project_id':c.project._id},
            feed_type,
            title,
            c.app.url,
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @expose()
    @h.vardec
    @validate(W.ticket_form, error_handler=new)
    def save_ticket(self, ticket_form=None, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        if globals.milestone_names is None:
            globals.milestone_names = ''
        ticket_num = ticket_form.pop('ticket_num', None)
        if ticket_num:
            ticket = model.Ticket.query.get(
                app_config_id=c.app.config._id,
                ticket_num=ticket_num)
            if not ticket:
                raise Exception('Ticket number not found.')
        else:
            ticket = model.Ticket(
                app_config_id=c.app.config._id,
                custom_fields=dict(),
                ticket_num=globals.next_ticket_num())
        ticket.update(ticket_form, globals)
        for u in ProjectRole.query.find({'name':'Admin'}).first().users_with_role():
            ticket.subscribe(user=u)
        redirect(str(ticket.ticket_num)+'/')

    @with_trailing_slash
    @expose('forgetracker.templates.mass_edit')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   limit=validators.Int(if_empty=10),
                   page=validators.Int(if_empty=0),
                   sort=validators.UnicodeString(if_empty='ticket_num_i asc')))
    def edit(self, q=None, sort=None, **kw):
        require(has_artifact_access('write'))
        result = self.paged_query(q, sort=sort, **kw)
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if globals.milestone_names is None:
            globals.milestone_names = ''
        result['globals'] = globals
        c.user_select = ffw.ProjectUserSelect()
        return result

    @expose()
    def update_tickets(self, **post_data):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        tickets = model.Ticket.query.find(dict(
                _id={'$in':[ObjectId(id) for id in post_data['selected'].split(',')]},
                app_config_id=c.app.config._id)).all()
        for ticket in tickets:
            require(has_artifact_access('write', ticket))

        fields = set(['milestone', 'status'])
        values = {}
        for k in fields:
            v = post_data.get(k)
            if v: values[k] = v
        assigned_to = post_data.get('assigned_to')
        if assigned_to == '-':
            values['assigned_to_id'] = None
        elif assigned_to is not None:
            user = c.project.user_in_project(assigned_to)
            if user:
                values['assigned_to_id'] = user._id

        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        custom_fields = set([cf.name for cf in globals.custom_fields or[]])
        custom_values = {}
        for k in custom_fields:
            v = post_data.get(k)
            if v: custom_values[k] = v

        for ticket in tickets:
            for k, v in values.iteritems():
                setattr(ticket, k, v)
            for k, v in custom_values.iteritems():
                ticket.custom_fields[k] = v

        ThreadLocalORMSession.flush_all()

# tickets
# open tickets
# closed tickets
# new tickets in the last 7/14/30 days
# of comments on tickets
# of new comments on tickets in 7/14/30
# of ticket changes in the last 7/14/30

    def tickets_since(self, when=None):
        count = 0
        if when:
            count = model.Ticket.query.find(dict(app_config_id=c.app.config._id,
                created_date={'$gte':when})).count()
        else:
            count = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).count()
        return count

    def ticket_comments_since(self, when=None):
        count = 0
        q = []
        tickets = model.Ticket.query.find(dict(app_config_id=c.app.config._id))
        if when:
            for ticket in tickets:
                posts = ticket.discussion_thread().find_posts(limit=None,
                        style='linear', timestamp={'$gte':when})
                count = count + len(posts)
        else:
            for ticket in tickets:
                posts = ticket.discussion_thread().find_posts(limit=None, style='linear')
                count = count + len(posts)
        return count

    @with_trailing_slash
    @expose('forgetracker.templates.stats')
    def stats(self):
        require(has_artifact_access('read'))
        total = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).count()
        open = model.Ticket.query.find(dict(app_config_id=c.app.config._id,status='open')).count()
        closed = model.Ticket.query.find(dict(app_config_id=c.app.config._id,status='closed')).count()
        now = datetime.utcnow()
        week = timedelta(weeks=1)
        fortnight = timedelta(weeks=2)
        month = timedelta(weeks=4)
        week_ago = now - week
        fortnight_ago = now - fortnight
        month_ago = now - month
        week_tickets = self.tickets_since(week_ago)
        fortnight_tickets = self.tickets_since(fortnight_ago)
        month_tickets = self.tickets_since(month_ago)
        comments=self.ticket_comments_since()
        week_comments=self.ticket_comments_since(week_ago)
        fortnight_comments=self.ticket_comments_since(fortnight_ago)
        month_comments=self.ticket_comments_since(month_ago)
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        c.user_select = ffw.ProjectUserSelect()
        return dict(
                now=str(now),
                week_ago=str(week_ago),
                fortnight_ago=str(fortnight_ago),
                month_ago=str(month_ago),
                week_tickets=week_tickets,
                fortnight_tickets=fortnight_tickets,
                month_tickets=month_tickets,
                comments=comments,
                week_comments=week_comments,
                fortnight_comments=fortnight_comments,
                month_comments=month_comments,
                total=total,
                open=open,
                closed=closed,
                globals=globals)

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        require(has_artifact_access('read'))
        if subscribe:
            Subscriptions.upsert().subscribe('direct')
        elif unsubscribe:
            Subscriptions.upsert().unsubscribe()
        redirect(request.referer)

class BinController(object):

    def __init__(self, summary=None):
        if summary is not None:
            self.summary = summary

    @with_trailing_slash
    @expose('forgetracker.templates.bin')
    def index(self, **kw):
        require(has_artifact_access('read'))
        bins = model.Bin.query.find()
        count=0
        count = len(bins)
        return dict(bins=bins or [], count=count)

    @with_trailing_slash
    @expose('forgetracker.templates.bin')
    def bins(self):
        require(has_artifact_access('read'))
        bins = model.Bin.query.find()
        count=0
        count = len(bins)
        return dict(bins=bins or [], count=count)
        redirect('bins/')

    @with_trailing_slash
    @expose('forgetracker.templates.new_bin')
    def newbin(self, q=None, **kw):
        require(has_artifact_access('write'))
        c.bin_form = W.bin_form
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        return dict(q=q or '', bin=bin or '', modelname='Bin', page='New Bin', globals=globals)
        redirect(request.referer)

    @with_trailing_slash
    @h.vardec
    @expose()
    @validate(W.bin_form, error_handler=newbin)
    def save_bin(self, bin_form=None, **post_data):
        require(has_artifact_access('write'))
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        if request.method != 'POST':
            raise Exception('save_bin must be a POST request')
        bin = model.Bin(summary=bin_form['summary'], terms=bin_form['terms'])
        bin.app_config_id = c.app.config._id
        bin.custom_fields = dict()
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        redirect('%ssearch/?q=%s' % (c.app.url, bin_form['terms']))

    @with_trailing_slash
    @expose()
    def delbin(self, summary=None):
        bin = model.Bin.query.find(dict(summary=summary,)).first()
        require(has_artifact_access('write', bin))
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        bin.delete()
        redirect(request.referer)

class changelog(object):
    """
    A dict-like object which keeps log about what keys have been changed.

    >>> c = changelog()
    >>> c['foo'] = 'bar'
    >>> c['bar'] = 'baraban'
    >>> c.get_changed()
    []
    >>> c['bar'] = 'drums'
    >>> c.get_changed()
    [('bar', ('baraban', 'drums'))]

    The .get_changed() lists key in the same order they were added to the changelog:

    >>> c['foo'] = 'quux'
    >>> c.get_changed()
    [('foo', ('bar', 'quux')), ('bar', ('baraban', 'drums'))]

    When the key is set multiple times it still compares to the value that was set first.
    If changed value equals to the value set first time it is not included.

    >>> c['foo'] = 'bar'
    >>> c['bar'] = 'koleso'
    >>> c.get_changed()
    [('bar', ('baraban', 'koleso'))]
    """

    def __init__(self):
        self.keys = [] # to track insertion order
        self.originals = {}
        self.data = {}

    def __setitem__(self, key, value):
        if key not in self.keys:
            self.keys.append(key)
        if key not in self.originals:
            self.originals[key] = value
        self.data[key] = value

    def get_changed(self):
        t = []
        for key in self.keys:
            if key in self.originals:
                orig_value = self.originals[key]
                curr_value = self.data[key]
                if not orig_value == curr_value:
                    t.append((key, (orig_value, curr_value)))
        return t


class TicketController(object):

    def __init__(self, ticket_num=None):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = model.Ticket.query.get(app_config_id=c.app.config._id,
                                                    ticket_num=self.ticket_num)
            self.attachment = AttachmentsController(self.ticket)
            # self.comments = CommentController(self.ticket)
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @with_trailing_slash
    @expose('forgetracker.templates.ticket')
    def index(self, **kw):
        require(has_artifact_access('read', self.ticket))
        c.thread = W.thread
        c.markdown_editor = W.markdown_editor
        c.attachment_list = W.attachment_list
        c.label_edit = W.label_edit
        c.user_select = ffw.ProjectUserSelect()
        c.attachment_list = W.attachment_list
        c.subscribe_form = W.ticket_subscribe_form
        if self.ticket is not None:
            globals = model.Globals.query.get(app_config_id=c.app.config._id)
            if globals.milestone_names is None:
                globals.milestone_names = ''
            return dict(ticket=self.ticket, globals=globals,
                        allow_edit=has_artifact_access('write', self.ticket)(),
                        subscribed=Subscriptions.upsert().subscribed(artifact=self.ticket))
        else:
            redirect('not_found')

    @with_trailing_slash
    @expose('forgetracker.templates.edit_ticket')
    def edit(self, **kw):
        require(has_artifact_access('write', self.ticket))
        c.ticket_form = W.edit_ticket_form
        c.thread = W.thread
        c.attachment_list = W.attachment_list
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if globals.milestone_names is None:
            globals.milestone_names = ''
        return dict(ticket=self.ticket, globals=globals)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None),
            until=h.DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        require(has_artifact_access('read', self.ticket))
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %d: %s' % (
            self.ticket.ticket_num, self.ticket.summary)
        feed = Feed.feed(
            {'artifact_reference':self.ticket.dump_ref()},
            feed_type,
            title,
            self.ticket.url(),
            title,
            since, until, offset, limit)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        return feed.writeString('utf-8')

    @expose()
    def update_ticket(self, **post_data):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        self._update_ticket(post_data)

    @expose()
    @h.vardec
    @validate(W.edit_ticket_form, error_handler=edit)
    def update_ticket_from_widget(self, **post_data):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        data = post_data['edit_ticket_form']
        # icky: handle custom fields like the non-widget form does
        if 'custom_fields' in data:
            for k in data['custom_fields']:
                data['custom_fields.'+k] = data['custom_fields'][k]
        self._update_ticket(data)
        
    def _update_ticket(self, post_data):
        require(has_artifact_access('write', self.ticket))
        if request.method != 'POST':
            raise Exception('update_ticket must be a POST request')
        changes = changelog()
        if 'tags' in post_data and len(post_data['tags']):
            tags = post_data['tags'].split(',')
            del post_data['tags']
        else:
            tags = []
        if 'labels' in post_data and len(post_data['labels']):
            changes['labels'] = self.ticket.labels
            self.ticket.labels = post_data['labels'].split(',')
            changes['labels'] = self.ticket.labels
            del post_data['labels']
        else:
            self.ticket.labels = []
        for k in ['summary', 'description', 'status', 'milestone']:
            changes[k] = getattr(self.ticket, k)
            if k in post_data:
                setattr(self.ticket, k, post_data[k])
            else:
                setattr(self.ticket, k, '')
            changes[k] = getattr(self.ticket, k)
        if 'assigned_to' in post_data:
            who = post_data['assigned_to']
            changes['assigned_to'] = self.ticket.assigned_to
            if who:
                user = c.project.user_in_project(who)
                if user:
                    self.ticket.assigned_to_id = user._id
            else:
                self.ticket.assigned_to_id = None
            changes['assigned_to'] = self.ticket.assigned_to
        h.tag_artifact(self.ticket, c.user, tags)

        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if globals.milestone_names is None:
            globals.milestone_names = ''
        any_sums = False
        for cf in globals.custom_fields or []:
            if 'custom_fields.'+cf.name in post_data:
                value = post_data['custom_fields.'+cf.name]
                if cf.type == 'sum':
                    any_sums = True
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        value = 0
            # unchecked boolean won't be passed in, so make it False here
            elif cf.type == 'boolean':
                value = False
            else:
                value = ''
            changes['custom_field_%s'%cf.name] =self.ticket.custom_fields.get(cf.name)
            self.ticket.custom_fields[cf.name] = value
            changes['custom_field_%s'%cf.name] =self.ticket.custom_fields.get(cf.name)
        thread = self.ticket.discussion_thread()
        latest_post = thread.posts and thread.posts[-1] or None
        post = None
        if latest_post and latest_post.author() == c.user:
            now = datetime.utcnow()
            folding_window = timedelta(seconds=60*5)
            if (latest_post.timestamp + folding_window) > now:
                post = latest_post
                log.info('Folding ticket updates into %s', post)
        tpl_fn = pkg_resources.resource_filename(
            'forgetracker', 'data/ticket_changed_tmpl')
        change_text = h.render_genshi_plaintext(tpl_fn,
            changelist=changes.get_changed())
        if post is None:
            post = thread.add_post(text=change_text)
        else:
            post.text += '\n\n' + change_text
        self.ticket.commit()
        if any_sums:
            self.ticket.dirty_sums()
        redirect('.')

    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('write', self.ticket))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        if h.supported_by_PIL(file_info.type):
            image = Image.open(file_info.file)
            format = image.format
            with model.Attachment.create(
                content_type=content_type,
                filename=filename,
                ticket_id=self.ticket._id,
                type="attachment",
                app_config_id=c.app.config._id) as fp:
                fp_name = fp.name
                image.save(fp, format)
            image = h.square_image(image)
            image.thumbnail((150, 150), Image.ANTIALIAS)
            with model.Attachment.create(
                content_type=content_type,
                filename=fp_name,
                ticket_id=self.ticket._id,
                type="thumbnail",
                app_config_id=c.app.config._id) as fp:
                image.save(fp, format)
        else:
            with model.Attachment.create(
                content_type=content_type,
                filename=filename,
                ticket_id=self.ticket._id,
                type="attachment",
                app_config_id=c.app.config._id) as fp:
                while True:
                    s = file_info.file.read()
                    if not s: break
                    fp.write(s)
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        require(has_artifact_access('read', self.ticket))
        if subscribe:
            Subscriptions.upsert().subscribe('direct', artifact=self.ticket)
        elif unsubscribe:
            Subscriptions.upsert().unsubscribe(artifact=self.ticket)
        redirect(request.referer)

class AttachmentsController(object):

    def __init__(self, ticket):
        self.ticket = ticket

    @expose()
    def _lookup(self, filename, *args):
        filename = unquote(filename)
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.ticket))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.thumbnail = model.Attachment.by_metadata(filename=filename).first()
        self.ticket = self.attachment.ticket

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('write', self.ticket))
            if delete:
                self.attachment.delete()
                if self.thumbnail:
                    self.thumbnail.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

    @expose()
    def thumb(self, embed=False):
        with self.thumbnail.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

NONALNUM_RE = re.compile(r'\W+')

class TrackerAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.globals = model.Globals.query.get(app_config_id=self.app.config._id)
        if self.globals and self.globals.milestone_names is None:
            self.globals.milestone_names = ''

    @with_trailing_slash
    def index(self):
        redirect('permissions')

    @without_trailing_slash
    @expose('forgetracker.templates.admin_fields')
    def fields(self):
        return dict(app=self.app, globals=self.globals,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @without_trailing_slash
    @expose('forgetracker.templates.admin_permissions')
    def permissions(self):
        return dict(app=self.app, globals=self.globals,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @expose()
    def update_tickets(self, **post_data):
        pass

    @expose()
    def set_custom_fields(self, **post_data):
        require(has_artifact_access('configure', app=self.app))
        self.globals.status_names=post_data['status_names']
        self.globals.milestone_names=post_data['milestone_names']
        data = urllib.unquote_plus(post_data['custom_fields'])
        custom_fields = json.loads(data)
        for field in custom_fields:
            field['name'] = '_' + '_'.join([w for w in NONALNUM_RE.split(field['label'].lower()) if w])
            field['label'] = field['label'].title()
        self.globals.custom_fields=custom_fields
        flash('Fields updated')

class RootRestController(object):

    def __init__(self):
        self._discuss = AppDiscussionRestController()

    @expose('json:')
    def index(self, **kw):
        require(has_artifact_access('read'))
        return dict(tickets=[
            dict(ticket_num=t.ticket_num, summary=t.summary)
            for t in model.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num') ])

    @expose()
    @h.vardec
    @validate(W.ticket_form, error_handler=h.json_validation_error)
    def new(self, ticket_form=None, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if globals.milestone_names is None:
            globals.milestone_names = ''
        ticket = model.Ticket(
            app_config_id=c.app.config._id,
            custom_fields=dict(),
            ticket_num=globals.next_ticket_num())
        ticket_form.pop('ticket_num', None)
        ticket.update(ticket_form, globals)
        redirect(str(ticket.ticket_num)+'/')

    @expose()
    def _lookup(self, ticket_num, *remainder):
        return TicketRestController(ticket_num), remainder

class TicketRestController(object):

    def __init__(self, ticket_num):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = model.Ticket.query.get(app_config_id=c.app.config._id,
                                                    ticket_num=self.ticket_num)

    @expose('json:')
    def index(self, **kw):
        require(has_artifact_access('read', self.ticket))
        return dict(ticket=self.ticket)

    @expose()
    @h.vardec
    @validate(W.ticket_form, error_handler=h.json_validation_error)
    def save(self, ticket_form=None, **post_data):
        require(has_artifact_access('write', self.ticket))
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.invalidate_bin_counts()
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        if globals.milestone_names is None:
            globals.milestone_names = ''
        self.ticket.update(ticket_form, globals)
        redirect('.')

