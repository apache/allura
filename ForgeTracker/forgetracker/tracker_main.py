#-*- python -*-
import logging
import json, urllib, re
from datetime import datetime, timedelta
from urllib import urlencode
from webob import exc

# Non-stdlib imports
import pkg_resources
from tg import expose, validate, redirect, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request, response
from formencode import validators
from bson import ObjectId

from ming.orm.ormsession import ThreadLocalORMSession

# Pyforge-specific imports
from allura import model as M
from allura.lib import helpers as h
from allura.app import Application, SitemapEntry, DefaultAdminController
from allura.lib.search import search_artifact
from allura.lib.decorators import audit, react
from allura.lib.security import require, has_artifact_access, has_project_access
from allura.lib import widgets as w
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.controllers import AppDiscussionController, AppDiscussionRestController
from allura.controllers import attachments as ac
from allura.controllers import BaseController

# Local imports
from forgetracker import model as TM
from forgetracker import version

from forgetracker.widgets.ticket_form import TicketForm, TicketCustomField
from forgetracker.widgets.bin_form import BinForm
from forgetracker.widgets.ticket_search import TicketSearchResults, MassEdit, MassEditForm
from forgetracker.widgets.admin_custom_fields import TrackerFieldAdmin, TrackerFieldDisplay
from forgetracker.import_support import ImportSupport

log = logging.getLogger(__name__)

class W:
    thread=w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    date_field = ffw.DateField()
    markdown_editor = ffw.MarkdownEdit()
    label_edit = ffw.LabelEdit()
    attachment_list = ffw.AttachmentList()
    ticket_search_results = TicketSearchResults()
    mass_edit = MassEdit()
    mass_edit_form = MassEditForm()
    bin_form = BinForm()
    ticket_form = TicketForm()
    subscribe_form = SubscribeForm()
    auto_resize_textarea = ffw.AutoResizeTextarea()
    file_chooser = ffw.FileChooser()
    ticket_subscribe_form = SubscribeForm(thing='ticket')
    field_admin = TrackerFieldAdmin()
    field_display = TrackerFieldDisplay()
    ticket_custom_field = TicketCustomField

