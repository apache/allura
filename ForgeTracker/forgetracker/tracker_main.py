#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import logging
import re
from datetime import datetime, timedelta
from six.moves.urllib.parse import urlencode, unquote
from webob import exc
import json
import os

# Non-stdlib imports
from tg import expose, validate, redirect, flash, url, jsonify
from tg.decorators import with_trailing_slash, without_trailing_slash
from paste.deploy.converters import aslist
from tg import tmpl_context as c, app_globals as g
from tg import request, response
from formencode import validators
from bson import ObjectId
from bson.son import SON
from bson.errors import InvalidId
import feedgenerator as FG

from ming import schema
from ming.odm import session
from ming.orm.ormsession import ThreadLocalORMSession
from ming.utils import LazyProperty

# Pyforge-specific imports
from allura import model as M
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib import utils
from allura.tasks import notification_tasks
from allura.app import (
    Application,
    SitemapEntry,
    DefaultAdminController,
    AdminControllerMixin,
    ConfigOption,
)
from allura.lib.search import search_artifact, SearchError
from allura.lib.solr import escape_solr_arg
from allura.lib.decorators import require_post, memorable_forget
from allura.lib.security import (require_access, has_access, require,
                                 require_authenticated)
from allura.lib import widgets as w
from allura.lib import validators as V
from allura.lib.utils import permanent_redirect
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.plugin import ImportIdConverter
from allura.lib import exceptions as forge_exc
from allura.controllers import AppDiscussionController, AppDiscussionRestController
from allura.controllers import attachments as att
from allura.controllers import BaseController
from allura.controllers.feed import FeedArgs, FeedController
from allura.controllers.rest import AppRestControllerMixin

# Local imports
from forgetracker import model as TM
from forgetracker import version
from forgetracker import tasks

from forgetracker.widgets.admin import OptionsAdmin
from forgetracker.widgets.ticket_form import TicketForm, TicketCustomField
from forgetracker.widgets.bin_form import BinForm
from forgetracker.widgets.ticket_search import TicketSearchResults, MassEdit, MassEditForm, MassMoveForm
from forgetracker.widgets.admin_custom_fields import TrackerFieldAdmin, TrackerFieldDisplay
import six

log = logging.getLogger(__name__)

search_validators = dict(
    q=v.UnicodeString(if_empty=None),
    history=validators.StringBool(if_empty=False),
    project=validators.StringBool(if_empty=False),
    limit=validators.Int(if_invalid=None),
    page=validators.Int(if_empty=0, if_invalid=0),
    sort=v.UnicodeString(if_empty=None),
    filter=V.JsonConverter(if_empty={}, if_invalid={}),
    deleted=validators.StringBool(if_empty=False))


def _mongo_col_to_solr_col(name):
    if name == 'ticket_num':
        return 'ticket_num_i'
    elif name == 'summary':
        return 'snippet_s'
    elif name == 'votes':
        return 'votes_total_i'
    elif name == 'votes_up':
        return 'votes_up_i'
    elif name == 'votes_down':
        return 'votes_down_i'
    elif name == '_milestone':
        return '_milestone_s'
    elif name == 'status':
        return 'status_s'
    elif name == 'assigned_to_username':
        return 'assigned_to_s'
    elif name == 'custom_fields._milestone':
        return '_milestone_s'
    elif name == 'reported_by':
        return 'reported_by_s'
    elif name == 'created_date':
        return 'created_date_dt'
    elif name == 'mod_date':
        return 'mod_date_dt'
    elif name == 'labels':
        return 'labels_t'
    else:
        for field in c.app.globals.sortable_custom_fields_shown_in_search():
            if name == field['name']:
                return field['sortable_name']


def get_label(name):
    for column in mongo_columns():
        if column['name'] == name:
            return column['label']
    if name == 'assigned_to_id':
        return 'Owner'
    if name == 'private':
        return 'Private'
    if name == 'discussion_disabled':
        return 'Discussion Disabled'


def get_change_text(name, new_value, old_value):
    changes = changelog()
    if isinstance(old_value, list):
        old_value = ', '.join(old_value)
    if isinstance(new_value, list):
        new_value = ', '.join(new_value)
    changes[name] = old_value
    changes[name] = new_value
    tmpl = g.jinja2_env.get_template('forgetracker:data/ticket_changed.html')
    return tmpl.render(
        changelist=changes.get_changed(),
        comment=None)


def attachments_info(attachments):
    text = []
    for attach in attachments:
        text.append("{} ({}; {})".format(
            h.really_unicode(attach.filename),
            h.do_filesizeformat(attach.length),
            attach.content_type))
    return "\n".join(text)


def render_changes(changes, comment=None):
    """
    Render ticket changes given instanse of :class changelog:

    Returns tuple (post_text, notification_text)
    """
    tmpl = g.jinja2_env.get_template('forgetracker:data/ticket_changed.html')
    changelist = changes.get_changed()
    post_text = tmpl.render(h=h, changelist=changelist, comment=None)
    notification_text = tmpl.render(h=h, changelist=changelist, comment=comment) if comment else None
    return post_text, notification_text


def _my_trackers(user, current_tracker_app_config):
    '''Collect all 'Tickets' instances in all user's projects
    for which user has admin permissions.

    Returns list of 3-tuples (<tracker_id>, '<project>/<mount_point>', <is current tracker?>)
    '''
    trackers = []
    projects = user.my_projects_by_role_name('Admin')
    for p in projects:
        for ac in p.app_configs:
            if ac.tool_name.lower() == 'tickets':
                trac = (str(ac._id),
                        '{}/{}'.format(p.shortname, ac.options['mount_point']),
                        bool(current_tracker_app_config == ac))
                trackers.append(trac)
    return trackers


class W:
    thread = w.Thread(
        page=None, limit=None, page_size=None, count=None,
        style='linear')
    date_field = ffw.DateField()
    markdown_editor = ffw.MarkdownEdit()
    label_edit = ffw.LabelEdit()
    attachment_list = ffw.AttachmentList()
    mass_edit = MassEdit()
    mass_edit_form = MassEditForm()
    bin_form = BinForm()
    ticket_form = TicketForm()
    subscribe_form = SubscribeForm()
    auto_resize_textarea = ffw.AutoResizeTextarea()
    ticket_subscribe_form = SubscribeForm(thing='ticket')
    field_admin = TrackerFieldAdmin()
    field_display = TrackerFieldDisplay()
    ticket_custom_field = TicketCustomField
    options_admin = OptionsAdmin()
    vote_form = w.VoteForm()
    move_ticket_form = w.forms.MoveTicketForm
    mass_move_form = MassMoveForm


