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

import re
import logging
from datetime import datetime, timedelta

from tg import expose, validate, flash, config, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
import bson
import tg
from pylons import app_globals as g
from pylons import tmpl_context as c
from pylons import request
from formencode import validators, Invalid
from webob.exc import HTTPNotFound

from allura.app import SitemapEntry
from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.decorators import require_post
from allura.lib.plugin import SiteAdminExtension
from allura.lib.security import require_access
from allura.lib.widgets import form_fields as ffw
from allura.ext.admin.widgets import AuditLog
from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph
import allura

from urlparse import urlparse


log = logging.getLogger(__name__)


class W:
    page_list = ffw.PageList()
    page_size = ffw.PageSize()
    audit = AuditLog()


class SiteAdminController(object):

    def __init__(self):
        self.task_manager = TaskManagerController()
        c.site_admin_sidebar_menu = self.sidebar_menu()

    def _check_security(self):
        with h.push_context(config.get('site_admin_project', 'allura'),
                            neighborhood=config.get('site_admin_project_nbhd', 'Projects')):
            require_access(c.project, 'admin')

    @expose()
    def _lookup(self, name, *remainder):
        for ep_name in sorted(g.entry_points['site_admin'].keys()):
            admin_extension = g.entry_points['site_admin'][ep_name]
            controller = admin_extension().controllers.get(name)
            if controller:
                return controller(), remainder
        raise HTTPNotFound, name

    def sidebar_menu(self):
        base_url = '/nf/admin/'
        links = [
            SitemapEntry('Home', base_url, ui_icon=g.icons['admin']),
            SitemapEntry('Add Subscribers', base_url + 'add_subscribers', ui_icon=g.icons['admin']),
            SitemapEntry('New Projects', base_url + 'new_projects', ui_icon=g.icons['admin']),
            SitemapEntry('Reclone Repo', base_url + 'reclone_repo', ui_icon=g.icons['admin']),
            SitemapEntry('Task Manager', base_url + 'task_manager?state=busy', ui_icon=g.icons['stats']),
            SitemapEntry('Users Audit Log', base_url + 'users', ui_icon=g.icons['admin']),
        ]
        for ep_name in sorted(g.entry_points['site_admin']):
            g.entry_points['site_admin'][ep_name]().update_sidebar_menu(links)
        return links

    @expose('jinja:allura:templates/site_admin_index.html')
    @with_trailing_slash
    def index(self):
        return {}

    def subscribe_artifact(self, url, user):
        artifact_url = urlparse(url).path[1:-1].split("/")
        neighborhood = M.Neighborhood.query.find({
            "url_prefix": "/" + artifact_url[0] + "/"}).first()

        if artifact_url[0] == "u":
            project = M.Project.query.find({
                "shortname": artifact_url[0] + "/" + artifact_url[1],
                "neighborhood_id": neighborhood._id}).first()
        else:
            project = M.Project.query.find({
                "shortname": artifact_url[1],
                "neighborhood_id": neighborhood._id}).first()

        appconf = M.AppConfig.query.find({
            "options.mount_point": artifact_url[2],
            "project_id": project._id}).first()

        if appconf.url() == urlparse(url).path:
            M.Mailbox.subscribe(
                user_id=user._id,
                app_config_id=appconf._id,
                project_id=project._id)
            return True

        tool_packages = h.get_tool_packages(appconf.tool_name)
        classes = set()
        for depth, cls in dfs(M.Artifact, build_model_inheritance_graph()):
            for pkg in tool_packages:
                if cls.__module__.startswith(pkg + '.'):
                    classes.add(cls)
        for cls in classes:
            for artifact in cls.query.find({"app_config_id": appconf._id}):
                if artifact.url() == urlparse(url).path:
                    M.Mailbox.subscribe(
                        user_id=user._id,
                        app_config_id=appconf._id,
                        project_id=project._id,
                        artifact=artifact)
                    return True
        return False

    @expose('jinja:allura:templates/site_admin_add_subscribers.html')
    @without_trailing_slash
    def add_subscribers(self, **data):
        if request.method == 'POST':
            url = data['artifact_url']
            user = M.User.by_username(data['for_user'])
            if not user or user == M.User.anonymous():
                flash('Invalid login', 'error')
                return data

            try:
                ok = self.subscribe_artifact(url, user)
            except:
                log.warn("Can't subscribe to artifact", exc_info=True)
                ok = False

            if ok:
                flash('User successfully subscribed to the artifact')
                return {}
            else:
                flash('Artifact not found', 'error')

        return data

    @expose('jinja:allura:templates/site_admin_new_projects.html')
    @without_trailing_slash
    def new_projects(self, **kwargs):
        start_dt = kwargs.pop('start-dt', '')
        end_dt = kwargs.pop('end-dt', '')
        try:
            start_dt = datetime.strptime(start_dt, '%Y/%m/%d %H:%M:%S')
        except ValueError:
            start_dt = datetime.utcnow() + timedelta(days=1)
        try:
            end_dt = datetime.strptime(end_dt, '%Y/%m/%d %H:%M:%S')
        except ValueError:
            end_dt = start_dt - timedelta(days=3) if not end_dt else end_dt
        start = bson.ObjectId.from_datetime(start_dt)
        end = bson.ObjectId.from_datetime(end_dt)
        nb = M.Neighborhood.query.get(name='Users')
        projects = (M.Project.query.find({
            'neighborhood_id': {'$ne': nb._id},
            'deleted': False,
            '_id': {'$lt': start, '$gt': end},
        }).sort('_id', -1))
        step = start_dt - end_dt
        params = request.params.copy()
        params['start-dt'] = (start_dt + step).strftime('%Y/%m/%d %H:%M:%S')
        params['end-dt'] = (end_dt + step).strftime('%Y/%m/%d %H:%M:%S')
        newer_url = tg.url(params=params).lstrip('/')
        params['start-dt'] = (start_dt - step).strftime('%Y/%m/%d %H:%M:%S')
        params['end-dt'] = (end_dt - step).strftime('%Y/%m/%d %H:%M:%S')
        older_url = tg.url(params=params).lstrip('/')
        return {
            'projects': projects,
            'newer_url': newer_url,
            'older_url': older_url,
            'window_start': start_dt,
            'window_end': end_dt,
        }

    @expose('jinja:allura:templates/site_admin_reclone_repo.html')
    @without_trailing_slash
    @validate(dict(prefix=validators.NotEmpty(),
                   shortname=validators.NotEmpty(),
                   mount_point=validators.NotEmpty()))
    def reclone_repo(self, prefix=None, shortname=None, mount_point=None, **data):
        if request.method == 'POST':
            if c.form_errors:
                error_msg = 'Error: '
                for msg in list(c.form_errors):
                    names = {'prefix': 'Neighborhood prefix', 'shortname':
                             'Project shortname', 'mount_point': 'Repository mount point'}
                    error_msg += '%s: %s ' % (names[msg], c.form_errors[msg])
                    flash(error_msg, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            nbhd = M.Neighborhood.query.get(url_prefix='/%s/' % prefix)
            if not nbhd:
                flash('Neighborhood with prefix %s not found' %
                      prefix, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.project = M.Project.query.get(
                shortname=shortname, neighborhood_id=nbhd._id)
            if not c.project:
                flash(
                    'Project with shortname %s not found in neighborhood %s' %
                    (shortname, nbhd.name), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.app = c.project.app_instance(mount_point)
            if not c.app:
                flash('Mount point %s not found on project %s' %
                      (mount_point, c.project.shortname), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            source_url = c.app.config.options.get('init_from_url')
            source_path = c.app.config.options.get('init_from_path')
            if not (source_url or source_path):
                flash('%s does not appear to be a cloned repo' %
                      c.app, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            allura.tasks.repo_tasks.reclone_repo.post(
                prefix=prefix, shortname=shortname, mount_point=mount_point)
            flash('Repository is being recloned')
        else:
            prefix = 'p'
            shortname = ''
            mount_point = ''
        return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)

    @expose('jinja:allura:templates/site_admin_users_audit.html')
    def users(self, username=None, limit=25, page=0, **kwargs):
        user = M.User.by_username(username)
        limit = int(limit)
        page = int(page)
        if user is None or user.is_anonymous():
            return dict(
                entries=[],
                limit=limit,
                page=page,
                count=0,
                username=username)
        count = M.AuditLog.for_user(user).count()
        q = M.AuditLog.for_user(user)
        q = q.sort('timestamp', -1)
        q = q.skip(page * limit)
        if count > limit:
            q = q.limit(limit)
        else:
            limit = count
        c.widget = W.audit
        return dict(
            entries=q.all(),
            limit=limit,
            page=page,
            count=count,
            audit_user=user,
            username=username)

    @expose()
    @require_post()
    def add_audit_trail_entry(self, **kw):
        username = kw.get('username')
        comment = kw.get('comment')
        user = M.User.by_username(username)
        if user and not user.is_anonymous() and comment:
            M.AuditLog.comment_user(c.user, comment, user=user)
            flash('Comment added', 'ok')
        else:
            flash('Can not add comment "%s" for user %s' % (comment, user))
        redirect(request.referer)


class TaskManagerController(object):

    def _check_security(self):
        with h.push_context(config.get('site_admin_project', 'allura'),
                            neighborhood=config.get('site_admin_project_nbhd', 'Projects')):
            require_access(c.project, 'admin')

    @expose('jinja:allura:templates/site_admin_task_list.html')
    @without_trailing_slash
    def index(self, page_num=1, minutes=10, state=None, task_name=None, host=None):
        now = datetime.utcnow()
        try:
            page_num = int(page_num)
        except ValueError:
            page_num = 1
        try:
            minutes = int(minutes)
        except ValueError:
            minutes = 1
        start_dt = now - timedelta(minutes=(page_num - 1) * minutes)
        end_dt = now - timedelta(minutes=page_num * minutes)
        start = bson.ObjectId.from_datetime(start_dt)
        end = bson.ObjectId.from_datetime(end_dt)
        query = {'_id': {'$gt': end}}
        if page_num > 1:
            query['_id']['$lt'] = start
        if state:
            query['state'] = state
        if task_name:
            query['task_name'] = re.compile(re.escape(task_name))
        if host:
            query['process'] = re.compile(re.escape(host))

        tasks = list(M.monq_model.MonQTask.query.find(query).sort('_id', -1))
        for task in tasks:
            task.project = M.Project.query.get(_id=task.context.project_id)
            task.user = M.User.query.get(_id=task.context.user_id)
        newer_url = tg.url(
            params=dict(request.params, page_num=page_num - 1)).lstrip('/')
        older_url = tg.url(
            params=dict(request.params, page_num=page_num + 1)).lstrip('/')
        return dict(
            tasks=tasks,
            page_num=page_num,
            minutes=minutes,
            newer_url=newer_url,
            older_url=older_url,
            window_start=start_dt,
            window_end=end_dt,
        )

    @expose('jinja:allura:templates/site_admin_task_view.html')
    @without_trailing_slash
    def view(self, task_id):
        try:
            task = M.monq_model.MonQTask.query.get(_id=bson.ObjectId(task_id))
        except bson.errors.InvalidId:
            task = None
        if task:
            task.project = M.Project.query.get(_id=task.context.project_id)
            task.app_config = M.AppConfig.query.get(
                _id=task.context.app_config_id)
            task.user = M.User.query.get(_id=task.context.user_id)
        return dict(task=task)

    @expose('jinja:allura:templates/site_admin_task_new.html')
    @without_trailing_slash
    def new(self, **kw):
        """Render the New Task form"""
        return dict(
            form_errors=c.form_errors or {},
            form_values=c.form_values or {},
        )

    @expose()
    @require_post()
    @validate(v.CreateTaskSchema(), error_handler=new)
    def create(self, task, task_args=None, user=None, path=None):
        """Post a new task"""
        args = task_args.get("args", ())
        kw = task_args.get("kwargs", {})
        config_dict = path
        if user:
            config_dict['user'] = user
        with h.push_config(c, **config_dict):
            task = task.post(*args, **kw)
        redirect('view/%s' % task._id)

    @expose()
    @require_post()
    def resubmit(self, task_id):
        try:
            task = M.monq_model.MonQTask.query.get(_id=bson.ObjectId(task_id))
        except bson.errors.InvalidId:
            task = None
        if task is None:
            raise HTTPNotFound()
        task.state = 'ready'
        redirect('../view/%s' % task._id)

    @expose('json:')
    def task_doc(self, task_name):
        """Return a task's docstring"""
        error, doc = None, None
        try:
            task = v.TaskValidator.to_python(task_name)
            doc = task.__doc__ or 'No doc string available'
        except Invalid as e:
            error = str(e)
        return dict(doc=doc, error=error)


class StatsController(object):
    """Show neighborhood stats."""
    @expose('jinja:allura:templates/site_admin_stats.html')
    @with_trailing_slash
    def index(self):
        neighborhoods = []
        for n in M.Neighborhood.query.find():
            project_count = M.Project.query.find(
                dict(neighborhood_id=n._id)).count()
            configured_count = M.Project.query.find(
                dict(neighborhood_id=n._id, database_configured=True)).count()
            neighborhoods.append((n.name, project_count, configured_count))
        neighborhoods.sort(key=lambda n: n[0])
        return dict(neighborhoods=neighborhoods)


class StatsSiteAdminExtension(SiteAdminExtension):
    controllers = {'stats': StatsController}

    def update_sidebar_menu(self, links):
        links.append(SitemapEntry('Stats', '/nf/admin/stats',
            ui_icon=g.icons['stats']))