class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write', 'save_searches',
                    'unmoderated_post', 'post', 'moderate', 'admin']
    searchable=True
    tool_label='Tickets'
    default_mount_label='Tickets'
    default_mount_point='tickets'
    ordinal=6
    icons={
        24:'allura/images/tickets_24.png',
        32:'allura/images/tickets_32.png',
        48:'allura/images/tickets_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.globals = TM.Globals.query.get(app_config_id=config._id)
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
            t = TM.Ticket.query.get(ticket_num=int(ticket_num))
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
        menu_id = self.config.options.mount_label.title()
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def admin_menu(self):
        admin_url = c.project.url()+'admin/'+self.config.options.mount_point+'/'
        links = [SitemapEntry('Field Management', admin_url + 'fields', className='nav_child'),
                 SitemapEntry('Edit Searches', admin_url + 'bins/', className='nav_child')]
        # if self.permissions and has_artifact_access('configure', app=self)():
        #     links.append(SitemapEntry('Permissions', admin_url + 'permissions', className='nav_child'))
        return links

    def sidebar_menu(self):
        related_artifacts = []
        search_bins = []
        related_urls = []
        milestones = []
        ticket = request.path_info.split(self.url)[-1].split('/')[0]
        for bin in TM.Bin.query.find(dict(app_config_id=self.config._id)).sort('summary'):
            label = bin.shorthand_id()
            search_bins.append(SitemapEntry(
                    h.text.truncate(label, 72), bin.url(), className='nav_child',
                    small=c.app.globals.bin_counts.get(bin.shorthand_id())))
        for fld in c.app.globals.milestone_fields:
            milestones.append(SitemapEntry(h.text.truncate(fld.label, 72)))
            for m in fld.milestones:
                if m.complete: continue
                hits = 0
                for ms in c.app.globals.milestone_counts:
                    if ms['name'] == '%s:%s' % (fld.name, m.name):
                        hits = ms['hits']
                milestones.append(
                    SitemapEntry(
                        h.text.truncate(m.name, 72),
                        self.url + fld.name[1:] + '/' + m.name + '/',
                        className='nav_child',
                        small=hits))
        if ticket.isdigit():
            ticket = TM.Ticket.query.find(dict(app_config_id=self.config._id,ticket_num=int(ticket))).first()
        else:
            ticket = None
        links = [SitemapEntry('Create Ticket', self.config.url() + 'new/', ui_icon=g.icons['plus'])]
        if has_artifact_access('configure', app=self)():
            links.append(SitemapEntry('Edit Milestones', self.config.url() + 'milestones', ui_icon=g.icons['table']))
            links.append(SitemapEntry('Edit Searches', c.project.url() + 'admin/' + c.app.config.options.mount_point + '/bins/', ui_icon=g.icons['search']))
        links.append(SitemapEntry('View Stats', self.config.url() + 'stats', ui_icon=g.icons['stats']))
        if ticket:
            for aref in ticket.references+ticket.backreferences.values():
                artifact = M.ArtifactReference(aref).artifact
                if artifact is None: continue
                artifact = artifact.primary(TM.Ticket)
                if artifact.url() not in related_urls:
                    related_urls.append(artifact.url())
                    title = '%s: %s' % (artifact.type_s, artifact.shorthand_id())
                    related_artifacts.append(SitemapEntry(title, artifact.url(), className='nav_child'))
            if ticket.super_id:
                links.append(SitemapEntry('Supertask'))
                super = TM.Ticket.query.get(_id=ticket.super_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('[#{0}]'.format(super.ticket_num), super.url(), className='nav_child'))
            if ticket.sub_ids:
                links.append(SitemapEntry('Subtasks'))
            for sub_id in ticket.sub_ids or []:
                sub = TM.Ticket.query.get(_id=sub_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('[#{0}]'.format(sub.ticket_num), sub.url(), className='nav_child'))
            #links.append(SitemapEntry('Create New Subtask', '{0}new/?super_id={1}'.format(self.config.url(), ticket._id), className='nav_child'))

        links += milestones

        if len(search_bins):
            links.append(SitemapEntry('Searches'))
            links = links + search_bins
        if len(related_artifacts):
            links.append(SitemapEntry('Related Pages'))
            links = links + related_artifacts
        links.append(SitemapEntry('Help'))
        links.append(SitemapEntry('Ticket Help', self.config.url() + 'help', className='nav_child'))
        links.append(SitemapEntry('Markdown Syntax', self.config.url() + 'markdown_syntax', className='nav_child'))
        return links

    def has_custom_field(self, field):
        '''Checks if given custom field is defined. (Custom field names
        must start with '_'.)
        '''
        for f in self.globals.custom_fields:
            if f['name'] == field:
                return True
        return False
        
    def install(self, project):
        'Set up any default permissions and roles here'

        super(ForgeTrackerApp, self).install(project)
        # Setup permissions
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl.update(
            configure=c.project.roleids_with_permission('tool'),
            read=c.project.roleids_with_permission('read'),
            write=[role_auth],
            unmoderated_post=[role_auth],
            post=[role_anon],
            moderate=[role_developer],
            save_searches=[role_developer],
            admin=c.project.roleids_with_permission('tool'))
        self.globals = TM.Globals(app_config_id=c.app.config._id,
            last_ticket_num=0,
            open_status_names='open unread accepted pending',
            closed_status_names='closed wont-fix',
            # milestone_names='',
            custom_fields=[dict(
                    name='_milestone',
                    label='Milestone',
                    type='milestone',
                    milestones=[
                        dict(name='1.0', complete=False, due_date=None),
                        dict(name='2.0', complete=False, due_date=None)]) ])
        c.app.globals.invalidate_bin_counts()
        bin = TM.Bin(summary='Open Tickets', terms=self.globals.not_closed_query)
        bin.app_config_id = self.config._id
        bin.custom_fields = dict()
        bin = TM.Bin(summary='Recent Changes', terms=self.globals.not_closed_query, sort='mod_date_dt desc')
        bin.app_config_id = self.config._id
        bin.custom_fields = dict()


    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        TM.TicketAttachment.query.remove(app_config_id=c.app.config._id)
        app_config_id = {'app_config_id':c.app.config._id}
        TM.Ticket.query.remove(app_config_id)
        TM.Bin.query.remove(app_config_id)
        # model.Comment.query.remove(app_config_id)
        TM.Globals.query.remove(app_config_id)
        super(ForgeTrackerApp, self).uninstall(project)

class RootController(BaseController):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)
        self._discuss = AppDiscussionController()

    def paged_query(self, q, limit=None, page=0, sort=None, columns=None, **kw):
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

        
        limit, page, start = g.handle_paging(limit, page, default=25)
        count = 0
        tickets = []
        refined_sort = sort if sort else 'ticket_num_i asc'
        if  'ticket_num_i' not in refined_sort:
            refined_sort += ',ticket_num_i asc'
        try:
            if q:
                matches = search_artifact(
                    TM.Ticket, q,
                    rows=limit, sort=refined_sort, start=start, fl='ticket_num_i', **kw)
            else:
                matches = None
            solr_error = None
        except ValueError, e:
            solr_error = e.args[0]
            matches = []
        if matches:
            count = matches.hits
            # ticket_numbers is in sorted order
            ticket_numbers = [match['ticket_num_i'] for match in matches.docs]
            # but query, unfortunately, returns results in arbitrary order
            query = TM.Ticket.query.find(dict(app_config_id=c.app.config._id, ticket_num={'$in':ticket_numbers}))
            # so stick all the results in a dictionary...
            ticket_for_num = {}
            for t in query:
                ticket_for_num[t.ticket_num] = t
            # and pull them out in the order given by ticket_numbers
            tickets = [ ticket_for_num[tn] for tn in ticket_numbers if tn in ticket_for_num ]
            if not has_artifact_access('read')():
                my_role_ids = set(pr._id for pr in c.user.project_role().role_iter())
                tickets = [ t for t in tickets
                            if has_artifact_access('read', t, user_roles=my_role_ids) ]
        sortable_custom_fields=c.app.globals.sortable_custom_fields_shown_in_search()
        if not columns:
            columns = [dict(name='ticket_num', sort_name='ticket_num_i', label='Ticket Number', active=True),
                       dict(name='summary', sort_name='', label='Summary', active=True),
                       dict(name='_milestone', sort_name='', label='Milestone', active=True),
                       dict(name='status', sort_name='status_s', label='Status', active=True),
                       dict(name='assigned_to', sort_name='assigned_to_s', label='Owner', active=True)]
            for field in sortable_custom_fields:
                columns.append(dict(name=field['name'], sort_name=field['sortable_name'], label=field['label'], active=True))
        return dict(tickets=tickets,
                    sortable_custom_fields=sortable_custom_fields,
                    columns=columns,
                    count=count, q=q, limit=limit, page=page, sort=sort,
                    solr_error=solr_error, **kw)

    @with_trailing_slash
    @h.vardec
    @expose('jinja:tracker/index.html')
    def index(self, limit=250, columns=None, page=0, sort='ticket_num_i desc', **kw):
        require(has_artifact_access('read'))
        result = self.paged_query(c.app.globals.not_closed_query, sort=sort,
                                  limit=int(limit), columns=columns, page=page)
        c.subscribe_form = W.subscribe_form
        result['subscribed'] = M.Mailbox.subscribed()
        result['allow_edit'] = has_artifact_access('write')()
        c.ticket_search_results = W.ticket_search_results
        return result

    @without_trailing_slash
    @expose('jinja:tracker/milestones.html')
    def milestones(self, **kw):
        require(has_artifact_access('configure'))
        milestones = []
        c.date_field = W.date_field
        for fld in c.app.globals.milestone_fields:
            if fld.name == '_milestone':
                for m in fld.milestones:
                    total = 0
                    closed = 0
                    for ms in c.app.globals.milestone_counts:
                        if ms['name'] == '%s:%s' % (fld.name, m.name):
                            total = ms['hits']
                            closed = ms['closed']
                    milestones.append(dict(
                        name=m.name,
                        due_date=m.get('due_date'),
                        description=m.get('description'),
                        complete=m.get('complete'),
                        total=total,
                        closed=closed))
        return dict(milestones=milestones)

    @without_trailing_slash
    @h.vardec
    @expose()
    def update_milestones(self, field_name=None, milestones=None, **kw):
        require(has_artifact_access('configure'))
        update_counts = False
        for fld in c.app.globals.milestone_fields:
            if fld.name == field_name:
                for new in milestones:
                    for m in fld.milestones:
                        if m.name == new['old_name']:
                            m.name = new['new_name']
                            m.description = new['description']
                            m.due_date = new['due_date']
                            m.complete = new['complete'] == 'Closed'
                            if new['old_name'] != new['new_name']:
                                q = '%s:%s' % (fld.name, new['old_name'])
                                r = search_artifact(TM.Ticket, q)
                                ticket_numbers = [match['ticket_num_i'] for match in r.docs]
                                tickets = TM.Ticket.query.find(dict(
                                    app_config_id=c.app.config._id,
                                    ticket_num={'$in':ticket_numbers})).all()
                                for t in tickets:
                                    t.custom_fields[field_name] = new['new_name']
                                update_counts = True
                    if new['old_name'] == '' and new['new_name'] != '':
                        fld.milestones.append(dict(
                            name=new['new_name'],
                            description = new['description'],
                            due_date = new['due_date'],
                            complete = new['complete'] == 'Closed'))
                        update_counts = True
        if update_counts:
            c.app.globals.invalidate_bin_counts()
        redirect('milestones')

    @with_trailing_slash
    @h.vardec
    @expose('jinja:tracker/search.html')
    @validate(validators=dict(
            q=validators.UnicodeString(if_empty=None),
            history=validators.StringBool(if_empty=False),
            project=validators.StringBool(if_empty=False),
            limit=validators.Int(if_invalid=None),
            page=validators.Int(if_empty=0),
            sort=validators.UnicodeString(if_empty=None)))
    def search(self, q=None, query=None, project=None, columns=None, page=0, sort=None, **kw):
        require(has_artifact_access('read'))
        if query and not q:
            q = query
        c.bin_form = W.bin_form
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=kw.get('history'))))
        result = self.paged_query(q, page=page, sort=sort, columns=columns, **kw)
        result['allow_edit'] = has_artifact_access('write')()
        c.ticket_search_results = W.ticket_search_results
        return result

    @expose()
    def _lookup(self, ticket_num, *remainder):
        if ticket_num.isdigit():
            return TicketController(ticket_num), remainder
        elif remainder:
            return MilestoneController(self, ticket_num, remainder[0]), remainder[1:]
        else:
            raise exc.HTTPNotFound

    @with_trailing_slash
    @expose('jinja:tracker/new_ticket.html')
    def new(self, super_id=None, **kw):
        require(has_artifact_access('write'))
        c.ticket_form = W.ticket_form
        return dict(action=c.app.config.url()+'save_ticket',
                    super_id=super_id)

    @expose('jinja:tracker/markdown_syntax.html')
    def markdown_syntax(self):
        'Static page explaining markdown.'
        return dict()

    @expose('jinja:tracker/help.html')
    def help(self):
        'Static help page.'
        return dict()

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since=None, until=None, offset=None, limit=None):
        require(has_artifact_access('read'))
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed_type = 'atom'
        else:
            feed_type = 'rss'
        title = 'Recent changes to %s' % c.app.config.options.mount_point
        feed = M.Feed.feed(
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
        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        ticket_num = ticket_form.pop('ticket_num', None)
        comment = ticket_form.pop('comment', None)
        if ticket_num:
            ticket = TM.Ticket.query.get(
                app_config_id=c.app.config._id,
                ticket_num=ticket_num)
            if not ticket:
                raise Exception('Ticket number not found.')
        else:
            ticket = TM.Ticket(
                app_config_id=c.app.config._id,
                custom_fields=dict(),
                ticket_num=c.app.globals.next_ticket_num())
        ticket.update(ticket_form)
        redirect(str(ticket.ticket_num)+'/')

    @with_trailing_slash
    @expose('jinja:tracker/mass_edit.html')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   limit=validators.Int(if_empty=10),
                   page=validators.Int(if_empty=0),
                   sort=validators.UnicodeString(if_empty='ticket_num_i asc')))
    def edit(self, q=None, sort=None, **kw):
        require(has_artifact_access('write'))
        result = self.paged_query(q, sort=sort, **kw)
        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        result['globals'] = c.app.globals
        c.user_select = ffw.ProjectUserSelect()
        c.mass_edit = W.mass_edit
        c.mass_edit_form = W.mass_edit_form
        return result

    @expose()
    def update_tickets(self, **post_data):
        c.app.globals.invalidate_bin_counts()
        tickets = TM.Ticket.query.find(dict(
                _id={'$in':[ObjectId(id) for id in post_data['selected'].split(',')]},
                app_config_id=c.app.config._id)).all()
        for ticket in tickets:
            require(has_artifact_access('write', ticket))

        fields = set(['status'])
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

        custom_fields = set([cf.name for cf in c.app.globals.custom_fields or[]])
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
            count = TM.Ticket.query.find(dict(app_config_id=c.app.config._id,
                created_date={'$gte':when})).count()
        else:
            count = TM.Ticket.query.find(dict(app_config_id=c.app.config._id)).count()
        return count

    def ticket_comments_since(self, when=None):
        q = dict(
            discussion_id=c.app.config.discussion_id)
        if when is not None:
            q['timestamp'] = {'$gte':when}
        return M.Post.query.find(q).count()

    @with_trailing_slash
    @expose('jinja:tracker/stats.html')
    def stats(self):
        require(has_artifact_access('read'))
        globals = c.app.globals
        total = TM.Ticket.query.find(dict(app_config_id=c.app.config._id)).count()
        open = TM.Ticket.query.find(dict(app_config_id=c.app.config._id,status={'$in': list(globals.set_of_open_status_names)})).count()
        closed = TM.Ticket.query.find(dict(app_config_id=c.app.config._id,status={'$in': list(globals.set_of_closed_status_names)})).count()
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
            M.Mailbox.subscribe(type='direct')
        elif unsubscribe:
            M.Mailbox.unsubscribe()
        redirect(request.referer)

