#-*- python -*-
import logging
from mimetypes import guess_type
import json, urllib, re

# Non-stdlib imports
import pkg_resources
from tg import tmpl_context
from tg import expose, validate, redirect
from tg import request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

from ming.orm.base import session
from ming.orm.ormsession import ThreadLocalORMSession

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config, tag_artifact, DateTimeConverter
from pyforge.lib.search import search_artifact
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, TagEvent, UserTags, ArtifactReference, Feed

# Local imports
from forgetracker import model
from forgetracker import version

from forgetracker.widgets.ticket_form import ticket_form
from forgetracker.widgets.bin_form import bin_form

log = logging.getLogger(__name__)

class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'write', 'comment']

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.admin = TrackerAdminController(self)

    @audit('Tickets.#')
    def auditor(self, routing_key, data):
        log.info('Auditing data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @react('Tickets.#')
    def reactor(self, routing_key, data):
        log.info('Reacting to data from %s (%s)',
                 routing_key, self.config.options.mount_point)

    @property
    def sitemap(self):
        menu_id = self.config.options.mount_point.title()
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        related_artifacts = []
        search_bins = []
        related_urls = []
        ticket = request.path_info.split(self.url)[-1].split('/')[0]
        for bin in model.Bin.query.find():
            search_bins.append(SitemapEntry(bin.shorthand_id(), bin.url(), className='nav_child'))
        if ticket.isdigit():
            ticket = model.Ticket.query.find(dict(app_config_id=self.config._id,ticket_num=int(ticket))).first()
        else:
            ticket = None
        links = [
            SitemapEntry('Home', self.config.url()),
            SitemapEntry('Create New Ticket', self.config.url() + 'new/')]
        if ticket:
            links.append(SitemapEntry('Update this Ticket',ticket.url() + 'edit/'))
            for aref in ticket.references+ticket.backreferences.values():
                artifact = ArtifactReference(aref).to_artifact()
                if artifact.url() not in related_urls:
                    related_urls.append(artifact.url())
                    related_artifacts.append(SitemapEntry(artifact.shorthand_id(), artifact.url(), className='nav_child'))
        if len(related_artifacts):
            links.append(SitemapEntry('Related Artifacts'))
            links = links + related_artifacts
        links.append(SitemapEntry('Search', self.config.url() + 'search/'))
        links.append(SitemapEntry('Saved Searches'))
        links.append(SitemapEntry('All', self.config.url() + 'bins', className='nav_child'))
        if len(search_bins):
            links = links + search_bins
        if ticket:
            if ticket.super_id:
                links.append(SitemapEntry('Supertask'))
                super = model.Ticket.query.get(_id=ticket.super_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('Ticket {0}'.format(super.ticket_num), super.url(), className='nav_child'))
            links.append(SitemapEntry('Subtasks'))
            for sub_id in ticket.sub_ids or []:
                sub = model.Ticket.query.get(_id=sub_id, app_config_id=c.app.config._id)
                links.append(SitemapEntry('Ticket {0}'.format(sub.ticket_num), sub.url(), className='nav_child'))
            links.append(SitemapEntry('Create New Subtask', '{0}new/?super_id={1}'.format(self.config.url(), ticket._id), className='nav_child'))
        links.append(SitemapEntry('Help'))
        links.append(SitemapEntry('Ticket Help', 'help', className='nav_child'))
        links.append(SitemapEntry('Markdown Syntax', self.config.url() + 'markdown_syntax', className='nav_child'))
        return links

    @property
    def templates(self):
         return pkg_resources.resource_filename('forgetracker', 'templates')

    def install(self, project):
        'Set up any default permissions and roles here'

        self.uninstall(project)
        # Give the installing user all the permissions
        pr = c.user.project_role()
        for perm in self.permissions:
              self.config.acl[perm] = [ pr._id ]
        self.config.acl['read'].append(
            ProjectRole.query.get(name='*anonymous')._id)
        self.config.acl['comment'].append(
            ProjectRole.query.get(name='*authenticated')._id)
        model.Globals(app_config_id=c.app.config._id,
            last_ticket_num=0,
            status_names='open unread accepted pending closed',
            custom_fields=[])

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        model.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        app_config_id = {'app_config_id':c.app.config._id}
        model.Ticket.query.remove(app_config_id)
        model.Comment.query.remove(app_config_id)
        model.Globals.query.remove(app_config_id)

class RootController(object):

    def __init__(self):
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    def ordered_history(self, limit=None):
        q = []
        tickets = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num')
        for ticket in tickets:
            q.append(dict(change_type='ticket',change_date=ticket.created_date,ticket_num=ticket.ticket_num,change_text=ticket.summary))
            for comment in ticket.ordered_comments(limit):
                q.append(dict(change_type='comment',change_date=comment.created_date,ticket_num=ticket.ticket_num,change_text=comment.text))
        q.sort(reverse=True)
        if limit:
            n = len(q)
            if n > limit:
                z = []
                for i in range(0, limit):
                    z.append(q[i])
                q = z
        return q

    @with_trailing_slash
    @expose('forgetracker.templates.index')
    def index(self):
        tickets = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num')
        changes = self.ordered_history(5)
        return dict(tickets=tickets,changes=changes)

    @with_trailing_slash
    @expose('forgetracker.templates.search')
    @validate(dict(q=validators.UnicodeString(if_empty=None),
                   history=validators.StringBool(if_empty=False)))
    def search(self, q=None, history=None):
        'local plugin search'
        results = []
        tickets = []
        count=0
        if not q:
            q = ''
        else:
            results = search_artifact(model.Ticket, q, history)
            if results:
                query = model.Ticket.query.find(
                    dict(app_config_id=c.app.config._id,
                         ticket_num={'$in':[r['ticket_num_i'] for r in results.docs]}))
                tickets = query.all()
                count = len(tickets)
        return dict(q=q, history=history, tickets=tickets or [], count=count)

    @with_trailing_slash
    @expose('forgetracker.templates.bin')
    def bins(self):
        bins = model.Bin.query.find()
        count=0
        count = len(bins)
        return dict(bins=bins or [], count=count)

    def _lookup(self, ticket_num, *remainder):
        return TicketController(ticket_num), remainder

    @with_trailing_slash
    @expose('forgetracker.templates.new_bin')
    def newbin(self, q=None, **kw):
        require(has_artifact_access('write'))
        tmpl_context.form = bin_form
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        return dict(q=q or '', modelname='Bin', page='New Bin', globals=globals)

    @with_trailing_slash
    @expose('forgetracker.templates.new_ticket')
    def new(self, super_id=None, **kw):
        require(has_artifact_access('write'))
        tmpl_context.form = ticket_form
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        return dict(action=c.app.config.url()+'save_ticket',
                    super_id=super_id,
                    globals=globals)

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
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since, until, offset, limit):
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
    def save_bin(self, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_bin must be a POST request')
        bin = model.Bin()
        bin.app_config_id = c.app.config._id
        bin.custom_fields = dict()
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        for k,v in post_data.iteritems():
            setattr(bin, k, v)
        redirect('bins/')

    @expose()
    def save_ticket(self, ticket_num, tags, tags_old=None, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_ticket must be a POST request')
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if ticket_num:
            ticket = model.Ticket.query.get(app_config_id=c.app.config._id,
                                          ticket_num=int(ticket_num))
            if not ticket:
                raise Exception('Ticket number not found.')
            del post_data['ticket_num']
        else:
            ticket = model.Ticket()
            ticket.app_config_id = c.app.config._id
            ticket.custom_fields = dict()

            if tags: tags = tags.split(',')
            else: tags = []
            tag_artifact(ticket, c.user, tags)

            # FIX ME: need to lock around this increment or something
            globals.last_ticket_num += 1
            post_data['ticket_num'] = globals.last_ticket_num
            # FIX ME

        custom_sums = set()
        other_custom_fields = set()
        for cf in globals.custom_fields or []:
            (custom_sums if cf.type=='sum' else other_custom_fields).add(cf.name)
        for k, v in post_data.iteritems():
            if k in custom_sums:
                # sums must be coerced to numeric type
                try:
                    ticket.custom_fields[k] = float(v)
                except ValueError:
                    ticket.custom_fields[k] = 0
            elif k in other_custom_fields:
                # strings are good enough for any other custom fields
                ticket.custom_fields[k] = v
            elif k != 'super_id':
                # if it's not a custom field, set it right on the ticket (but don't overwrite super_id)
                setattr(ticket, k, v)
        ticket.commit()
        # flush so we can participate in a subticket search (if any)
        session(ticket).flush()
        super_id = post_data.get('super_id')
        if super_id:
            ticket.set_as_subticket_of(ObjectId(super_id))
        redirect(str(ticket.ticket_num)+'/')

    @with_trailing_slash
    @expose('forgetracker.templates.mass_edit')
    @validate(dict(q=validators.UnicodeString(if_empty=None)))
    def edit(self, q=None, **kw):
        tickets = []
        if q is None:
            tickets = model.Ticket.query.find(dict(app_config_id=c.app.config._id)).sort('ticket_num')
        else:
            results = search_artifact(model.Ticket, q)
            if results:
                # copied from search (above), can we factor this?
                query = model.Ticket.query.find(
                    dict(app_config_id=c.app.config._id,
                         ticket_num={'$in':[r['ticket_num_i'] for r in results.docs]}))
                tickets = query.all()
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        return dict(tickets=tickets, globals=globals)

    @expose()
    def update_tickets(self, **post_data):
        fields = set(['milestone', 'status'])
        values = {}
        for k in fields:
            v = post_data.get(k)
            if v: values[k] = v
        assigned_to = post_data.get('assigned_to')
        if assigned_to == '-':
            values['assigned_to_id'] = None
        elif assigned_to is not None:
            values['assigned_to_id'] = ObjectId(assigned_to)

        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        custom_fields = set([cf.name for cf in globals.custom_fields or[]])
        custom_values = {}
        for k in custom_fields:
            v = post_data.get(k)
            if v: custom_values[k] = v

        for id in post_data['selected'].split(','):
            ticket = model.Ticket.query.get(_id=ObjectId(id), app_config_id=c.app.config._id)
            for k, v in values.iteritems():
                ticket[k] = v
            for k, v in custom_values.iteritems():
                ticket.custom_fields[k] = v

        ThreadLocalORMSession.flush_all()


class TicketController(object):

    def __init__(self, ticket_num=None):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = model.Ticket.query.get(app_config_id=c.app.config._id,
                                                    ticket_num=self.ticket_num)
            self.attachment = AttachmentsController(self.ticket)
            self.comments = CommentController(self.ticket)
        setattr(self, 'feed.atom', self.feed)
        setattr(self, 'feed.rss', self.feed)

    @with_trailing_slash
    @expose('forgetracker.templates.ticket')
    def index(self, **kw):
        require(has_artifact_access('read', self.ticket))
        if self.ticket is not None:
            globals = model.Globals.query.get(app_config_id=c.app.config._id)
            return dict(ticket=self.ticket, globals=globals)
        else:
            redirect('not_found')

    @with_trailing_slash
    @expose('forgetracker.templates.edit_ticket')
    def edit(self, **kw):
        require(has_artifact_access('write', self.ticket))
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        user_tags = UserTags.upsert(c.user, self.ticket.dump_ref())
        return dict(ticket=self.ticket, globals=globals, user_tags=user_tags)

    @without_trailing_slash
    @expose()
    @validate(dict(
            since=DateTimeConverter(if_empty=None),
            until=DateTimeConverter(if_empty=None),
            offset=validators.Int(if_empty=None),
            limit=validators.Int(if_empty=None)))
    def feed(self, since, until, offset, limit):
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
    def update_ticket(self, tags, tags_old, **post_data):
        require(has_artifact_access('write', self.ticket))
        if request.method != 'POST':
            raise Exception('update_ticket must be a POST request')
        if tags: tags = tags.split(',')
        else: tags = []
        self.ticket.summary = post_data['summary']
        self.ticket.description = post_data['description']
        if post_data['assigned_to']:
            self.ticket.assigned_to_id = post_data['assigned_to']
        else:
            self.ticket.assigned_to_id = None
        self.ticket.status = post_data['status']
        tag_artifact(self.ticket, c.user, tags)

        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        any_sums = False
        for cf in globals.custom_fields or []:
            value = post_data[cf.name]
            if cf.type == 'sum':
                any_sums = True
                try:
                    value = float(value)
                except ValueError:
                    value = 0
            self.ticket.custom_fields[cf.name] = value
        self.ticket.commit()
        if any_sums:
            self.ticket.dirty_sums()
        redirect('edit/')

    @expose()
    def attach(self, file_info=None):
        require(has_artifact_access('write', self.ticket))
        filename = file_info.filename
        content_type = guess_type(filename)
        if content_type: content_type = content_type[0]
        else: content_type = 'application/octet-stream'
        with model.Attachment.create(
            content_type=content_type,
            filename=filename,
            ticket_id=self.ticket._id,
            app_config_id=c.app.config._id) as fp:
            while True:
                s = file_info.file.read()
                if not s: break
                fp.write(s)
        redirect('.')

class AttachmentsController(object):

    def __init__(self, ticket):
        self.ticket = ticket

    def _lookup(self, filename, *args):
        return AttachmentController(filename), args

class AttachmentController(object):

    def _check_security(self):
        require(has_artifact_access('read', self.ticket))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = model.Attachment.query.get(filename=filename)
        self.ticket = self.attachment.ticket

    @expose()
    def index(self, delete=False, embed=False):
        if request.method == 'POST':
            require(has_artifact_access('write', self.ticket))
            if delete: self.attachment.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename']
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

class CommentController(object):

    def __init__(self, ticket, comment_id=None):
        self.ticket = ticket
        self.comment_id = comment_id
        self.comment = model.Comment.query.get(slug=comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.ticket))
        if self.comment_id:
            c = self.comment.reply(text)
        else:
            c = self.ticket.reply(text)
        redirect(request.referer)

    @expose()
    def delete(self):
#        require(lambda:c.user._id == self.comment.author()._id)
#        self.comment.text = '[Text deleted by commenter]'
        self.comment.delete()
        redirect(request.referer)

    def _lookup(self, next, *remainder):
        if self.comment_id:
            return CommentController(
                self.ticket,
                self.comment_id + '/' + next), remainder
        else:
            return CommentController(
                self.ticket, next), remainder

NONALNUM_RE = re.compile(r'\W+')

class TrackerAdminController(DefaultAdminController):

    def __init__(self, app):
        self.app = app
        self.globals = model.Globals.query.get(app_config_id=self.app.config._id)

    @with_trailing_slash
    @expose('forgetracker.templates.admin')
    def index(self):
        return dict(app=self.app, globals=self.globals)

    @expose()
    def update_tickets(self, **post_data):
        pass

    @expose()
    def set_status_names(self, **post_data):
        self.globals.status_names = post_data['status_names']
        redirect('.')

    @expose()
    def set_custom_fields(self, **post_data):
        data = urllib.unquote_plus(post_data['custom_fields'])
        custom_fields = json.loads(data)
        for field in custom_fields:
            field['name'] = '_' + '_'.join([w for w in NONALNUM_RE.split(field['label'].lower()) if w])
            field['label'] = field['label'].title()
        self.globals.custom_fields = custom_fields