class ForgeTrackerApp(Application):
    __version__ = version.__version__
    permissions = ['configure', 'read', 'update', 'create', 'save_searches',
                   'unmoderated_post', 'post', 'moderate', 'admin', 'delete']
    permissions_desc = {
        'configure': 'Edit milestones.',
        'read': 'View tickets.',
        'update': 'Edit tickets.',
        'create': 'Create tickets.',
        'save_searches': 'Not used.',
        'admin': 'Set permissions. Configure options, saved searches, custom fields, '
        'and default list view columns. Move tickets to or from this '
        'tracker. Import tickets.',
        'delete': 'Delete and undelete tickets. View deleted tickets.',
    }
    config_options = Application.config_options + [
        ConfigOption('EnableVoting', bool, True),
        ConfigOption('TicketMonitoringEmail', str, ''),
        ConfigOption('TicketMonitoringType',
                     schema.OneOf('NewTicketsOnly', 'AllTicketChanges',
                                  'NewPublicTicketsOnly', 'AllPublicTicketChanges'), None),
        ConfigOption('AllowEmailPosting', bool, True)
    ]
    exportable = True
    searchable = True
    tool_label = 'Tickets'
    tool_description = """
        Organize your project's bugs, enhancements, tasks, etc. with a ticket system.
        You can track and search by status, assignee, milestone, labels, and custom fields.
    """
    default_mount_label = 'Tickets'
    default_mount_point = 'tickets'
    ordinal = 6
    icons = {
        24: 'images/tickets_24.png',
        32: 'images/tickets_32.png',
        48: 'images/tickets_48.png'
    }

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = RootController()
        self.api_root = RootRestController()
        self.admin = TrackerAdminController(self)

    @LazyProperty
    def globals(self):
        return TM.Globals.query.get(app_config_id=self.config._id)

    def has_access(self, user, topic):
        return has_access(c.app, 'post')(user=user)

    def handle_message(self, topic, message):
        log.info('Message from %s (%s)',
                 topic, self.config.options.mount_point)
        log.info('Headers are: %s', message['headers'])
        try:
            ticket = TM.Ticket.query.get(
                app_config_id=self.config._id,
                ticket_num=int(topic))
        except Exception:
            log.exception('Error getting ticket %s', topic)
            return
        if not ticket:
            log.info('No such ticket num: %s', topic)
        elif ticket.discussion_disabled:
            log.info('Discussion disabled for ticket %s', ticket.ticket_num)
        else:
            self.handle_artifact_message(ticket, message)

    def main_menu(self):
        '''Apps should provide their entries to be added to the main nav
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        '''
        return [SitemapEntry(
            self.config.options.mount_label,
            '.')]

    def sitemap_xml(self):
        """
        Used for generating sitemap.xml.
        If the root page has default content, omit it from the sitemap.xml.
        Assumes :attr:`main_menu` will return an entry pointing to the root page.
        :return: a list of :class:`SitemapEntries <allura.app.SitemapEntry>`
        """
        if self.should_noindex():
            return []
        return self.main_menu()

    @property
    @h.exceptionless([], log)
    def sitemap(self):
        menu_id = self.config.options.mount_label
        with h.push_config(c, app=self):
            return [
                SitemapEntry(menu_id, '.')[self.sidebar_menu()]]

    def should_noindex(self):
        has_ticket = TM.Ticket.query.get(app_config_id=self.config._id, deleted=False)
        return has_ticket is None

    def admin_menu(self):
        admin_url = c.project.url() + 'admin/' + \
            self.config.options.mount_point + '/'
        links = [SitemapEntry('Field Management', admin_url + 'fields'),
                 SitemapEntry('Edit Searches', admin_url + 'bins/')]
        links += super().admin_menu()
        # change Options menu html class
        for link in links:
            if link.label == 'Options':
                link.className = None
        return links

    @h.exceptionless([], log)
    def sidebar_menu(self):
        search_bins = []
        milestones = []
        for bin in self.bins:
            label = bin.shorthand_id()
            cls = '' if bin.terms and '$USER' in bin.terms else 'search_bin'
            search_bins.append(SitemapEntry(
                h.text.truncate(label, 72), bin.url(), className=cls))
        for fld in c.app.globals.milestone_fields:
            milestones.append(SitemapEntry(h.text.truncate(fld.label, 72)))
            for m in getattr(fld, "milestones", []):
                if m.complete:
                    continue
                milestones.append(
                    SitemapEntry(
                        h.text.truncate(m.name, 72),
                        self.url + fld.name[1:] + '/' +
                        h.urlquote(m.name) + '/',
                        className='milestones'))

        links = []
        if has_access(self, 'create')():
            links.append(SitemapEntry('Create Ticket',
                                      self.config.url() + 'new/', ui_icon=g.icons['add']))
        else:
            extra_attrs = {"title": "To create a new ticket, you must be authorized by the project admin."}
            links.append(SitemapEntry('Create Ticket',
                                      self.config.url() + 'new/',
                                      extra_html_attrs=extra_attrs,
                                      className='sidebar-disabled',
                                      ui_icon=g.icons['add']))
        if has_access(self, 'configure')():
            links.append(SitemapEntry('Edit Milestones', self.config.url()
                         + 'milestones', ui_icon=g.icons['table']))
            links.append(SitemapEntry('Edit Searches', c.project.url() + 'admin/' +
                         c.app.config.options.mount_point + '/bins/', ui_icon=g.icons['search']))
        links.append(SitemapEntry('View Stats', self.config.url()
                     + 'stats/', ui_icon=g.icons['stats']))
        discussion = c.app.config.discussion
        pending_mod_count = M.Post.query.find({
            'discussion_id': discussion._id,
            'status': 'pending',
            'deleted': False,
        }).count()
        if pending_mod_count and has_access(discussion, 'moderate')():
            links.append(
                SitemapEntry(
                    'Moderate', discussion.url() + 'moderate', ui_icon=g.icons['moderate'],
                    small=pending_mod_count))

        links += milestones

        if len(search_bins):
            links.append(SitemapEntry('Searches'))
            links = links + search_bins
        links.append(SitemapEntry('Help'))
        links.append(
            SitemapEntry('Formatting Help', '/nf/markdown_syntax', extra_html_attrs={'target': '_blank'}))
        return links

    def sidebar_menu_js(self):
        return """\
        $(function() {
            $.ajax({
                url:'%(app_url)sbin_counts',
                success: function(data) {
                    var $spans = $('.search_bin > span');
                    $.each(data.bin_counts, function(i, item) {
                        $spans.each(function() {
                            if ($(this).text() === item.label) {
                                $(this).after('<small>' + item.count + '</small>').fadeIn('fast');
                            }
                        });
                    });
                }
            });
            if ($('.milestones').length > 0) {
                $.ajax({
                    url: '%(app_url)smilestone_counts',
                    success: function(data) {
                        var $spans = $('.milestones > span');
                        $.each(data.milestone_counts, function(i, item) {
                            $spans.each(function() {
                                if ($(this).text() === item.name) {
                                    $(this).after('<small>' + item.count + '</small>').fadeIn('fast');
                                }
                            });
                        });
                    }
                });
            }
        });""" % {'app_url': c.app.url}

    def has_custom_field(self, field):
        """Checks if given custom field is defined.
        (Custom field names must start with '_'.)
        """
        for f in self.globals.custom_fields:
            if f['name'] == field:
                return True
        return False

    def install(self, project):
        'Set up any default permissions and roles here'
        super().install(project)
        # Setup permissions
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_developer = M.ProjectRole.by_name('Developer')._id
        role_auth = M.ProjectRole.by_name('*authenticated')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_auth, 'post'),
            M.ACE.allow(role_auth, 'unmoderated_post'),
            M.ACE.allow(role_auth, 'create'),
            M.ACE.allow(role_developer, 'update'),
            M.ACE.allow(role_developer, 'moderate'),
            M.ACE.allow(role_developer, 'save_searches'),
            M.ACE.allow(role_developer, 'delete'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin'),
        ]
        self.globals = TM.Globals(app_config_id=c.app.config._id,
                                  last_ticket_num=0,
                                  open_status_names=self.config.options.pop(
                                      'open_status_names', 'open unread accepted pending'),
                                  closed_status_names=self.config.options.pop(
                                      'closed_status_names', 'closed wont-fix'),
                                  custom_fields=[dict(
                                      name='_milestone',
                                      label='Milestone',
                                      type='milestone',
                                      milestones=[
                                          dict(name='1.0', complete=False,
                                               due_date=None, default=True),
                                          dict(name='2.0', complete=False, due_date=None, default=False)])])
        self.globals.update_bin_counts()
        # create default search bins
        TM.Bin(summary='Open Tickets', terms=self.globals.not_closed_query,
               app_config_id=self.config._id, custom_fields=dict())
        TM.Bin(summary='Closed Tickets', terms=self.globals.closed_query,
               app_config_id=self.config._id, custom_fields=dict())
        TM.Bin(summary='Changes', terms=self.globals.not_closed_query,
               sort='mod_date_dt desc', app_config_id=self.config._id,
               custom_fields=dict())

    def uninstall(self, project):
        """Remove all the tool's artifacts from the database"""
        app_config_id = {'app_config_id': c.app.config._id}
        TM.TicketAttachment.query.remove(app_config_id)
        TM.Ticket.query.remove(app_config_id)
        TM.Bin.query.remove(app_config_id)
        TM.Globals.query.remove(app_config_id)
        super().uninstall(project)

    def bulk_export(self, f, export_path='', with_attachments=False):
        f.write('{"tickets": [')
        tickets = list(TM.Ticket.query.find(dict(
            app_config_id=self.config._id,
            # backwards compat for old tickets that don't have it set
            deleted={'$ne': True},
        )))
        if with_attachments:
            GenericClass = utils.JSONForExport
            self.export_attachments(tickets, export_path)
        else:
            GenericClass = jsonify.JSONEncoder

        for i, ticket in enumerate(tickets):
            if i > 0:
                f.write(',')
            json.dump(ticket, f, cls=GenericClass, indent=2)
        f.write('],\n"tracker_config":')
        json.dump(self.config, f, cls=GenericClass, indent=2)
        f.write(',\n"milestones":')
        milestones = self.milestones
        json.dump(milestones, f, cls=GenericClass, indent=2)
        f.write(',\n"custom_fields":')
        json.dump(self.globals.custom_fields, f,
                  cls=GenericClass, indent=2)
        f.write(',\n"open_status_names":')
        json.dump(self.globals.open_status_names, f,
                  cls=GenericClass, indent=2)
        f.write(',\n"closed_status_names":')
        json.dump(self.globals.closed_status_names, f,
                  cls=GenericClass, indent=2)
        f.write(',\n"saved_bins":')
        bins = self.bins
        json.dump(bins, f, cls=GenericClass, indent=2)
        f.write('}')

    def export_attachments(self, tickets, export_path):
        for ticket in tickets:
            attachment_path = self.get_attachment_export_path(export_path, str(ticket._id))
            self.save_attachments(attachment_path, ticket.attachments)

            for post in ticket.discussion_thread.query_posts(status='ok'):
                post_path = os.path.join(
                    attachment_path,
                    ticket.discussion_thread._id,
                    post.slug
                )
                self.save_attachments(post_path, post.attachments)

    @property
    def bins(self):
        return TM.Bin.query.find(dict(app_config_id=self.config._id)).sort('summary').all()

    @property
    def milestones(self):
        milestones = []
        for fld in self.globals.milestone_fields:
            if fld.name == '_milestone':
                for m in fld.milestones:
                    d = self.globals.milestone_count(
                        f'{fld.name}:{m.name}')
                    milestones.append(dict(
                        name=m.name,
                        due_date=m.get('due_date'),
                        description=m.get('description'),
                        complete=m.get('complete'),
                        default=m.get('default'),
                        total=d['hits'],
                        closed=d['closed']))
        return milestones