class BinController(BaseController):

    def __init__(self, summary=None, app=None):
        if summary is not None:
            self.summary = summary
        if app is not None:
            self.app = app

    @with_trailing_slash
    @expose('jinja:tracker/bin.html')
    def index(self, **kw):
        require(has_artifact_access('save_searches', app=self.app))
        c.bin_form = W.bin_form
        bins = TM.Bin.query.find()
        count=0
        count = len(bins)
        return dict(bins=bins or [], count=count, app=self.app)

    @with_trailing_slash
    @expose('jinja:tracker/bin.html')
    def bins(self):
        require(has_artifact_access('save_searches', app=self.app))
        c.bin_form = W.bin_form
        bins = TM.Bin.query.find()
        count=0
        count = len(bins)
        return dict(bins=bins or [], count=count, app=self.app)

    @with_trailing_slash
    @expose('jinja:tracker/new_bin.html')
    def newbin(self, q=None, **kw):
        require(has_artifact_access('save_searches', app=self.app))
        c.bin_form = W.bin_form
        return dict(q=q or '', bin=bin or '', modelname='Bin', page='New Bin', globals=self.app.globals)
        redirect(request.referer)

    @with_trailing_slash
    @h.vardec
    @expose()
    @validate(W.bin_form, error_handler=newbin)
    def save_bin(self, bin_form=None, **post_data):
        require(has_artifact_access('save_searches', app=self.app))
        self.app.globals.invalidate_bin_counts()
        if request.method != 'POST':
            raise Exception('save_bin must be a POST request')
        if bin_form['old_summary']:
            TM.Bin.query.find(dict(summary=bin_form['old_summary'])).first().delete()
        bin = TM.Bin(summary=bin_form['summary'], terms=bin_form['terms'])
        bin.app_config_id = self.app.config._id
        bin.custom_fields = dict()
        redirect('.')

    @with_trailing_slash
    @expose()
    def delbin(self, summary=None):
        bin = TM.Bin.query.find(dict(summary=summary,)).first()
        require(has_artifact_access('save_searches', app=self.app))
        self.app.globals.invalidate_bin_counts()
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


