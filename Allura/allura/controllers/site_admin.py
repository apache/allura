import logging
from datetime import datetime, timedelta
from collections import defaultdict

from tg import expose, flash, config, request
from tg.decorators import with_trailing_slash, without_trailing_slash
from ming.orm import session
import pymongo
from pylons import c

from allura.lib import helpers as h
from allura.lib.security import require_access
from allura import model as M
from allura.command.show_models import dfs, build_model_inheritance_graph

from urlparse import urlparse


log = logging.getLogger(__name__)


class SiteAdminController(object):

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

        classes = set()
        for depth, cls in dfs(M.Artifact, build_model_inheritance_graph()):
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
