from datetime import datetime
from itertools import chain
from string import Template

from sf.gobble.lib import sf_updater
from sf.gobble.queueworkers import QueueWorker
from sf.gutenberg.utils import configtree, GutenbergError
from sf.gutenberg.model import Project

class KeepsakeWorker(QueueWorker):

    def parse(self, message):
        if 'project' in message:
            shortname = message['project']
        else:
            # FRS_SUMMARY, PROJECT_REMOVE doesn't provide 'project' field to us
            shortname = Project.shortname_from_id(message['project-id'])
            if shortname is None:
                raise GutenbergError("Couldn't find project for id %s" % message['project-id'])
        return shortname, 'sf.net', dict(eventid = message['event-id'])


class SFNewsWorker(KeepsakeWorker):
    routing_keys=['sf.NEWS_ADD']
    # Hints for run-worker.py
    source = 'sf.net'
    update_type = 'news'

    def handle(self, shortname, source, **kwargs):
        return sf_updater.update_news(shortname, source, self.host, **kwargs)

class SFFilesWorker(KeepsakeWorker):
    routing_keys=['sf.FRS_SUMMARY']
    # Hints for run-worker.py
    source = 'sf.net'
    update_type = 'files'

    def handle(self, shortname, source, **kwargs):
        return sf_updater.update_files(shortname, source, self.host, **kwargs)

class SFProjectInfoWorker(KeepsakeWorker):
    # Hints for run-worker.py
    source = 'sf.net'
    update_type = 'project'

    routing_keys=['sf.PROJECT_ADD',
                  'sf.PROJECT_ADD_MEMBER',
                  'sf.PROJECT_MODIFY_INFO',
                  'sf.PROJECT_REMOVE',
                  'sf.PROJECT_RENAME',
                  'sf.PROJECT_RESTORE',
                  'sf.INVISIBLE',
                  'sf.FORUM_ADD',
                  'sf.TRACKER_ADD',
                  ]

    def handle(self, shortname, source, **kwargs):
        return sf_updater.update_project(shortname, source, self.host, **kwargs)

class SFEventWorker(QueueWorker):
    routing_keys=['sf.#']
    handle_every_message=True

    def make_descr(self, message):
        templates = {
        'GIT_COMMIT':
            'committed <a href="$url" title="Git commit $hash">$hash</a> '
            'of branch $branch to the <a href="/projects/$project/">$project</a> '
            'Git repository, changing $files files',
        'SVN_COMMIT':
            'committed revision <a href="$url" title="SVN revision $revision">'
            '$revision</a> to the <a href="/projects/$project/">$project</a> '
            'SVN repository, changing $files files',
        'CVS_COMMIT':
            'committed patchset <a href="$url" title="CVS patchset $revision">'
            '$revision</a> of module $module to the <a href="/projects/$project/">$project</a> '
            'CVS repository, changing $files files',
        'HG_COMMIT':
            'committed revision <a href="$url" title="Mercurial revision $revision">$revision</a> '
            'to the <a href="/projects/$project/">$project</a> '
            'Mercurial repository, changing $files files',
        'BZR_COMMIT':
            'committed revision <a href="$url" title="Bazaar revision $revision">$revision</a> '
            'of branch $branch to the <a href="/projects/$project/">$project</a> '
            'Bazaar repository, changing $files files',
        'PROJECT_REMOVE':
            'removed project from $old_name to $new_name',
        'PROJECT_RESTORE':
            'restored project from $old_name to $new_name',
        'PROJECT_RENAME':
            'renamed project from $old_name to $new_name',
        'FRS_SUMMARY':
            'made $total file-release changes',
        }
        if message['type'] in templates:
            try:
                # combine message and message['extended'] dicts
                vars = dict(chain(message['extended'].iteritems(), message.iteritems()))
                return Template(templates[message['type']]).substitute(vars)
            except KeyError, e:
                self.log.error("Can't complete template for %s" % message['type'], exc_info=e)
                return ''
        else:
            self.log.error("Can't build description for type %s (message had no description of its own)" % message['type'])
            return ''

    def parse(self, message):
        if message['type'] is None:
            # AMQP messages from SFX come through like
            # "routing_key" : "sf." , "message" : {"author-id" : 0 , "description" : null , "author" : null , "perms" : [] , "timestamp" : 0 , "project" : "jscalendar" , "type" : null , "project-id" : 75569 , "event-id" : 45466436}
            # if there are strange permissions situations
            # this is known to happen for some anonymous tracker comment event
            raise GutenbergError("Message data has no 'type'")

        if 'project' in message:
            shortname = message['project']
        else:
            # FRS_SUMMARY doesn't provide it to us
            shortname = Project.shortname_from_id(message['project-id'])

        event =  dict(date = datetime.fromtimestamp(message['timestamp']),
                      author_username = message.get('author',''),
                      type = message['type'],
                      description = message.get('description') or self.make_descr(message),
                      title = message['type'],
                      _id = 'http://%s/event/id/%s' % (configtree().get('sys_default_domain','sourceforge.net'), message['event-id']),
                      project = {'shortname': shortname, 'source':'sf.net'},
                      url = message.get('extended',{}).get('url'),
                      description_type = 'html',
        )

        perms = [perm.split('PERMISSION_')[1]
                 for perm in message.get('perms',[])]
        if perms:
            event['permission_required'] = perms

        if message['type'] == 'PROJECT_RENAME':
            event['project']['shortname'] = message['extended']['new_name']
        return shortname, 'sf.net', dict(event=event)

    def handle(self, shortname, source, **kwargs):
        return sf_updater.add_event(shortname, source, self.host, **kwargs)