def mongo_columns():
    columns = [dict(name='ticket_num',
                    sort_name='ticket_num',
                    label='Ticket Number',
                    active=c.app.globals.show_in_search['ticket_num']),
               dict(name='summary',
                    sort_name='summary',
                    label='Summary',
                    active=c.app.globals.show_in_search['summary']),
               dict(name='_milestone',
                    sort_name='custom_fields._milestone',
                    label='Milestone',
                    active=c.app.globals.show_in_search['_milestone']),
               dict(name='status',
                    sort_name='status',
                    label='Status',
                    active=c.app.globals.show_in_search['status']),
               dict(name='assigned_to',
                    sort_name='assigned_to_username',
                    label='Owner',
                    active=c.app.globals.show_in_search['assigned_to']),
               dict(name='reported_by',
                    sort_name='reported_by',
                    label='Creator',
                    active=c.app.globals.show_in_search['reported_by']),
               dict(name='created_date',
                    sort_name='created_date',
                    label='Created',
                    active=c.app.globals.show_in_search['created_date']),
               dict(name='mod_date',
                    sort_name='mod_date',
                    label='Updated',
                    active=c.app.globals.show_in_search['mod_date']),
               dict(name='labels',
                    sort_name='labels',
                    label='Labels',
                    active=c.app.globals.show_in_search['labels']),
               ]
    for field in c.app.globals.sortable_custom_fields_shown_in_search():
        columns.append(
            dict(name=field['name'], sort_name=field['name'], label=field['label'], active=True))
    if c.app.config.options.get('EnableVoting'):
        columns.append(
            dict(name='votes', sort_name='votes', label='Votes', active=True))
    return columns


def solr_columns():
    columns = [dict(name='ticket_num',
                    sort_name='ticket_num_i',
                    label='Ticket Number',
                    active=c.app.globals.show_in_search['ticket_num']),
               dict(name='summary',
                    sort_name='snippet_s',
                    label='Summary',
                    active=c.app.globals.show_in_search['summary']),
               dict(name='_milestone',
                    sort_name='_milestone_s',
                    label='Milestone',
                    active=c.app.globals.show_in_search['_milestone']),
               dict(name='status',
                    sort_name='status_s',
                    label='Status',
                    active=c.app.globals.show_in_search['status']),
               dict(name='assigned_to',
                    sort_name='assigned_to_s',
                    label='Owner',
                    active=c.app.globals.show_in_search['assigned_to']),
               dict(name='reported_by',
                    sort_name='reported_by_s',
                    label='Creator',
                    active=c.app.globals.show_in_search['reported_by']),
               dict(name='created_date',
                    sort_name='created_date_dt',
                    label='Created',
                    active=c.app.globals.show_in_search['created_date']),
               dict(name='mod_date',
                    sort_name='mod_date_dt',
                    label='Updated',
                    active=c.app.globals.show_in_search['mod_date']),
               dict(name='labels',
                    sort_name='labels_t',
                    label='Labels',
                    active=c.app.globals.show_in_search['labels']),
               ]
    for field in c.app.globals.sortable_custom_fields_shown_in_search():
        columns.append(
            dict(name=field['name'], sort_name=field['sortable_name'], label=field['label'], active=True))
    if c.app.config.options.get('EnableVoting'):
        columns.append(
            dict(name='votes', sort_name='votes_total_i', label='Votes', active=True))
    return columns