class TicketController(BaseController):

    def __init__(self, ticket_num=None):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = TM.Ticket.query.get(app_config_id=c.app.config._id,
                                                    ticket_num=self.ticket_num)
            self.attachment = AttachmentsController(self.ticket)
            # self.comments = CommentController(self.ticket)
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @with_trailing_slash
    @expose('jinja:tracker/ticket.html')
    @validate(dict(
            page=validators.Int(if_empty=0),
            limit=validators.Int(if_empty=10)))
    def index(self, page=0, limit=10, **kw):
        if self.ticket is not None:
            require(has_artifact_access('read', self.ticket))
            c.ticket_form = W.ticket_form
            c.thread = W.thread
            c.attachment_list = W.attachment_list
            c.subscribe_form = W.ticket_subscribe_form
            thread = self.ticket.discussion_thread
            post_count = M.Post.query.find(dict(discussion_id=thread.discussion_id, thread_id=thread._id)).count()
            c.ticket_custom_field = W.ticket_custom_field
            tool_subscribed = M.Mailbox.subscribed()
            if tool_subscribed:
                subscribed = False
            else:
                subscribed = M.Mailbox.subscribed(artifact=self.ticket)
            return dict(ticket=self.ticket, globals=c.app.globals,
                        allow_edit=has_artifact_access('write', self.ticket)(),
                        tool_subscribed=tool_subscribed,
                        subscribed=subscribed,
                        page=page, limit=limit, count=post_count)
        else:
            raise exc.HTTPNotFound, 'Ticket #%s does not exist.' % self.ticket_num

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=h.DateTimeConverter(if_empty=None, if_invalid=None),
            until=h.DateTimeConverter(if_empty=None, if_invalid=None),
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
        feed = M.Feed.feed(
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
    @h.vardec
    def update_ticket(self, **post_data):
        if not post_data.get('summary'):
            flash('You must provide a Name','error')
            redirect('.')
        c.app.globals.invalidate_bin_counts()
        if 'labels' in post_data:
            post_data['labels'] = post_data['labels'].split(',')
        else:
            post_data['labels'] = []
        self._update_ticket(post_data)

    @expose()
    @h.vardec
    @validate(W.ticket_form, error_handler=index)
    def update_ticket_from_widget(self, **post_data):
        c.app.globals.invalidate_bin_counts()
        data = post_data['ticket_form']
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
        comment = post_data.pop('comment', None)
        tags = post_data.pop('tags', None) or []
        labels = post_data.pop('labels', None) or []
        if labels:
            changes['labels'] = self.ticket.labels
            changes['labels'] = labels
        self.ticket.labels = labels
        for k in ['summary', 'description', 'status']:
            changes[k] = getattr(self.ticket, k)
            setattr(self.ticket, k, post_data.pop(k, ''))
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

        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        if 'attachment' in post_data:
            attachment = post_data['attachment']
            if hasattr(attachment, 'file'):
                self.ticket.attach(
                    attachment.filename, attachment.file, content_type=attachment.type)
        any_sums = False
        for cf in c.app.globals.custom_fields or []:
            if 'custom_fields.'+cf.name in post_data:
                value = post_data['custom_fields.'+cf.name]
                if cf.type == 'sum':
                    any_sums = True
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        value = 0
            elif cf.name == '_milestone' and cf.name in post_data:
                value = post_data[cf.name]
            # unchecked boolean won't be passed in, so make it False here
            elif cf.type == 'boolean':
                value = False
            else:
                value = ''
            if cf.type == 'number' and value == '':
                value = None
            if value is not None:
                changes[cf.name[1:]] =self.ticket.custom_fields.get(cf.name)
                self.ticket.custom_fields[cf.name] = value
                changes[cf.name[1:]] =self.ticket.custom_fields.get(cf.name)
        thread = self.ticket.discussion_thread
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
        if comment:
            self.ticket.discussion_thread.post(text=comment)
        redirect('.')

    @expose()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None):
        require(has_artifact_access('read', self.ticket))
        if subscribe:
            self.ticket.subscribe(type='direct')
        elif unsubscribe:
            self.ticket.unsubscribe()
        redirect(request.referer)

