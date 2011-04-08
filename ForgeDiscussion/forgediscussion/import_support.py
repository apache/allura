#-*- python -*-
import logging
from datetime import datetime

from ming import schema as S
from ming.orm import ThreadLocalORMSession, session

from pylons import c

from allura import model as M

from forgediscussion import model as DM

log = logging.getLogger(__name__)

def validate_import(json, username_mapping, default_username=None):
    warnings = []
    schema = make_schema(username_mapping, default_username, warnings)
    json = schema.validate(json)
    return warnings, json

def perform_import(json, username_mapping, default_username=None, create_users=False):
    if create_users: default_username=create_user

    # Validate the import, create missing users
    warnings, json = validate_import(json, username_mapping, default_username)
    for w in warnings:
        log.warning('Importing to %s/%s: %s',
                    c.project.shortname,
                    c.app.config.options.mount_point,
                    w)

    for name, forum in json.forums.iteritems():
        log.info('... %s has %d threads with %d total posts',
                 name, len(forum.threads), sum(len(t) for t in forum.threads.itervalues()))

    for name, forum in json.forums.iteritems():
        log.info('... creating %s/%s: %s',
                 c.project.shortname,
                 c.app.config.options.mount_point,
                 name)
        f = DM.Forum(
            app_config_id=c.app.config._id,
            name=forum['name'],
            shortname=forum['name'],
            description=forum['description'])
        for tid, posts in forum.threads.iteritems():
            rest, head = posts[:-1], posts[-1]
            t = DM.ForumThread(
                _id=tid,
                discussion_id=f._id,
                subject=head['subject'])
            for p in posts:
                p = create_post(f._id, t._id, p)
            t.first_post_id=p._id
            ThreadLocalORMSession.flush_all()
            t.update_stats()
        ThreadLocalORMSession.flush_all()
        f.update_stats()
    return warnings

def make_schema(user_name_map, default_username, warnings):
    USER = AlluraUser(user_name_map, default_username, warnings)
    TIMESTAMP = TimeStamp()

    POST = {
        'msg_id':str,
        'is_followup_to':str,
        'is_deleted':str,
        'thread_id':str,
        'poster_name':str,
        'poster_user':USER,
        'subject':str,
        'date':TIMESTAMP,
        'body':str,
        }

    FORUM = {
        'name': str,
        'description': str,
        'threads': { str: [ POST ] },
        }

    result = S.SchemaItem.make({
            'class':str,
            'trackers':[None],
            'forums': { str: FORUM }
            })
    return result

class AlluraUser(S.FancySchemaItem):

    def __init__(self, mapping, default_username, warnings, **kw):
        self.mapping = mapping
        self.default_username = default_username
        self.warnings = warnings
        super(AlluraUser, self).__init__(**kw)

    def _validate(self, value):
        value = S.String().validate(value)
        sf_username = self.mapping.get(value, value)
        result = M.User.by_username(sf_username)
        if result is None:
            self.warnings.append('User %s not found' % value)
            if callable(self.default_username):
                sf_username = self.default_username(value)
            else:
                sf_username = self.default_username
            self.warnings.append('... setting username to %r' % sf_username)
            result = M.User.by_username(sf_username)
            self.mapping[value] = sf_username
        return result

    def _from_python(self, value, state):
        return value.username

class TimeStamp(S.FancySchemaItem):

    def _validate(self, value):
        try:
            value = int(value)
        except TypeError:
            raise S.Invalid('%s is not int()-able' % value, value, None)
        value = datetime.fromtimestamp(value)
        return value

def create_user(json_username):
    allura_username = c.project.shortname + '-' + json_username
    while True:
        try:
            M.User.register(
                dict(
                    username=allura_username,
                    display_name=allura_username),
                False)
            session(M.User).flush()
            break
        except:
            raise
    return allura_username

def create_post(discussion_id, thread_id, json_post):
    p = DM.ForumPost(
        _id='%s@import' % (json_post.msg_id),
        thread_id=thread_id,
        discussion_id=discussion_id,
        timestamp=json_post.date,
        author_id=json_post.poster_user._id,
        subject=json_post.subject,
        text=json_post.body,
        status='ok')
    if json_post.is_followup_to not in ('0', '-1'):
        p.parent_id = '%s@import' % (json_post['is_followup_to'])
    return p