class RootController(BaseController, FeedController):

    def __init__(self):
        setattr(self, 'search_feed.atom', self.search_feed)
        setattr(self, 'search_feed.rss', self.search_feed)
        self._discuss = AppDiscussionController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def bin_counts(self, *args, **kw):
        bin_counts = []
        for bin in c.app.bins:
            bin_id = bin.shorthand_id()
            label = h.text.truncate(bin_id, 72)
            count = 0
            try:
                count = c.app.globals.bin_count(bin_id)['hits']
            except ValueError:
                log.info('Ticket bin %s search failed for project %s' %
                         (label, c.project.shortname))
            bin_counts.append(dict(label=label, count=count))
        return dict(bin_counts=bin_counts)

    @expose('json:')
    def milestone_counts(self, *args, **kw):
        milestone_counts = []
        for fld in c.app.globals.milestone_fields:
            for m in getattr(fld, "milestones", []):
                if m.complete:
                    continue
                count = c.app.globals.milestone_count(
                    f'{fld.name}:{m.name}')['hits']
                name = h.text.truncate(m.name, 72)
                milestone_counts.append({'name': name, 'count': count})
        return {'milestone_counts': milestone_counts}

    @expose('json:')
    def tags(self, term=None, **kw):
        if not term:
            return json.dumps([])
        db = M.session.project_doc_session.db
        tickets = db[TM.Ticket.__mongometa__.name]
        tags = tickets.aggregate([
            {
                '$match': {
                    'app_config_id': c.app.config._id,
                    'labels': {
                        '$exists': True,
                        '$ne': [],
                    }
                }
            },
            {'$project': {'labels': 1}},
            {'$unwind': '$labels'},
            {'$match': {'labels': {'$regex': '^%s' % term, '$options': 'i'}}},
            {'$group': {'_id': '$labels', 'count': {'$sum': 1}}},
            {'$sort': SON([('count', -1), ('_id', 1)])}
        ], cursor={})
        return json.dumps([tag['_id'] for tag in tags])

    @with_trailing_slash
    @h.vardec
    @expose('jinja:forgetracker:templates/tracker/index.html')
    @validate(dict(deleted=validators.StringBool(if_empty=False),
                   filter=V.JsonConverter(if_empty={})))
    def index(self, limit=None, columns=None, page=0, sort='ticket_num desc', deleted=False, filter=None, **kw):
        show_deleted = [False]
        if deleted and has_access(c.app, 'delete'):
            show_deleted = [False, True]
        elif deleted and not has_access(c.app, 'delete'):
            deleted = False

        # it's just our original query mangled and sent back to us
        kw.pop('q', None)
        result = TM.Ticket.paged_query_or_search(c.app.config, c.user,
                                                 c.app.globals.not_closed_mongo_query,
                                                 c.app.globals.not_closed_query,
                                                 filter,
                                                 sort=sort, limit=limit, page=page,
                                                 deleted={'$in': show_deleted},
                                                 show_deleted=deleted, **kw)

        result['columns'] = columns or mongo_columns()
        result[
            'sortable_custom_fields'] = c.app.globals.sortable_custom_fields_shown_in_search()
        result['subscribed'] = M.Mailbox.subscribed()
        result['allow_edit'] = has_access(c.app, 'update')()
        result['allow_move'] = has_access(c.app, 'admin')()
        result['help_msg'] = c.app.config.options.get(
            'TicketHelpSearch', '').strip()
        result['url_q'] = c.app.globals.not_closed_query
        result['deleted'] = deleted
        c.subscribe_form = W.subscribe_form
        c.ticket_search_results = TicketSearchResults(result['filter_choices'])
        return result

    @without_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/milestones.html')
    def milestones(self, **kw):
        require_access(c.app, 'configure')
        c.date_field = W.date_field
        milestones = c.app.milestones
        return dict(milestones=milestones)

    @without_trailing_slash
    @h.vardec
    @expose()
    @require_post()
    def update_milestones(self, field_name=None, milestones=None, **kw):
        require_access(c.app, 'configure')
        update_counts = False
        # If the default milestone field doesn't exist, create it.
        # TODO: This is a temporary fix for migrated projects, until we make
        # the Edit Milestones page capable of editing any/all milestone fields
        # instead of just the default "_milestone" field.
        if field_name == '_milestone' and \
                field_name not in [m.name for m in c.app.globals.milestone_fields]:
            c.app.globals.custom_fields.append(dict(name='_milestone',
                                                    label='Milestone', type='milestone', milestones=[]))
        for fld in c.app.globals.milestone_fields:
            if fld.name == field_name:
                for new in milestones:
                    exists_milestones = [m.name for m in fld.milestones]
                    new['new_name'] = new['new_name'].replace("/", "-")
                    if (new['new_name'] in exists_milestones) and (new['new_name'] != new['old_name']):
                        flash('The milestone "%s" already exists.' %
                              new['new_name'], 'error')
                        redirect('milestones')
                    for m in fld.milestones:
                        if m.name == new['old_name']:
                            if new['new_name'] == '':
                                flash('You must name the milestone.', 'error')
                            else:
                                m.name = new['new_name']
                                m.description = new['description']
                                m.due_date = new['due_date']
                                m.complete = new['complete'] == 'Closed'
                                m.default = new.get('default', False)
                                if new['old_name'] != m.name:
                                    q = '{}:"{}"'.format(fld.name, new['old_name'])
                                    # search_artifact() limits results to 10
                                    # rows by default, so give it a high upper
                                    # bound to make sure we get all tickets
                                    # for this milestone
                                    r = search_artifact(
                                        TM.Ticket, q, rows=10000, short_timeout=False)
                                    ticket_numbers = [match['ticket_num_i']
                                                      for match in r.docs]
                                    tickets = TM.Ticket.query.find(dict(
                                        app_config_id=c.app.config._id,
                                        ticket_num={'$in': ticket_numbers})).all()
                                    for t in tickets:
                                        t.custom_fields[field_name] = m.name
                                    update_counts = True
                    if new['old_name'] == '' and new['new_name'] != '':
                        fld.milestones.append(dict(
                            name=new['new_name'],
                            description=new['description'],
                            due_date=new['due_date'],
                            complete=new['complete'] == 'Closed',
                            default=new.get('default', False),
                        ))
                        update_counts = True
        if update_counts:
            c.app.globals.invalidate_bin_counts()
        redirect('milestones')

    @with_trailing_slash
    @h.vardec
    @expose('jinja:forgetracker:templates/tracker/search.html')
    @validate(validators=search_validators)
    def search(self, q=None, query=None, project=None, columns=None, page=0, sort=None,
               deleted=False, filter=None, **kw):
        require(has_access(c.app, 'read'))

        if deleted and not has_access(c.app, 'delete'):
            deleted = False
        if query and not q:
            q = query
        c.bin_form = W.bin_form
        bin = None
        if q:
            bin = TM.Bin.query.find(
                dict(app_config_id=c.app.config._id, terms=q)).first()
        if project:
            redirect(c.project.url() + 'search?' + urlencode(dict(q=q, history=kw.get('history'))))
        result = TM.Ticket.paged_search(c.app.config, c.user, q, page=page, sort=sort,
                                        show_deleted=deleted, filter=filter, **kw)
        result['columns'] = columns or solr_columns()
        result[
            'sortable_custom_fields'] = c.app.globals.sortable_custom_fields_shown_in_search()
        result['allow_edit'] = has_access(c.app, 'update')()
        result['allow_move'] = has_access(c.app, 'admin')()
        result['bin'] = bin
        result['help_msg'] = c.app.config.options.get(
            'TicketHelpSearch', '').strip()
        result['deleted'] = deleted
        c.ticket_search_results = TicketSearchResults(result['filter_choices'])
        return result

    @with_trailing_slash
    @h.vardec
    @expose()
    @validate(validators=search_validators)
    def search_feed(self, q=None, query=None, project=None, page=0, sort=None, deleted=False, **kw):
        if query and not q:
            q = query
        result = TM.Ticket.paged_search(
            c.app.config, c.user, q, page=page, sort=sort, show_deleted=deleted, **kw)
        response.headers['Content-Type'] = ''
        response.content_type = 'application/xml'
        d = dict(title='Ticket search results', link=h.absurl(c.app.url),
                 description='You searched for %s' % q, language='en')
        if request.environ['PATH_INFO'].endswith('.atom'):
            feed = FG.Atom1Feed(**d)
        else:
            feed = FG.Rss201rev2Feed(**d)
        for t in result['tickets']:
            url = h.absurl(t.url())
            feed_kwargs = dict(title=t.summary,
                               link=url,
                               pubdate=t.mod_date,
                               description=t.description,
                               unique_id=url,
                               )
            if t.reported_by:
                feed_kwargs['author_name'] = t.reported_by.display_name
                feed_kwargs['author_link'] = h.absurl(t.reported_by.url())
            feed.add_item(**feed_kwargs)
        return feed.writeString('utf-8')

    @expose()
    def _lookup(self, ticket_num, *remainder):
        if ticket_num.isdigit():
            return TicketController(ticket_num), remainder
        elif remainder:
            return MilestoneController(self, ticket_num, remainder[0]), remainder[1:]
        else:
            raise exc.HTTPNotFound

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/search_help.html')
    def search_help(self, **kw):
        'Static page with search help'
        return dict(
            custom_fields=[fld for fld in (c.app.globals.custom_fields or []) if fld.name != '_milestone'],
        )

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/new_ticket.html')
    def new(self, **kw):
        require_access(c.app, 'create')
        self.rate_limit(TM.Ticket, 'Ticket creation', redir='..')
        c.ticket_form = W.ticket_form
        help_msg = c.app.config.options.get('TicketHelpNew', '').strip()
        return dict(action=c.app.config.url() + 'save_ticket',
                    help_msg=help_msg,
                    url_params=kw,
                    subscribed_to_tool=M.Mailbox.subscribed(),
                    )

    @expose()
    def markdown_syntax(self, **kw):
        permanent_redirect('/nf/markdown_syntax')

    @memorable_forget()
    @expose()
    @h.vardec
    @require_post()
    @validate(W.ticket_form, error_handler=new)
    def save_ticket(self, ticket_form=None, **post_data):
        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        ticket_num = ticket_form.pop('ticket_num', None)
        # W.ticket_form gives us this, but we don't set any comment during
        # ticket creation
        ticket_form.pop('comment', None)
        if ticket_num:
            ticket = TM.Ticket.query.get(
                app_config_id=c.app.config._id,
                ticket_num=ticket_num)
            if not ticket:
                raise Exception('Ticket number not found.')
            require_access(ticket, 'update')
            ticket.update_fields_basics(ticket_form)
        else:
            require_access(c.app, 'create')
            self.rate_limit(TM.Ticket, 'Ticket creation', redir='.')
            ticket = TM.Ticket.new(form_fields=ticket_form)
        ticket.update_fields_finish(ticket_form)
        g.spam_checker.check(ticket_form['summary'] + '\n' + ticket_form.get('description', ''), artifact=ticket,
                             user=c.user, content_type='ticket')
        c.app.globals.invalidate_bin_counts()
        notification_tasks.send_usermentions_notification.post(ticket.index_id(), ticket_form.get('description', ''))
        g.director.create_activity(c.user, 'created', ticket,
                                   related_nodes=[c.project], tags=['ticket'])
        redirect(str(ticket.ticket_num) + '/')

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/mass_edit.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   filter=V.JsonConverter(if_empty={}),
                   limit=validators.Int(if_empty=10, if_invalid=10),
                   page=validators.Int(if_empty=0, if_invalid=0),
                   sort=v.UnicodeString(if_empty='ticket_num_i asc')))
    def edit(self, q=None, limit=None, page=None, sort=None, filter=None, **kw):
        require_access(c.app, 'update')
        result = TM.Ticket.paged_search(c.app.config, c.user, q, filter=filter,
                                        sort=sort, limit=limit, page=page,
                                        show_deleted=False, **kw)

        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        result['columns'] = solr_columns()
        result[
            'sortable_custom_fields'] = c.app.globals.sortable_custom_fields_shown_in_search()
        result['globals'] = c.app.globals
        result['cancel_href'] = url(
            c.app.url + 'search/',
            dict(q=q, limit=limit, sort=sort))
        c.user_select = ffw.ProjectUserCombo()
        c.label_edit = ffw.LabelEdit()
        c.mass_edit = W.mass_edit
        c.mass_edit_form = W.mass_edit_form
        return result

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/mass_move.html')
    @validate(dict(q=v.UnicodeString(if_empty=None),
                   filter=V.JsonConverter(if_empty={}),
                   limit=validators.Int(if_empty=10, if_invalid=10),
                   page=validators.Int(if_empty=0, if_invalid=0),
                   sort=v.UnicodeString(if_empty='ticket_num_i asc')))
    def move(self, q=None, limit=None, page=None, sort=None, filter=None, **kw):
        require_access(c.app, 'admin')
        result = TM.Ticket.paged_search(c.app.config, c.user, q, filter=filter,
                                        sort=sort, limit=limit, page=page,
                                        show_deleted=False, **kw)

        result['columns'] = solr_columns()
        result[
            'sortable_custom_fields'] = c.app.globals.sortable_custom_fields_shown_in_search()
        result['globals'] = c.app.globals
        result['cancel_href'] = url(
            c.app.url + 'search/', dict(q=q, limit=limit, sort=sort))
        c.mass_move = W.mass_edit
        trackers = _my_trackers(c.user, c.app.config)
        c.mass_move_form = W.mass_move_form(
            trackers=trackers,
            action=c.app.url + 'move_tickets')
        return result

    @expose()
    @require_post()
    def move_tickets(self, **post_data):
        require_access(c.app, 'admin')
        ticket_ids = aslist(post_data.get('__ticket_ids', []))
        search = post_data.get('__search', '')
        try:
            destination_tracker_id = ObjectId(post_data.get('tracker', ''))
        except InvalidId:
            destination_tracker_id = None
        tracker = M.AppConfig.query.get(_id=destination_tracker_id)
        if tracker is None:
            flash('Select valid tracker', 'error')
            redirect('move/' + search)
        if tracker == c.app.config:
            flash('Ticket already in a selected tracker', 'info')
            redirect('move/' + search)
        if not has_access(tracker, 'admin')():
            flash('You should have admin access to destination tracker',
                  'error')
            redirect('move/' + search)
        tickets = TM.Ticket.query.find(dict(
            _id={'$in': [ObjectId(id) for id in ticket_ids]},
            app_config_id=c.app.config._id)).all()

        tasks.move_tickets.post(ticket_ids, destination_tracker_id)

        c.app.globals.invalidate_bin_counts()
        ThreadLocalORMSession.flush_all()
        count = len(tickets)
        flash('Move scheduled ({} ticket{})'.format(
            count, 's' if count != 1 else ''), 'ok')
        redirect('move/' + search)

    @expose()
    @require_post()
    def update_tickets(self, **post_data):
        tickets = TM.Ticket.query.find(dict(
            _id={'$in': [ObjectId(id)
                         for id in aslist(
                             post_data['__ticket_ids'])]},
            app_config_id=c.app.config._id)).all()
        for ticket in tickets:
            require_access(ticket, 'update')
        tasks.bulk_edit.post(**post_data)
        count = len(tickets)
        flash('Update scheduled ({} ticket{})'.format(
            count, 's' if count != 1 else ''), 'ok')
        redirect('edit/' + post_data['__search'])

    def tickets_since(self, when=None):
        count = 0
        if when:
            count = TM.Ticket.query.find(dict(app_config_id=c.app.config._id,
                                              created_date={'$gte': when})).count()
        else:
            count = TM.Ticket.query.find(
                dict(app_config_id=c.app.config._id)).count()
        return count

    def ticket_comments_since(self, when=None):
        q = dict(
            discussion_id=c.app.config.discussion_id,
            status='ok',
            deleted=False,
        )
        if when is not None:
            q['timestamp'] = {'$gte': when}
        return M.Post.query.find(q).count()

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/stats.html')
    def stats(self, dates=None, **kw):
        globals = c.app.globals
        total = TM.Ticket.query.find(
            dict(app_config_id=c.app.config._id, deleted=False)).count()
        open = TM.Ticket.query.find(dict(app_config_id=c.app.config._id, deleted=False, status={
                                    '$in': list(globals.set_of_open_status_names)})).count()
        closed = TM.Ticket.query.find(dict(app_config_id=c.app.config._id, deleted=False, status={
                                      '$in': list(globals.set_of_closed_status_names)})).count()
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
        comments = self.ticket_comments_since()
        week_comments = self.ticket_comments_since(week_ago)
        fortnight_comments = self.ticket_comments_since(fortnight_ago)
        month_comments = self.ticket_comments_since(month_ago)
        c.user_select = ffw.ProjectUserCombo()
        if dates is None:
            today = datetime.utcnow()
            dates = "{} to {}".format((today - timedelta(days=61))
                                  .strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
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
            globals=globals,
            dates=dates,
        )

    @expose('json:')
    @require_post()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None, **kw):
        if subscribe:
            M.Mailbox.subscribe(type='direct')
        elif unsubscribe:
            M.Mailbox.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(),
        }