class AttachmentController(ac.AttachmentController):
    AttachmentClass = TM.TicketAttachment
    edit_perm = 'write'

class AttachmentsController(ac.AttachmentsController):
    AttachmentControllerClass = AttachmentController

NONALNUM_RE = re.compile(r'\W+')

class TrackerAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.bins = BinController(app=app)
        # if self.app.globals and self.app.globals.milestone_names is None:
        #     self.app.globals.milestone_names = ''

    @with_trailing_slash
    def index(self, **kw):
        redirect('permissions')

    @without_trailing_slash
    @expose('jinja:tracker/admin_fields.html')
    def fields(self, **kw):
        allow_config=has_artifact_access('configure', app=self.app)()
        if allow_config:
            c.form = W.field_admin
        else:
            c.form = W.field_display
        return dict(app=self.app, globals=self.app.globals)


    @without_trailing_slash
    @expose('jinja:tracker/admin_permissions.html')
    def permissions(self):
        return dict(app=self.app, globals=self.app.globals,
                    allow_config=has_artifact_access('configure', app=self.app)())

    @expose()
    def update_tickets(self, **post_data):
        pass

    @expose()
    @validate(W.field_admin, error_handler=fields)
    @h.vardec
    def set_custom_fields(self, **post_data):
        require(has_artifact_access('configure', app=self.app))
        self.app.globals.open_status_names=post_data['open_status_names']
        self.app.globals.closed_status_names=post_data['closed_status_names']
        custom_fields = post_data.get('custom_fields', [])
        for field in custom_fields:
            field['name'] = '_' + '_'.join([w for w in NONALNUM_RE.split(field['label'].lower()) if w])
            field['label'] = field['label'].title()
        self.app.globals.custom_fields=custom_fields
        flash('Fields updated')
        redirect(request.referer)

