import re
import json
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from tg import expose, validate, flash, config, redirect
from tg.decorators import with_trailing_slash, without_trailing_slash
from ming.orm import session
import pymongo
import bson
import tg
from pylons import tmpl_context as c, app_globals as g
from pylons import request
from formencode import validators, Invalid

from allura.lib import helpers as h
from allura.lib import validators as v
from allura.lib.decorators import require_post
from allura.lib.security import require_access
from allura.lib.widgets import form_fields as ffw
from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph
import allura

from urlparse import urlparse


log = logging.getLogger(__name__)

class W:
    page_list = ffw.PageList()
    page_size = ffw.PageSize()

class SiteAdminController(object):

    def __init__(self):
        self.task_manager = TaskManagerController()

    def _check_security(self):
        with h.push_context(config.get('site_admin_project', 'allura'),
                            neighborhood=config.get('site_admin_project_nbhd', 'Projects')):
            require_access(c.project, 'admin')

    @expose('jinja:allura:templates/site_admin_index.html')
    @with_trailing_slash
    def index(self):
        neighborhoods = []
        for n in M.Neighborhood.query.find():
            project_count = M.Project.query.find(dict(neighborhood_id=n._id)).count()
            configured_count = M.Project.query.find(dict(neighborhood_id=n._id, database_configured=True)).count()
            neighborhoods.append((n.name, project_count, configured_count))
        neighborhoods.sort(key=lambda n:n[0])
        return dict(neighborhoods=neighborhoods)

    @expose('jinja:allura:templates/site_admin_stats.html')
    @without_trailing_slash
    def stats(self, limit=25):
        stats = defaultdict(lambda:defaultdict(list))
        agg_timings = defaultdict(list)
        for doc in M.Stats.m.find():
            if doc.url.startswith('/_debug'): continue
            doc_stats = stats[doc.url]
            for t,val in doc.timers.iteritems():
                doc_stats[t].append(val)
                agg_timings[t].append(val)
        for url, timings in stats.iteritems():
            new_timings = dict(
                (timer, round(sum(readings)/len(readings),3))
                for timer, readings in timings.iteritems())
            timings.update(new_timings)
        agg_timings = dict(
            (timer, round(sum(readings)/len(readings),3))
            for timer, readings in agg_timings.iteritems())
        stats = sorted(stats.iteritems(), key=lambda x:-x[1]['total'])
        return dict(
            agg_timings=agg_timings,
            stats=stats[:int(limit)])

    @expose('jinja:allura:templates/site_admin_api_tickets.html')
    @without_trailing_slash
    def api_tickets(self, **data):
        import json
        import dateutil.parser
        if request.method == 'POST':
            log.info('api_tickets: %s', data)
            ok = True
            for_user = M.User.by_username(data['for_user'])
            if not for_user:
                ok = False
                flash('User not found')
            caps = None
            try:
                caps = json.loads(data['caps'])
            except ValueError:
                ok = False
                flash('JSON format error')
            if type(caps) is not type({}):
                ok = False
                flash('Capabilities must be a JSON dictionary, mapping capability name to optional discriminator(s) (or "")')
            try:
                expires = dateutil.parser.parse(data['expires'])
            except ValueError:
                ok = False
                flash('Date format error')
            if ok:
                tok = None
                try:
                    tok = M.ApiTicket(user_id=for_user._id, capabilities=caps, expires=expires)
                    session(tok).flush()
                    log.info('New token: %s', tok)
                    flash('API Ticket created')
                except:
                    log.exception('Could not create API ticket:')
                    flash('Error creating API ticket')
        elif request.method == 'GET':
            data = {'expires': datetime.utcnow() + timedelta(days=2)}

        data['token_list'] = M.ApiTicket.query.find().sort('mod_date', pymongo.DESCENDING).all()
        log.info(data['token_list'])
        return data

    def subscribe_artifact(self, url, user):
        artifact_url = urlparse(url).path[1:-1].split("/")
        neighborhood = M.Neighborhood.query.find({
            "url_prefix": "/" + artifact_url[0] + "/"}).first()

        if  artifact_url[0] == "u":
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

        tool_package = h.get_tool_package(appconf.tool_name)
        classes = set()
        for depth, cls in dfs(M.Artifact, build_model_inheritance_graph()):
            if cls.__module__.startswith(tool_package + '.'):
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
    @validate(dict(page=validators.Int(if_empty=0),
                   limit=validators.Int(if_empty=100)))
    def new_projects(self, page=0, limit=100, **kwargs):
        c.page_list = W.page_list
        c.page_size = W.page_size
        limit, pagenum, start = g.handle_paging(limit, page, default=100)
        count = 0
        nb = M.Neighborhood.query.get(name='Users')
        projects = (M.Project.query.find({'neighborhood_id': {'$ne': nb._id}})
                                   .sort('_id', -1))
        count = projects.count()
        projects = projects.skip(start).limit(limit)
        return {
            'projects': projects,
            'limit': limit,
            'pagenum': pagenum,
            'count': count
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
                    names = {'prefix': 'Neighborhood prefix', 'shortname': 'Project shortname', 'mount_point': 'Repository mount point'}
                    error_msg += '%s: %s ' % (names[msg], c.form_errors[msg])
                    flash(error_msg, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            nbhd = M.Neighborhood.query.get(url_prefix='/%s/' % prefix)
            if not nbhd:
                flash('Neighborhood with prefix %s not found' % prefix, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.project = M.Project.query.get(shortname=shortname, neighborhood_id=nbhd._id)
            if not c.project:
                flash('Project with shortname %s not found in neighborhood %s' % (shortname, nbhd.name), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            c.app = c.project.app_instance(mount_point)
            if not c.app:
                flash('Mount point %s not found on project %s' % (mount_point, c.project.shortname), 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            source_url = c.app.config.options.get('init_from_url')
            source_path = c.app.config.options.get('init_from_path')
            if not (source_url or source_path):
                flash('%s does not appear to be a cloned repo' % c.app, 'error')
                return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)
            allura.tasks.repo_tasks.reclone_repo.post(prefix=prefix, shortname=shortname, mount_point=mount_point)
            flash('Repository is being recloned')
        else:
            prefix = 'p'
            shortname = ''
            mount_point = ''
        return dict(prefix=prefix, shortname=shortname, mount_point=mount_point)

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
        except ValueError as e:
            page_num = 1
        try:
            minutes = int(minutes)
        except ValueError as e:
            minutes = 1
        start_dt = now - timedelta(minutes=(page_num-1)*minutes)
        end_dt = now - timedelta(minutes=page_num*minutes)
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
        newer_url = tg.url(params=dict(request.params, page_num=page_num - 1)).lstrip('/')
        older_url = tg.url(params=dict(request.params, page_num=page_num + 1)).lstrip('/')
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
        except bson.errors.InvalidId as e:
            task = None
        if task:
            task.project = M.Project.query.get(_id=task.context.project_id)
            task.app_config = M.AppConfig.query.get(_id=task.context.app_config_id)
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
        redirect('view', task_id=task._id)

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