class BinController(BaseController, AdminControllerMixin):

    def __init__(self, summary=None, app=None):
        if summary is not None:
            self.summary = summary
        if app is not None:
            self.app = app

    def _check_security(self):
        require_access(self.app, 'save_searches')

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/bin.html')
    def index(self, **kw):
        count = len(self.app.bins)
        return dict(bins=self.app.bins, count=count, app=self.app)

    @with_trailing_slash
    @h.vardec
    @expose('jinja:forgetracker:templates/tracker/bin.html')
    @require_post()
    @validate(W.bin_form, error_handler=index)
    def save_bin(self, **bin_form):
        """Update existing search bin or create a new one.

        If the search terms are valid, save the search and redirect to the
        search bin list page.

        If the search terms are invalid (throw an error), do not save the
        search. Instead, render the search bin edit page and display the error
        so the user can fix.
        """
        # New search bin that the user is attempting to create
        new_bin = None
        bin = bin_form['_id']
        if bin is None:
            bin = TM.Bin(app_config_id=self.app.config._id, summary='')
            new_bin = bin
        require(lambda: bin.app_config_id == self.app.config._id)
        bin.summary = bin_form['summary']
        bin.terms = bin_form['terms']
        try:
            # Test the search by running it
            with h.push_config(c, app=self.app):
                search_artifact(TM.Ticket, bin.terms,
                                rows=0, short_timeout=True)
        except SearchError as e:
            # Search threw an error.
            # Save the error on the bin object for displaying
            # in the template.
            bin.error = str(e)
            # Expunge the bin object so we don't save the
            # errant search terms to mongo.
            M.session.artifact_orm_session.expunge(bin)
            # Render edit page with error messages
            return dict(bins=self.app.bins, count=len(self.app.bins),
                        app=self.app, new_bin=new_bin, errors=True)
        self.app.globals.invalidate_bin_counts()
        redirect('.')

    @without_trailing_slash
    @h.vardec
    @expose('jinja:forgetracker:templates/tracker/bin.html')
    @require_post()
    def update_bins(self, field_name=None, bins=None, **kw):
        """Update saved search bins.

        If all the updated searches are valid solr searches, save them and
        redirect to the search bin list page.

        If any of the updated searches are invalid (throw an error), do not
        save the offending search(es). Instead, render the search bin edit
        page and display the error(s) so the user can fix.
        """
        require_access(self.app, 'save_searches')
        # Have any of the updated searches thrown an error?
        errors = False
        # Persistent search bins - will need this if we encounter errors
        # and need to re-render the edit page
        saved_bins = []
        # New search bin that the user is attempting to create
        new_bin = None
        for bin_form in bins:
            bin = None
            if bin_form['id']:
                # An existing bin that might be getting updated
                bin = TM.Bin.query.find(dict(
                    app_config_id=self.app.config._id,
                    _id=ObjectId(bin_form['id']))).first()
                saved_bins.append(bin)
            elif bin_form['summary'] and bin_form['terms']:
                # A brand new search bin being created
                bin = TM.Bin(app_config_id=self.app.config._id, summary='')
                new_bin = bin
            if bin:
                if bin_form['delete'] == 'True':
                    # Search bin is being deleted; delete from mongo and
                    # remove from our list of saved search bins.
                    bin.delete()
                    saved_bins.remove(bin)
                else:
                    # Update bin.summary with the posted value.
                    bin.summary = bin_form['summary']
                    if bin.terms != bin_form['terms']:
                        # If the bin terms are being updated, test the search.
                        bin.terms = bin_form['terms']
                        try:
                            with h.push_config(c, app=self.app):
                                search_artifact(
                                    TM.Ticket, bin.terms, rows=0, short_timeout=True)
                        except SearchError as e:
                            # Search threw an error.
                            # Save the error on the bin object for displaying
                            # in the template.
                            bin.error = str(e)
                            errors = True
                            # Expunge the bin object so we don't save the
                            # errant search terms to mongo.
                            M.session.artifact_orm_session.expunge(bin)
                        else:
                            # Search was good (no errors)
                            if bin is new_bin:
                                # If this was a new bin, it'll get flushed to
                                # mongo, meaning it'll no longer be a new bin
                                # - add to saved_bins and reset new_bin.
                                saved_bins.append(bin)
                                new_bin = None
        if errors:
            # There were errors in some of the search terms. Render the edit
            # page so the user can fix the errors.
            return dict(bins=saved_bins, count=len(bins), app=self.app,
                        new_bin=new_bin, errors=errors)
        self.app.globals.invalidate_bin_counts()
        # No errors, redirect to search bin list page.
        redirect('.')