class RootRestController(BaseController):

    def __init__(self):
        self._discuss = AppDiscussionRestController()

    @expose('json:')
    def index(self, **kw):
        require(has_artifact_access('read'))
        return dict(tickets=[
            dict(ticket_num=t.ticket_num, summary=t.summary)
            for t in TM.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num') ])

    @expose()
    @h.vardec
    @validate(W.ticket_form, error_handler=h.json_validation_error)
    def new(self, ticket_form=None, **post_data):
        require(has_artifact_access('write'))
        c.app.globals.invalidate_bin_counts()
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        if c.app.globals.milestone_names is None:
            c.app.globals.milestone_names = ''
        ticket = TM.Ticket(
            app_config_id=c.app.config._id,
            custom_fields=dict(),
            ticket_num=c.app.globals.next_ticket_num())
        ticket_form.pop('ticket_num', None)
        ticket.update(ticket_form)
        redirect(str(ticket.ticket_num)+'/')

    @expose('json:')
    def validate_import(self, doc=None, options=None, **post_data):
        require(has_artifact_access('write'))
        migrator = ImportSupport()
        try:
            status = migrator.validate_import(doc, options, **post_data)
            return status
        except Exception, e:
            log.exception(e)
            return dict(status=False, errors=[str(e)])

    @expose('json:')
    def perform_import(self, doc=None, options=None, **post_data):
        require(has_project_access('tool'))
        if c.api_token.capabilities.get('import') != c.project.shortname:
            raise exc.HTTPForbidden(detail='Import is not allowed')

        migrator = ImportSupport()
        try:
            status = migrator.perform_import(doc, options, **post_data)
            return status
        except Exception, e:
            log.exception(e)
            return dict(status=False, errors=[str(e)])

    @expose()
    def _lookup(self, ticket_num, *remainder):
        return TicketRestController(ticket_num), remainder

class TicketRestController(BaseController):

    def __init__(self, ticket_num):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = TM.Ticket.query.get(app_config_id=c.app.config._id,
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
        c.app.globals.invalidate_bin_counts()
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        self.ticket.update(ticket_form)
        redirect('.')

class MilestoneController(BaseController):

    def __init__(self, root, field, milestone):
        for fld in c.app.globals.milestone_fields:
            if fld.name[1:] == field: break
        else:
            raise exc.HTTPNotFound()
        for m in fld.milestones:
            if m.name == milestone: break
        else:
            raise exc.HTTPNotFound()
        self.root = root
        self.field = fld
        self.milestone = m
        self.query = '%s:%s' % (fld.name, m.name)

    @with_trailing_slash
    @h.vardec
    @expose('jinja:tracker/milestone.html')
    @validate(validators=dict(
            limit=validators.Int(if_invalid=None),
            page=validators.Int(if_empty=0),
            sort=validators.UnicodeString(if_empty=None)))
    def index(self, q=None, project=None, columns=None, page=0, query=None, sort=None, **kw):
        require(has_artifact_access('read'))
        result = self.root.paged_query(self.query, page=page, sort=sort, columns=columns, **kw)
        result['allow_edit'] = has_artifact_access('write')()
        total = 0
        closed = 0
        for ms in c.app.globals.milestone_counts:
            if ms['name'] == '%s:%s' % (self.field.name, self.milestone.name):
                total = ms['hits']
                closed = ms['closed']
        result.update(
            field=self.field,
            milestone=self.milestone,
            total=total,
            closed=closed)
        c.ticket_search_results = W.ticket_search_results
        c.auto_resize_textarea = W.auto_resize_textarea
        return result
