import logging
import os
import mimetypes
from datetime import datetime, timedelta
from collections import defaultdict

import pkg_resources
from tg import expose, redirect, flash, config, validate, request, response
from tg.decorators import with_trailing_slash, without_trailing_slash
from webob import exc
from formencode import validators as fev
from ming.orm import session
import pymongo
from pylons import c, g

from allura.lib import helpers as h
from allura.lib.security import require_access
from allura import model as M


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