class changelog:

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
        self.keys = []  # to track insertion order
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


class TicketController(BaseController, FeedController):

    def __init__(self, ticket_num=None):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = TM.Ticket.query.get(app_config_id=c.app.config._id,
                                              ticket_num=self.ticket_num)
            if self.ticket is None:
                self.ticket = TM.Ticket.query.get(
                    app_config_id=c.app.config._id,
                    import_id=ImportIdConverter.get().expand(
                        ticket_num, c.app),
                )
                if self.ticket is not None:
                    utils.permanent_redirect(self.ticket.url())
                else:
                    # check if ticket was moved
                    moved_ticket = TM.MovedTicket.query.find({
                        'app_config_id': c.app.config._id,
                        'ticket_num': self.ticket_num,
                    }).first()
                    if moved_ticket:
                        flash('Original ticket was moved to this location')
                        utils.permanent_redirect(moved_ticket.moved_to_url)
            self.attachment = AttachmentsController(self.ticket)

    def _check_security(self):
        if self.ticket is not None:
            require_access(self.ticket, 'read')

    @with_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/ticket.html')
    @validate(dict(
        page=validators.Int(if_empty=0, if_invalid=0),
        limit=validators.Int(if_empty=None, if_invalid=None)))
    def index(self, page=0, limit=None, deleted=False, **kw):
        ticket_visible = self.ticket and not self.ticket.deleted
        if ticket_visible or has_access(self.ticket, 'delete'):
            c.ticket_form = W.ticket_form
            c.thread = W.thread
            c.attachment_list = W.attachment_list
            c.subscribe_form = W.ticket_subscribe_form
            c.ticket_custom_field = W.ticket_custom_field
            c.vote_form = W.vote_form
            tool_subscribed = M.Mailbox.subscribed()
            if tool_subscribed:
                subscribed = False
            else:
                subscribed = M.Mailbox.subscribed(artifact=self.ticket)
            post_count = self.ticket.discussion_thread.post_count
            limit, page, _ = g.handle_paging(limit, page)
            limit, page = h.paging_sanitizer(limit, page, post_count)
            voting_enabled = self.ticket.app.config.options.get('EnableVoting')
            return dict(ticket=self.ticket, globals=c.app.globals,
                        allow_edit=has_access(self.ticket, 'update')(),
                        subscribed=subscribed, voting_enabled=voting_enabled,
                        page=page, limit=limit, count=post_count)
        else:
            raise exc.HTTPNotFound('Ticket #%s does not exist.' % self.ticket_num)

    def get_feed(self, project, app, user):
        """Return a :class:`allura.controllers.feed.FeedArgs` object describing
        the xml feed for this controller.

        Overrides :meth:`allura.controllers.feed.FeedController.get_feed`.

        """
        title = 'Recent changes to %d: %s' % (
            self.ticket.ticket_num, self.ticket.summary)
        return FeedArgs(
            {'ref_id': self.ticket.index_id()},
            title,
            self.ticket.url())

    @expose()
    @require_post()
    @h.vardec
    def update_ticket(self, **post_data):
        if not post_data.get('summary'):
            flash('You must provide a Name', 'error')
            redirect('.')
        if 'labels' in post_data:
            post_data['labels'] = post_data['labels'].split(',')
        else:
            post_data['labels'] = []
        self._update_ticket(post_data)

    @memorable_forget()
    @expose()
    @require_post()
    @h.vardec
    @validate(W.ticket_form, error_handler=index)
    def update_ticket_from_widget(self, **post_data):
        data = post_data['ticket_form']
        # icky: handle custom fields like the non-widget form does
        if 'custom_fields' in data:
            for k in data['custom_fields']:
                data['custom_fields.' + k] = data['custom_fields'][k]
        self._update_ticket(data)

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def delete(self, **kw):
        self.ticket.soft_delete()
        flash('Ticket successfully deleted')
        return dict(location='../' + str(self.ticket.ticket_num))

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def undelete(self, **kw):
        require_access(self.ticket, 'delete')
        self.ticket.deleted = False
        self.ticket.summary = re.sub(r' \d+:\d+:\d+ \d+-\d+-\d+$', '', self.ticket.summary)
        M.Shortlink.from_artifact(self.ticket)
        flash('Ticket successfully restored')
        c.app.globals.invalidate_bin_counts()
        return dict(location='../' + str(self.ticket.ticket_num))

    @require_post()
    def _update_ticket(self, post_data):
        require_access(self.ticket, 'update')
        old_text = self.ticket.description
        new_text = post_data.get('description', '')
        g.spam_checker.check(post_data.get('summary', '') + '\n' + post_data.get('description', ''),
                             artifact=self.ticket, user=c.user, content_type='ticket')
        changes = changelog()
        comment = post_data.pop('comment', None)
        labels = post_data.pop('labels', None) or []
        changes['labels'] = self.ticket.labels
        self.ticket.labels = labels
        changes['labels'] = self.ticket.labels
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

        # Register a key with the changelog -->
        # Update the ticket property from the post_data -->
        # Set the value of the changelog key again in case it has changed.
        changes['private'] = 'Yes' if self.ticket.private else 'No'
        self.ticket.private = post_data.get('private', False)
        changes['private'] = 'Yes' if self.ticket.private else 'No'

        changes['discussion'] = 'disabled' if self.ticket.discussion_disabled else 'enabled'
        self.ticket.discussion_disabled = post_data.get('discussion_disabled', False)
        changes['discussion'] = 'disabled' if self.ticket.discussion_disabled else 'enabled'

        if 'attachment' in post_data:
            attachment = post_data['attachment']
            changes['attachments'] = attachments_info(self.ticket.attachments)
            self.ticket.add_multiple_attachments(attachment)
            # flush new attachments to db
            session(self.ticket.attachment_class()).flush()
            # self.ticket.attachments is ming's LazyProperty, we need to reset
            # it's cache to fetch updated attachments here:
            self.ticket.__dict__.pop('attachments')
            changes['attachments'] = attachments_info(self.ticket.attachments)
        for cf in c.app.globals.custom_fields or []:
            if 'custom_fields.' + cf.name in post_data:
                value = post_data['custom_fields.' + cf.name]
                if cf.type == 'user':
                    # restrict custom user field values to project members
                    user = c.project.user_in_project(value)
                    value = user.username \
                        if user and user != M.User.anonymous() else ''
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
                def cf_val(cf):
                    return self.ticket.get_custom_user(cf.name) \
                        if cf.type == 'user' \
                        else self.ticket.custom_fields.get(cf.name)
                changes[cf.label] = cf_val(cf)
                self.ticket.custom_fields[cf.name] = value
                changes[cf.label] = cf_val(cf)

        post_text, notification_text = render_changes(changes, comment)

        thread = self.ticket.discussion_thread
        if changes.get_changed() or post_text or notification_text:
            thread.add_post(text=post_text, is_meta=True,
                            notification_text=notification_text)
        self.ticket.commit()
        if comment:
            thread.post(text=comment, notify=False)
        notification_tasks.send_usermentions_notification.post(self.ticket.index_id(), new_text, old_text)
        g.director.create_activity(c.user, 'modified', self.ticket,
                                   related_nodes=[c.project], tags=['ticket'])
        c.app.globals.invalidate_bin_counts()
        redirect('.')

    @without_trailing_slash
    @expose('json:')
    @require_post()
    def update_markdown(self, text=None, **kw):
        if has_access(self.ticket, 'update'):
            self.ticket.description = text
            self.ticket.commit()
            g.director.create_activity(c.user, 'modified', self.ticket, related_nodes=[c.project], tags=['ticket'])
            g.spam_checker.check(text, artifact=self.ticket, user=c.user, content_type='ticket')
            return {
                'status': 'success'
            }
        else:
            return {
                'status': 'no_permission'
            }

    @expose()
    @without_trailing_slash
    def get_markdown(self):
        return self.ticket.description

    @expose('json:')
    @require_post()
    @validate(W.subscribe_form)
    def subscribe(self, subscribe=None, unsubscribe=None, **kw):
        if subscribe:
            self.ticket.subscribe(type='direct')
        elif unsubscribe:
            self.ticket.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(artifact=self.ticket),
            'subscribed_to_tool': M.Mailbox.subscribed(),
            'subscribed_to_entire_name': 'ticket tracker',
        }

    @expose('json:')
    @require_post()
    def vote(self, vote, **kw):
        require_authenticated()
        require_access(self.ticket, 'post')
        status = 'ok'
        if vote == 'u':
            self.ticket.vote_up(c.user)
        elif vote == 'd':
            self.ticket.vote_down(c.user)
        else:
            status = 'error'
        return dict(
            status=status,
            votes_up=self.ticket.votes_up,
            votes_down=self.ticket.votes_down,
            votes_percent=self.ticket.votes_up_percent)

    @expose('jinja:forgetracker:templates/tracker/move_ticket.html')
    def move(self, **post_data):
        require_access(self.ticket.app, 'admin')
        if request.method == 'POST':
            t_id = str(post_data.pop('tracker', ''))
            try:
                t_id = ObjectId(t_id)
            except InvalidId:
                t_id = None

            tracker = M.AppConfig.query.get(_id=t_id)
            if tracker is None:
                flash('Select valid tracker', 'error')
                redirect(six.ensure_text(request.referer or '/'))

            if tracker == self.ticket.app.config:
                flash('Ticket already in a selected tracker', 'info')
                redirect(six.ensure_text(request.referer or '/'))

            if not has_access(tracker, 'admin')():
                flash('You should have admin access to destination tracker',
                      'error')
                redirect(six.ensure_text(request.referer or '/'))

            new_ticket = self.ticket.move(tracker)
            c.app.globals.invalidate_bin_counts()
            flash('Ticket successfully moved')
            redirect(new_ticket.url())

        trackers = _my_trackers(c.user, self.ticket.app.config)
        return {
            'ticket': self.ticket,
            'form': W.move_ticket_form(trackers=trackers),
        }


