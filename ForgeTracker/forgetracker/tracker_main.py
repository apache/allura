#-*- python -*-
import logging
from mimetypes import guess_type

# Non-stdlib imports
import pkg_resources
from tg import tmpl_context
from tg import expose, validate, redirect
from tg import request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from pylons import g, c, request
from formencode import validators
from pymongo.bson import ObjectId

# Pyforge-specific imports
from pyforge.app import Application, ConfigOption, SitemapEntry, DefaultAdminController
from pyforge.lib.helpers import push_config
from pyforge.lib.search import search
from pyforge.lib.decorators import audit, react
from pyforge.lib.security import require, has_artifact_access
from pyforge.model import ProjectRole, TagEvent, UserTags

# Local imports
from forgetracker import model
from forgetracker import version

from forgetracker.widgets.ticket_form import ticket_form

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
        menu_id = 'ForgeTracker (%s)' % self.config.options.mount_point
        with push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()] ]

    def sidebar_menu(self):
        return [
            SitemapEntry('Home', self.config.url()),
            SitemapEntry('Search', self.config.url() + 'search'),
            SitemapEntry('New Ticket', self.config.url() + 'new/'),
            ]

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
        model.Globals(app_config_id=c.app.config._id, last_ticket_num=0, status_names='open,unread,accepted,pending,closed')

    def uninstall(self, project):
        "Remove all the plugin's artifacts from the database"
        model.Attachment.query.remove({'metadata.app_config_id':c.app.config._id})
        app_config_id = {'app_config_id':c.app.config._id}
        model.Ticket.query.remove(app_config_id)
        model.Comment.query.remove(app_config_id)
        model.Globals.query.remove(app_config_id)

class RootController(object):

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

    @expose('forgetracker.templates.search')
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

    def _lookup(self, ticket_num, *remainder):
        return TicketController(ticket_num), remainder

    @with_trailing_slash
    @expose('forgetracker.templates.new_ticket')
    def new(self, **kw):
        require(has_artifact_access('write'))
        tmpl_context.form = ticket_form
        return dict(modelname='Ticket',
            page='New Ticket')

    @expose('forgetracker.templates.not_found')
    def not_found(self, **kw):
        return dict()

    @expose()
    def save_ticket(self, ticket_num, **post_data):
        require(has_artifact_access('write'))
        if request.method != 'POST':
            raise Exception('save_new must be a POST request')
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
            globals = model.Globals.query.get(app_config_id=c.app.config._id)

            # FIX ME: need to lock around this increment or something
            globals.last_ticket_num += 1
            post_data['ticket_num'] = globals.last_ticket_num
            # FIX ME

        for k,v in post_data.iteritems():
            setattr(ticket, k, v)
        redirect(str(ticket.ticket_num)+'/')


class TicketController(object):

    def __init__(self, ticket_num=None):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = model.Ticket.query.get(app_config_id=c.app.config._id,
                                                    ticket_num=self.ticket_num)
            self.attachment = AttachmentsController(self.ticket)
            self.comments = CommentController(self.ticket)

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

    @expose()
    def update_ticket(self, tags, tags_old, **post_data):
        tags = tags.split(',')
        require(has_artifact_access('write', self.ticket))
        if request.method != 'POST':
            raise Exception('update_ticket must be a POST request')
        self.ticket.summary = post_data['summary']
        self.ticket.description = post_data['description']
      # self.ticket.assigned_to = post_data['assigned_to']
        self.ticket.status = post_data['status']

        user_tags = UserTags.upsert(c.user, self.ticket.dump_ref())
        TagEvent.remove(self.ticket, [tag.tag for tag in user_tags.tags if tag.tag not in tags])
        TagEvent.add(self.ticket, [t for t in tags if t not in [tag.tag for tag in user_tags.tags]])

        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        if globals.custom_fields:
            for field in globals.custom_fields.split(','):
                self.ticket.custom_fields[field] = post_data[field]

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
        self.comment = model.Comment.query.get(_id=self.comment_id)

    @expose()
    def reply(self, text):
        require(has_artifact_access('comment', self.ticket))
        if self.comment_id:
            c = self.comment.reply()
            c.text = text
        else:
            c = self.ticket.reply()
            c.text = text
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


class TrackerAdminController(DefaultAdminController):

    @with_trailing_slash
    @expose('forgetracker.templates.admin')
    def index(self):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        return dict(app=self.app, globals=globals)

    @expose()
    def update_tickets(self, **post_data):
        pass

    @expose()
    def set_status_names(self, **post_data):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.status_names = post_data['status_names']
        redirect('.')

    @expose()
    def set_custom_fields(self, **post_data):
        globals = model.Globals.query.get(app_config_id=c.app.config._id)
        globals.custom_fields = post_data['custom_fields']
        redirect('.')