class AttachmentController(att.AttachmentController):
    AttachmentClass = TM.TicketAttachment
    edit_perm = 'update'

    def handle_post(self, delete, **kw):
        old_attachments = attachments_info(self.artifact.attachments)
        super().handle_post(delete, **kw)
        if delete:
            session(self.artifact.attachment_class()).flush()
            # self.artifact.attachments is ming's LazyProperty, we need to reset
            # it's cache to fetch updated attachments here:
            self.artifact.__dict__.pop('attachments')
            new_attachments = attachments_info(self.artifact.attachments)
            changes = changelog()
            changes['attachments'] = old_attachments
            changes['attachments'] = new_attachments
            post_text, notification = render_changes(changes)
            self.artifact.discussion_thread.add_post(
                text=post_text,
                is_meta=True,
                notification_text=notification)


class AttachmentsController(att.AttachmentsController):
    AttachmentControllerClass = AttachmentController


NONALNUM_RE = re.compile(r'\W+')


class TrackerAdminController(DefaultAdminController):

    def __init__(self, app):
        super().__init__(app)
        self.bins = BinController(app=self.app)
        # if self.app.globals and self.app.globals.milestone_names is None:
        #     self.app.globals.milestone_names = ''

    def _check_security(self):
        require_access(self.app, 'configure')

    @with_trailing_slash
    def index(self, **kw):
        redirect('permissions')

    @without_trailing_slash
    @expose('jinja:forgetracker:templates/tracker/admin_fields.html')
    def fields(self, **kw):
        c.form = W.field_admin
        columns = {column: get_label(column)
                       for column in self.app.globals['show_in_search'].keys()}
        return dict(app=self.app, globals=self.app.globals, columns=columns)

    @expose('jinja:forgetracker:templates/tracker/admin_options.html')
    def options(self, **kw):
        c.options_admin = W.options_admin
        return dict(app=self.app, form_value=dict(
            EnableVoting=self.app.config.options.get('EnableVoting'),
            TicketMonitoringType=self.app.config.options.get(
                'TicketMonitoringType'),
            TicketMonitoringEmail=self.app.config.options.get(
                'TicketMonitoringEmail'),
            TicketHelpNew=self.app.config.options.get('TicketHelpNew'),
            TicketHelpSearch=self.app.config.options.get('TicketHelpSearch'),
            AllowEmailPosting=self.app.config.options.get('AllowEmailPosting', True),
        ))

    @expose()
    @require_post()
    @validate(W.options_admin, error_handler=options)
    def set_options(self, **kw):
        require_access(self.app, 'configure')
        mount_point = self.app.config.options['mount_point']
        for k, val in kw.items():
            if self.app.config.options.get(k) != val:
                M.AuditLog.log('{}: set option "{}" {} => {}'.format(
                    mount_point, k, self.app.config.options.get(k), bool(val)))
                self.app.config.options[k] = val
        flash('Options updated')
        redirect(six.ensure_text(request.referer or '/'))

    @expose()
    @require_post()
    def allow_default_field(self, **post_data):
        for column in list(self.app.globals['show_in_search'].keys()):
            if post_data.get(column) == 'on':
                self.app.globals['show_in_search'][column] = True
            else:
                self.app.globals['show_in_search'][column] = False
        redirect(six.ensure_text(request.referer or '/'))

    @expose()
    def update_tickets(self, **post_data):
        pass

    @expose()
    @validate(W.field_admin, error_handler=fields)
    @require_post()
    @h.vardec
    def set_custom_fields(self, **post_data):
        self.app.globals.open_status_names = post_data['open_status_names']
        self.app.globals.closed_status_names = post_data['closed_status_names']
        custom_fields = post_data.get('custom_fields', [])
        for field in custom_fields:
            if 'name' not in field or not field['name']:
                field['name'] = '_' + '_'.join([
                    w for w in NONALNUM_RE.split(field['label'].lower()) if w])
            if field['type'] == 'milestone':
                field.setdefault('milestones', [])

        existing_milestone_fld_names = {
            mf.name for mf in self.app.globals.milestone_fields}
        posted_milestone_fld_names = {
            cf['name'] for cf in custom_fields if cf['type'] == 'milestone'}
        deleted_milestone_fld_names = existing_milestone_fld_names -\
            posted_milestone_fld_names
        added_milestone_fld_names = posted_milestone_fld_names -\
            existing_milestone_fld_names

        # TODO: make milestone custom fields renameable
        for milestone_fld_name in existing_milestone_fld_names |\
                posted_milestone_fld_names:
            if milestone_fld_name in deleted_milestone_fld_names:
                # Milestone field deleted, remove it from tickets
                tickets = TM.Ticket.query.find({
                    'app_config_id': self.app.config._id,
                    'custom_fields.%s' % milestone_fld_name:
                    {'$exists': True}}).all()
                for t in tickets:
                    del t.custom_fields[milestone_fld_name]
            elif milestone_fld_name in added_milestone_fld_names:
                # Milestone field added, sanitize milestone names
                milestone_fld = [
                    cf for cf in custom_fields
                    if cf['type'] == 'milestone'
                    and cf['name'] == milestone_fld_name][0]
                for milestone in milestone_fld.get('milestones', []):
                    milestone['name'] = milestone['name'].replace("/", "-")
            else:
                # Milestone field updated, sanitize milestone names and update
                # tickets if milestone names have changed
                existing_milestone_fld = [
                    mf for mf in self.app.globals.milestone_fields
                    if mf.name == milestone_fld_name][0]
                posted_milestone_fld = [
                    cf for cf in custom_fields
                    if cf['type'] == 'milestone'
                    and cf['name'] == milestone_fld_name][0]
                existing_milestone_names = {
                    m.name for m in
                    existing_milestone_fld.get('milestones', [])}
                old_posted_milestone_names = {
                    m['old_name']
                    for m in posted_milestone_fld.get('milestones', [])
                    if m.get('old_name', None)}
                deleted_milestone_names = existing_milestone_names -\
                    old_posted_milestone_names

                # Milestone deleted, remove it from tickets
                tickets = TM.Ticket.query.find({
                    'app_config_id': self.app.config._id,
                    'custom_fields.%s' % milestone_fld_name:
                    {'$in': list(deleted_milestone_names)}}).all()
                for t in tickets:
                    t.custom_fields[milestone_fld_name] = ''

                for milestone in posted_milestone_fld.get('milestones', []):
                    milestone['name'] = milestone['name'].replace("/", "-")
                    old_name = milestone.pop('old_name', None)
                    if old_name and old_name in existing_milestone_names \
                            and old_name != milestone['name']:
                        # Milestone name updated, need to update tickets
                        tickets = TM.Ticket.query.find({
                            'app_config_id': self.app.config._id,
                            'custom_fields.%s' % milestone_fld_name:
                            old_name}).all()
                        for t in tickets:
                            t.custom_fields[milestone_fld_name] = \
                                milestone['name']

        self.app.globals.custom_fields = custom_fields
        flash('Fields updated')
        redirect(six.ensure_text(request.referer or '/'))


class RootRestController(BaseController, AppRestControllerMixin):

    def __init__(self):
        self._discuss = AppDiscussionRestController()

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('json:')
    def index(self, limit=100, page=0, **kw):
        results = TM.Ticket.paged_query(c.app.config, c.user, query={},
                                        limit=int(limit), page=int(page))
        results['tickets'] = [dict(ticket_num=t.ticket_num, summary=t.summary)
                              for t in results['tickets']]
        results['tracker_config'] = c.app.config.__json__()
        if not has_access(c.app, 'admin', c.user):
            try:
                del results['tracker_config'][
                    'options']['TicketMonitoringEmail']
            except KeyError:
                pass
        results['milestones'] = c.app.milestones
        results['saved_bins'] = c.app.bins
        results.pop('q', None)
        results.pop('sort', None)
        return results

    @expose()
    @h.vardec
    @require_post()
    @validate(W.ticket_form, error_handler=h.json_validation_error)
    def new(self, ticket_form=None, **post_data):
        require_access(c.app, 'create')
        if TM.Ticket.is_limit_exceeded(c.app.config, user=c.user):
            msg = 'Ticket creation rate limit exceeded. '
            log.warn(msg + c.app.config.url())
            raise forge_exc.HTTPTooManyRequests()
        if c.app.globals.milestone_names is None:
            c.app.globals.milestone_names = ''
        ticket = TM.Ticket.new()
        ticket.update(ticket_form)
        c.app.globals.invalidate_bin_counts()
        redirect(str(ticket.ticket_num) + '/')

    @expose('json:')
    def search(self, q=None, limit=100, page=0, sort=None, **kw):
        def _convert_ticket(t):
            t = t.__json__()
            # just pop out all the heavy stuff
            for field in ['description', 'discussion_thread']:
                t.pop(field, None)
            return t

        results = TM.Ticket.paged_search(
            c.app.config, c.user, q, limit, page, sort, show_deleted=False)
        results['tickets'] = list(map(_convert_ticket, results['tickets']))
        return results

    @expose()
    def _lookup(self, ticket_num, *remainder):
        if ticket_num.isdigit():
            return TicketRestController(ticket_num), remainder
        raise exc.HTTPNotFound


class TicketRestController(BaseController):

    def __init__(self, ticket_num):
        if ticket_num is not None:
            self.ticket_num = int(ticket_num)
            self.ticket = TM.Ticket.query.get(app_config_id=c.app.config._id,
                                              ticket_num=self.ticket_num)
            if self.ticket is None:
                moved_ticket = TM.MovedTicket.query.get(
                    app_config_id=c.app.config._id,
                    ticket_num=self.ticket_num)
                if moved_ticket:
                    utils.permanent_redirect(
                        '/rest' + moved_ticket.moved_to_url)

                raise exc.HTTPNotFound()

    def _check_security(self):
        require_access(self.ticket, 'read')

    @expose('json:')
    def index(self, **kw):
        return dict(ticket=self.ticket.__json__(posts_limit=10))

    @expose()
    @h.vardec
    @require_post()
    @validate(W.ticket_form, error_handler=h.json_validation_error)
    def save(self, ticket_form=None, **post_data):
        require_access(self.ticket, 'update')
        # if c.app.globals.milestone_names is None:
        #     c.app.globals.milestone_names = ''
        self.ticket.update(ticket_form)
        c.app.globals.invalidate_bin_counts()
        redirect('.')


class MilestoneController(BaseController):

    def __init__(self, root, field, milestone):
        for fld in c.app.globals.milestone_fields:
            name_no_underscore = fld.name[1:]
            if name_no_underscore == field:
                break
        else:
            raise exc.HTTPNotFound()
        for m in fld.milestones:
            if m.name == six.ensure_text(unquote(milestone)):
                break
        else:
            raise exc.HTTPNotFound()
        self.root = root
        self.field = fld
        self.milestone = m
        escaped_name = escape_solr_arg(m.name)
        self.progress_key = f'{fld.name}:{escaped_name}'
        self.mongo_query = {'custom_fields.%s' % fld.name: m.name}
        self.solr_query = f'{_mongo_col_to_solr_col(fld.name)}:{escaped_name}'

    @with_trailing_slash
    @h.vardec
    @expose('jinja:forgetracker:templates/tracker/milestone.html')
    @validate(validators=dict(
        limit=validators.Int(if_invalid=None),
        page=validators.Int(if_empty=0, if_invalid=0),
        sort=v.UnicodeString(if_empty=''),
        filter=V.JsonConverter(if_empty={}),
        deleted=validators.StringBool(if_empty=False)))
    def index(self, q=None, columns=None, page=0, query=None, sort=None,
              deleted=False, filter=None, **kw):
        require(has_access(c.app, 'read'))
        show_deleted = [False]
        if deleted and has_access(c.app, 'delete'):
            show_deleted = [False, True]
        elif deleted and not has_access(c.app, 'delete'):
            deleted = False

        result = TM.Ticket.paged_query_or_search(c.app.config, c.user,
                                                 self.mongo_query,
                                                 self.solr_query,
                                                 filter, sort=sort, page=page,
                                                 deleted={'$in': show_deleted},
                                                 show_deleted=deleted, **kw)

        result['columns'] = columns or mongo_columns()
        result[
            'sortable_custom_fields'] = c.app.globals.sortable_custom_fields_shown_in_search()
        result['allow_edit'] = has_access(c.app, 'update')()
        result['allow_move'] = has_access(c.app, 'admin')()
        result['help_msg'] = c.app.config.options.get(
            'TicketHelpSearch', '').strip()
        result['deleted'] = deleted
        progress = c.app.globals.milestone_count(self.progress_key)
        result.pop('q')
        result.update(
            field=self.field,
            milestone=self.milestone,
            total=progress['hits'],
            closed=progress['closed'],
            q=self.progress_key)
        c.ticket_search_results = TicketSearchResults(result['filter_choices'])
        c.auto_resize_textarea = W.auto_resize_textarea
        return result
