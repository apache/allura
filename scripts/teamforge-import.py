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
from getpass import getpass
from optparse import OptionParser
from tg import tmpl_context as c
import re
import os
from time import mktime
import time
import json
from six.moves.urllib.parse import urlparse
import six.moves.urllib.request
import six.moves.urllib.parse
import six.moves.urllib.error
from six.moves.http_cookiejar import CookieJar
from datetime import datetime
from six.moves.configparser import ConfigParser
import random
import string

import sqlalchemy
from suds.client import Client
from ming.orm.ormsession import ThreadLocalORMSession
from ming.base import Object

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils
import six

log = logging.getLogger('teamforge-import')

'''

http://help.collab.net/index.jsp?topic=/teamforge520/reference/api-services.html

http://www.open.collab.net/nonav/community/cif/csfe/50/javadoc/index.html?com/collabnet/ce/soap50/webservices/page/package-summary.html

'''

options = None
s = None  # security token
client = None  # main api client
users = {}

cj = CookieJar()
loggedInOpener = six.moves.urllib.request.build_opener(six.moves.urllib.request.HTTPCookieProcessor(cj))


def make_client(api_url, app):
    return Client(api_url + app + '?wsdl', location=api_url + app)


def main():
    global options, s, client, users
    defaults = dict(
        api_url=None,
        attachment_url='/sf/%s/do/%s/',
        default_wiki_text='PRODUCT NAME HERE',
        username=None,
        password=None,
        output_dir='teamforge-export/',
        list_project_ids=False,
        neighborhood=None,
        neighborhood_shortname=None,
        use_thread_import_id_when_reloading=False,
        skip_wiki=False,
        skip_frs_download=False,
        skip_unsupported_check=False)
    optparser = get_parser(defaults)
    options, project_ids = optparser.parse_args()
    if options.config_file:
        config = ConfigParser()
        config.read(options.config_file)
        defaults.update(
            (k, eval(v)) for k, v in config.items('teamforge-import'))
        optparser = get_parser(defaults)
        options, project_ids = optparser.parse_args()

    # neither specified, so do both
    if not options.extract and not options.load:
        options.extract = True
        options.load = True

    if options.extract:
        client = make_client(options.api_url, 'CollabNet')
        api_v = client.service.getApiVersion()
        if not api_v.startswith('5.4.'):
            log.warning('Unexpected API Version %s.  May not work correctly.' %
                        api_v)

        s = client.service.login(
            options.username, options.password or getpass('Password: '))
        teamforge_v = client.service.getVersion(s)
        if not teamforge_v.startswith('5.4.'):
            log.warning(
                'Unexpected TeamForge Version %s.  May not work correctly.' %
                teamforge_v)

    if options.load:
        if not options.neighborhood:
            log.error('You must specify a neighborhood when loading')
            return
        try:
            nbhd = M.Neighborhood.query.get(name=options.neighborhood)
        except Exception:
            log.exception('error querying mongo')
            log.error(
                'This should be run as "paster script production.ini ../scripts/teamforge-import.py -- ...options.."')
            return
        assert nbhd

    if not project_ids:
        if not options.extract:
            log.error('You must specify project ids')
            return
        projects = client.service.getProjectList(s)
        project_ids = [p.id for p in projects.dataRows]

    if options.list_project_ids:
        print(' '.join(project_ids))
        return

    if not os.path.exists(options.output_dir):
        os.makedirs(options.output_dir)
    for pid in project_ids:
        if options.extract:
            try:
                project = client.service.getProjectData(s, pid)
                log.info('Project: %s %s %s' %
                         (project.id, project.title, project.path))
                out_dir = os.path.join(options.output_dir, project.id)
                if not os.path.exists(out_dir):
                    os.mkdir(out_dir)

                get_project(project)
                get_files(project)
                if not options.skip_wiki:
                    get_homepage_wiki(project)
                get_discussion(project)
                get_news(project)
                if not options.skip_unsupported_check:
                    check_unsupported_tools(project)
                with open(os.path.join(options.output_dir, 'users.json'), 'w', encoding='utf-8') as user_file:
                    json.dump(users, user_file, default=str)
            except Exception:
                log.exception('Error extracting %s' % pid)

        if options.load:
            try:
                project = create_project(pid, nbhd)
            except Exception:
                log.exception('Error creating %s' % pid)


def load_users():
    ''' load the users data from file, if it hasn't been already '''
    global users
    user_filename = os.path.join(options.output_dir, 'users.json')
    if not users and os.path.exists(user_filename):
        with open(user_filename) as user_file:
            # Object for attribute access
            users = json.load(user_file, object_hook=Object)


def save_user(usernames):
    if isinstance(usernames, str):
        usernames = [usernames]

    load_users()

    for username in usernames:
        if username not in users:
            user_data = client.service.getUserData(s, username)
            users[username] = Object(user_data)
            if users[username].status != 'Active':
                log.warn('user: %s status: %s' %
                         (username, users[username].status))


def get_project(project):
    global client
    cats = make_client(options.api_url, 'CategorizationApp')

    data = client.service.getProjectData(s, project.id)
    access_level = {1: 'public', 4: 'private', 3: 'gated community'}[
        client.service.getProjectAccessLevel(s, project.id)
    ]
    admins = client.service.listProjectAdmins(s, project.id).dataRows
    members = client.service.getProjectMemberList(s, project.id).dataRows
    groups = client.service.getProjectGroupList(s, project.id).dataRows
    categories = cats.service.getProjectCategories(s, project.id).dataRows
    save(json.dumps(dict(
        data=dict(data),
        access_level=access_level,
        admins=list(map(dict, admins)),
        members=list(map(dict, members)),
        groups=list(map(dict, groups)),
        categories=list(map(dict, categories)),
    ), default=str),
        project, project.id + '.json')

    if len(groups):
        log.warn('Project has groups %s' % groups)
    for u in admins:
        if not u.status != 'active':
            log.warn('inactive admin %s' % u)
        if u.superUser:
            log.warn('super user admin %s' % u)

    save_user(data.createdBy)
    save_user(u.userName for u in admins)
    save_user(u.userName for u in members)


def get_user(orig_username):
    'returns an allura User object'
    sf_username = make_valid_sf_username(orig_username)

    u = M.User.by_username(sf_username)

    if not u:
        load_users()
        user = users[orig_username]
        if user.status != 'Active':
            log.warn(f'Inactive user {orig_username} {user.status}')

        if not 3 <= len(user.fullName) <= 32:
            raise Exception('invalid fullName length: %s' % user.fullName)
        if '@' not in user.email:
            raise Exception('invalid email: %s' % user.email)
        # FIXME: hardcoded SFX integration
        from sfx.model import tables as T
        nu = T.users.insert()
        nu.execute(user_name=sf_username.encode('utf-8'),
                   email=user.email.lower().encode('utf-8'),
                   realname=user.fullName.encode('utf-8'),
                   status='A' if user.status == 'Active' else 'D',
                   language=275,  # english trove id
                   timezone=user.timeZone,
                   user_pw=''.join(random.sample(string.printable, 32)),
                   unix_pw=''.join(random.sample(string.printable, 32)),
                   user_pw_modtime=int(time.time()),
                   mail_siteupdates=0,
                   add_date=int(time.time()),
                   )
        user_id = sqlalchemy.select(
            [T.users.c.user_id], T.users.c.user_name == sf_username).execute().fetchone().user_id
        npref = T.user_preferences.insert()
        npref.execute(user_id=user_id, preference_name='country',
                      preference_value='US')
        npref.execute(user_id=user_id,
                      preference_name='opt_research', preference_value=0)
        npref.execute(user_id=user_id,
                      preference_name='opt_thirdparty', preference_value=0)

        new_audit = T.audit_trail_user.insert()
        new_audit.execute(
            date=int(time.time()),
            username='nobody',
            ip_address='(imported)',
            operation_resource=user_id,
            operation='%s user account created by TeamForge import script' % user.status,
            operation_target='',
        )

        u = M.User.by_username(sf_username)
    assert u
    return u


def convert_project_shortname(teamforge_path):
    'convert from TeamForge to SF, and validate early'
    tf_shortname = teamforge_path.split('.')[-1]
    sf_shortname = tf_shortname.replace('_', '-')

    # FIXME hardcoded translations
    sf_shortname = {
        'i1': 'motorola-i1',
        'i9': 'motorola-i9',
        'devplatformforocap': 'ocap-dev-pltfrm',
        'sitewide': '--init--',
    }.get(sf_shortname, sf_shortname)

    if not 3 <= len(sf_shortname) <= 15:
        raise ValueError(
            'Project name length must be between 3 & 15, inclusive: %s (%s)' %
            (sf_shortname, len(sf_shortname)))
    return sf_shortname


# FIXME hardcoded
skip_perms_usernames = {
    'username1', 'username2', 'username3'
}


def create_project(pid, nbhd):
    M.session.artifact_orm_session._get().skip_mod_date = True
    data = loadjson(pid, pid + '.json')
    # pprint(data)
    log.info(f'Loading: {pid} {data.data.title} {data.data.path}')
    shortname = convert_project_shortname(data.data.path)

    project = M.Project.query.get(
        shortname=shortname, neighborhood_id=nbhd._id)
    if not project:
        private = (data.access_level == 'private')
        log.debug(f'Creating {shortname} private={private}')
        one_admin = [
            u.userName for u in data.admins if u.status == 'Active'][0]
        project = nbhd.register_project(shortname,
                                        get_user(one_admin),
                                        project_name=data.data.title,
                                        private_project=private)
    project.notifications_disabled = True
    project.short_description = data.data.description
    project.last_updated = datetime.strptime(
        data.data.lastModifiedDate, '%Y-%m-%d %H:%M:%S')
    M.main_orm_session.flush(project)
    # TODO: push last_updated to gutenberg?
    # TODO: try to set createdDate?

    role_admin = M.ProjectRole.by_name('Admin', project)
    admin_usernames = set()
    for admin in data.admins:
        # FIXME: skip non-active users
        if admin.userName in skip_perms_usernames:
            continue
        admin_usernames.add(admin.userName)
        user = get_user(admin.userName)
        c.user = user
        pr = M.ProjectRole.by_user(user, project=project, upsert=True)
        pr.roles = [role_admin._id]
        ThreadLocalORMSession.flush_all()
    role_developer = M.ProjectRole.by_name('Developer', project)
    for member in data.members:
        # FIXME: skip non-active users
        if member.userName in skip_perms_usernames:
            continue
        if member.userName in admin_usernames:
            continue
        user = get_user(member.userName)
        pr = M.ProjectRole.by_user(user, project=project, upsert=True)
        pr.roles = [role_developer._id]
        ThreadLocalORMSession.flush_all()
    project.labels = [cat.path.split('projects/categorization.root.')[1]
                      for cat in data.categories]
    icon_file = 'emsignia-MOBILITY-red.png'
    if 'nsn' in project.labels or 'msi' in project.labels:
        icon_file = 'emsignia-SOLUTIONS-blue.gif'
    if project.icon:
        M.ProjectFile.remove(dict(project_id=project._id, category='icon'))
    with open(os.path.join('..', 'scripts', icon_file), 'rb') as fp:
        M.ProjectFile.save_image(
            icon_file, fp, content_type=utils.guess_mime_type(icon_file),
            square=True, thumbnail_size=(48, 48),
            thumbnail_meta=dict(project_id=project._id, category='icon'))
    ThreadLocalORMSession.flush_all()

    dirs = os.listdir(os.path.join(options.output_dir, pid))

    frs_mapping = loadjson(pid, 'frs_mapping.json')

    if not options.skip_wiki and 'wiki' in dirs:
        import_wiki(project, pid, nbhd)
    if not options.skip_frs_download and not project.app_instance('downloads'):
        project.install_app('Downloads', 'downloads')
    if 'forum' in dirs:
        import_discussion(project, pid, frs_mapping, shortname, nbhd)
    if 'news' in dirs:
        import_news(project, pid, frs_mapping, shortname, nbhd)

    project.notifications_disabled = False
    ThreadLocalORMSession.flush_all()
    return project


def import_wiki(project, pid, nbhd):
    from forgewiki import model as WM

    def upload_attachments(page, pid, beginning):
        dirpath = os.path.join(options.output_dir, pid, 'wiki', beginning)
        if not os.path.exists(dirpath):
            return
        files = os.listdir(dirpath)
        for f in files:
            with open(os.path.join(options.output_dir, pid, 'wiki', beginning, f)) as fp:
                page.attach(f, fp, content_type=utils.guess_mime_type(f))
    pages = os.listdir(os.path.join(options.output_dir, pid, 'wiki'))
    # handle the homepage content
    if 'homepage_text.markdown' in pages:
        home_app = project.app_instance('home')
        h.set_context(project.shortname, 'home', neighborhood=nbhd)
        # set permissions and config options
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        home_app.config.options['show_discussion'] = False
        home_app.config.options['show_left_bar'] = False
        home_app.config.options['show_right_bar'] = False
        home_app.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'create'),
            M.ACE.allow(role_admin, 'edit'),
            M.ACE.allow(role_admin, 'delete'),
            M.ACE.allow(role_admin, 'moderate'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin')]
        p = WM.Page.upsert('Home')
        p.text = wiki2markdown(load(pid, 'wiki', 'homepage_text.markdown'))
        upload_attachments(p, pid, 'homepage')
    if 'HomePage.json' in pages and 'HomePage.markdown' in pages:
        wiki_app = project.app_instance('wiki')
        if not wiki_app:
            wiki_app = project.install_app('Wiki', 'wiki')
        h.set_context(project.shortname, 'wiki', neighborhood=nbhd)
        # set permissions and config options
        role_admin = M.ProjectRole.by_name('Admin')._id
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        wiki_app.config.options['show_discussion'] = False
        wiki_app.config.options['show_left_bar'] = False
        wiki_app.config.options['show_right_bar'] = False
        wiki_app.config.acl = [
            M.ACE.allow(role_anon, 'read'),
            M.ACE.allow(role_admin, 'create'),
            M.ACE.allow(role_admin, 'edit'),
            M.ACE.allow(role_admin, 'delete'),
            M.ACE.allow(role_admin, 'moderate'),
            M.ACE.allow(role_admin, 'configure'),
            M.ACE.allow(role_admin, 'admin')]
        # make all the wiki pages
        for page in pages:
            ending = page[-5:]
            beginning = page[:-5]
            markdown_file = '%s.markdown' % beginning
            if '.json' == ending and markdown_file in pages:
                page_data = loadjson(pid, 'wiki', page)
                content = load(pid, 'wiki', markdown_file)
                if page == 'HomePage.json':
                    globals = WM.Globals.query.get(
                        app_config_id=wiki_app.config._id)
                    if globals is not None:
                        globals.root = page_data.title
                    else:
                        globals = WM.Globals(
                            app_config_id=wiki_app.config._id, root=page_data.title)
                p = WM.Page.upsert(page_data.title)
                p.text = wiki2markdown(content)
                # upload attachments
                upload_attachments(p, pid, beginning)
                if not p.history().first():
                    p.commit()
    ThreadLocalORMSession.flush_all()


def import_discussion(project, pid, frs_mapping, sf_project_shortname, nbhd):
    from forgediscussion import model as DM
    discuss_app = project.app_instance('discussion')
    if not discuss_app:
        discuss_app = project.install_app('Discussion', 'discussion')
    h.set_context(project.shortname, 'discussion', neighborhood=nbhd)
    assert c.app
    # set permissions and config options
    role_admin = M.ProjectRole.by_name('Admin')._id
    role_developer = M.ProjectRole.by_name('Developer')._id
    role_auth = M.ProjectRole.by_name('*authenticated')._id
    role_anon = M.ProjectRole.by_name('*anonymous')._id
    discuss_app.config.acl = [
        M.ACE.allow(role_anon, 'read'),
        M.ACE.allow(role_auth, 'post'),
        M.ACE.allow(role_auth, 'unmoderated_post'),
        M.ACE.allow(role_developer, 'moderate'),
        M.ACE.allow(role_admin, 'configure'),
        M.ACE.allow(role_admin, 'admin')]
    ThreadLocalORMSession.flush_all()
    DM.Forum.query.remove(
        dict(app_config_id=discuss_app.config._id, shortname='general'))
    forums = os.listdir(os.path.join(options.output_dir, pid, 'forum'))
    for forum in forums:
        ending = forum[-5:]
        forum_name = forum[:-5]
        if '.json' == ending and forum_name in forums:
            forum_data = loadjson(pid, 'forum', forum)
            fo = DM.Forum.query.get(
                shortname=forum_name, app_config_id=discuss_app.config._id)
            if not fo:
                fo = DM.Forum(app_config_id=discuss_app.config._id,
                              shortname=forum_name)
            fo.name = forum_data.title
            fo.description = forum_data.description
            fo_num_topics = 0
            fo_num_posts = 0
            topics = os.listdir(os.path.join(options.output_dir, pid, 'forum',
                                forum_name))
            for topic in topics:
                ending = topic[-5:]
                topic_name = topic[:-5]
                if '.json' == ending and topic_name in topics:
                    fo_num_topics += 1
                    topic_data = loadjson(pid, 'forum', forum_name, topic)
                    thread_query = dict(
                        subject=topic_data.title,
                        discussion_id=fo._id,
                        app_config_id=discuss_app.config._id)
                    if not options.skip_thread_import_id_when_reloading:
                        # temporary/transitional.  Just needed the first time
                        # running with this new code against an existing import
                        # that didn't have import_ids
                        thread_query['import_id'] = topic_data.id
                    to = DM.ForumThread.query.get(**thread_query)
                    if not to:
                        to = DM.ForumThread.new(
                            subject=topic_data.title,
                            discussion_id=fo._id,
                            import_id=topic_data.id,
                            app_config_id=discuss_app.config._id)
                    to.import_id = topic_data.id
                    to_num_replies = 0
                    oldest_post = None
                    newest_post = None
                    posts = sorted(
                        os.listdir(os.path.join(options.output_dir, pid, 'forum', forum_name, topic_name)))
                    for post in posts:
                        ending = post[-5:]
                        post_name = post[:-5]
                        if '.json' == ending:
                            to_num_replies += 1
                            post_data = loadjson(pid, 'forum',
                                                 forum_name, topic_name, post)
                            p = DM.ForumPost.query.get(
                                _id='{}{}@import'.format(
                                    post_name, str(discuss_app.config._id)),
                                thread_id=to._id,
                                discussion_id=fo._id,
                                app_config_id=discuss_app.config._id)

                            if not p:
                                p = DM.ForumPost(
                                    _id='{}{}@import'.format(
                                        post_name, str(
                                            discuss_app.config._id)),
                                    thread_id=to._id,
                                    discussion_id=fo._id,
                                    app_config_id=discuss_app.config._id)
                            create_date = datetime.strptime(
                                post_data.createdDate, '%Y-%m-%d %H:%M:%S')
                            p.timestamp = create_date
                            p.author_id = str(
                                get_user(post_data.createdByUserName)._id)
                            p.text = convert_post_content(
                                frs_mapping, sf_project_shortname, post_data.content, nbhd)
                            p.status = 'ok'
                            if post_data.replyToId:
                                p.parent_id = '{}{}@import'.format(
                                    post_data.replyToId, str(discuss_app.config._id))
                            slug, full_slug = p.make_slugs(
                                parent=p.parent, timestamp=create_date)
                            p.slug = slug
                            p.full_slug = full_slug
                            if oldest_post is None or oldest_post.timestamp > create_date:
                                oldest_post = p
                            if newest_post is None or newest_post.timestamp < create_date:
                                newest_post = p
                            ThreadLocalORMSession.flush_all()
                    to.num_replies = to_num_replies
                    to.first_post_id = oldest_post._id
                    to.last_post_date = newest_post.timestamp
                    to.mod_date = newest_post.timestamp
                    fo_num_posts += to_num_replies
            fo.num_topics = fo_num_topics
            fo.num_posts = fo_num_posts
            ThreadLocalORMSession.flush_all()


def import_news(project, pid, frs_mapping, sf_project_shortname, nbhd):
    from forgeblog import model as BM
    posts = os.listdir(os.path.join(options.output_dir, pid, 'news'))
    if len(posts):
        news_app = project.app_instance('news')
        if not news_app:
            news_app = project.install_app('blog', 'news', mount_label='News')
        h.set_context(project.shortname, 'news', neighborhood=nbhd)
        # make all the blog posts
        for post in posts:
            if '.json' == post[-5:]:
                post_data = loadjson(pid, 'news', post)
                create_date = datetime.strptime(
                    post_data.createdOn, '%Y-%m-%d %H:%M:%S')
                p = BM.BlogPost.query.get(title=post_data.title,
                                          timestamp=create_date,
                                          app_config_id=news_app.config._id)
                if not p:
                    p = BM.BlogPost(title=post_data.title,
                                    timestamp=create_date,
                                    app_config_id=news_app.config._id)
                p.text = convert_post_content(
                    frs_mapping, sf_project_shortname, post_data.body, nbhd)
                p.mod_date = create_date
                p.state = 'published'
                if not p.slug:
                    p.make_slug()
                if not p.history().first():
                    p.commit()
                    ThreadLocalORMSession.flush_all()
                    M.Thread.new(discussion_id=p.app_config.discussion_id,
                                 ref_id=p.index_id(),
                                 subject='%s discussion' % p.title)
                user = get_user(post_data.createdByUsername)
                p.history().first().author = dict(
                    id=user._id,
                    username=user.username,
                    display_name=user.get_pref('display_name'))
                ThreadLocalORMSession.flush_all()


def check_unsupported_tools(project):
    docs = make_client(options.api_url, 'DocumentApp')
    doc_count = 0
    for doc in docs.service.getDocumentFolderList(s, project.id, recursive=True).dataRows:
        if doc.title == 'Root Folder':
            continue
        doc_count += 1
    if doc_count:
        log.warn('Migrating documents is not supported, but found %s docs' %
                 doc_count)

    scm = make_client(options.api_url, 'ScmApp')
    for repo in scm.service.getRepositoryList(s, project.id).dataRows:
        log.warn('Migrating SCM repos is not supported, but found %s' %
                 repo.repositoryPath)

    tasks = make_client(options.api_url, 'TaskApp')
    task_count = len(
        tasks.service.getTaskList(s, project.id, filters=None).dataRows)
    if task_count:
        log.warn('Migrating tasks is not supported, but found %s tasks' %
                 task_count)

    tracker = make_client(options.api_url, 'TrackerApp')
    tracker_count = len(
        tracker.service.getArtifactList(s, project.id, filters=None).dataRows)
    if tracker_count:
        log.warn(
            'Migrating trackers is not supported, but found %s tracker artifacts' %
            task_count)


def load(project_id, *paths):
    in_file = os.path.join(options.output_dir, project_id, *paths)
    with open(in_file, encoding='utf-8') as input:
        content = input.read()
    return content


def loadjson(*args):
    # Object for attribute access
    return json.loads(load(*args), object_hook=Object)


def save(content, project, *paths):
    out_file = os.path.join(options.output_dir, project.id, *paths)
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))
    with open(out_file, 'w', encoding='utf-8') as out:
        out.write(content.encode('utf-8'))


def download_file(tool, url_path, *filepaths):
    if tool == 'wiki':
        action = 'viewAttachment'
    elif tool == 'frs':
        action = 'downloadFile'
    else:
        raise ValueError('tool %s not supported' % tool)
    action_url = options.attachment_url % (tool, action)

    out_file = os.path.join(options.output_dir, *filepaths)
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))

    if '://' in url_path:
        url = url_path
    else:
        hostname = urlparse(options.api_url).hostname
        scheme = urlparse(options.api_url).scheme
        url = scheme + '://' + hostname + action_url + six.moves.urllib.parse.quote(url_path)
    log.debug('fetching %s' % url)

    resp = loggedInOpener.open(url)
    # if not logged in and this is private, you will get an html response instead of the file
    # log in to make sure the file should really be html
    if resp.headers.type == 'text/html':
        # log in and save the file
        resp = loggedInOpener.open(scheme + '://' + hostname + "/sf/sfmain/do/login", six.moves.urllib.parse.urlencode({
            'username': options.username,
            'password': options.password,
            'returnToUrl': url,
            'sfsubmit': 'submit'
        }))
    with open(out_file, 'w', encoding='utf-8') as out:
        out.write(resp.fp.read())
    return out_file

bracket_macro = re.compile(r'\[(.*?)\]')
h1 = re.compile(r'^!!!', re.MULTILINE)
h2 = re.compile(r'^!!', re.MULTILINE)
h3 = re.compile(r'^!', re.MULTILINE)
re_stats = re.compile(r'#+ .* [Ss]tatistics\n+(.*\[sf:.*?Statistics\].*)+')


def wiki2markdown(markup):
    '''
    Partial implementation of http://help.collab.net/index.jsp?topic=/teamforge520/reference/wiki-wikisyntax.html
    TODO: __ for bold
    TODO: quote filenames with spaces, e.g. [[img src="foo bar.jpg"]]
    '''
    def bracket_handler(matchobj):
        snippet = matchobj.group(1)
        ext = snippet.rsplit('.')[-1].lower()
        # TODO: support [foo|bar.jpg]
        if snippet.startswith('sf:'):
            # can't handle these macros
            return matchobj.group(0)
        elif ext in ('jpg', 'gif', 'png'):
            filename = snippet.split('/')[-1]
            return '[[img src=%s]]' % filename
        elif '|' in snippet:
            text, link = snippet.split('|', 1)
            return f'[{text}]({link})'
        else:
            # regular link
            return '<%s>' % snippet
    markup = bracket_macro.sub(bracket_handler, markup or '')
    markup = h1.sub('#', markup)
    markup = h2.sub('##', markup)
    markup = h3.sub('###', markup)

    markup = re_stats.sub('', markup)
    return markup

re_rel = re.compile(r'\b(rel\d+)\b')


def convert_post_content(frs_mapping, sf_project_shortname, text, nbhd):
    def rel_handler(matchobj):
        relno = matchobj.group(1)
        path = frs_mapping.get(relno)
        if path:
            return '<a href="/projects/{}.{}/files/{}">{}</a>'.format(
                sf_project_shortname, nbhd.url_prefix.strip('/'), path, path)
        else:
            return relno
    text = re_rel.sub(rel_handler, text or '')
    return text


def find_image_references(markup):
    'yields filenames'
    for matchobj in bracket_macro.finditer(markup):
        snippet = matchobj.group(1)
        ext = snippet.rsplit('.')[-1].lower()
        if ext in ('jpg', 'gif', 'png'):
            yield snippet


def get_news(project):
    '''
    Extracts news posts
    '''
    app = make_client(options.api_url, 'NewsApp')

    # find the forums
    posts = app.service.getNewsPostList(s, project.id)
    for post in posts.dataRows:
        save(json.dumps(dict(post), default=str),
             project, 'news', post.id + '.json')
        save_user(post.createdByUsername)


def get_discussion(project):
    '''
    Extracts discussion forums and posts
    '''
    app = make_client(options.api_url, 'DiscussionApp')

    # find the forums
    forums = app.service.getForumList(s, project.id)
    for forum in forums.dataRows:
        forumname = forum.path.split('.')[-1]
        log.info('Retrieving data for forum: %s' % forumname)
        save(json.dumps(dict(forum), default=str), project, 'forum',
             forumname + '.json')
        # topic in this forum
        topics = app.service.getTopicList(s, forum.id)
        for topic in topics.dataRows:
            save(json.dumps(dict(topic), default=str), project, 'forum',
                 forumname, topic.id + '.json')
            # posts in this topic
            posts = app.service.getPostList(s, topic.id)
            for post in posts.dataRows:
                save(json.dumps(dict(post), default=str), project, 'forum',
                     forumname, topic.id, post.id + '.json')
                save_user(post.createdByUserName)


def get_homepage_wiki(project):
    '''
    Extracts home page and wiki pages
    '''
    wiki = make_client(options.api_url, 'WikiApp')

    pages = {}
    wiki_pages = wiki.service.getWikiPageList(s, project.id)
    for wiki_page in wiki_pages.dataRows:
        wiki_page = wiki.service.getWikiPageData(s, wiki_page.id)
        pagename = wiki_page.path.split('/')[-1]
        save(json.dumps(dict(wiki_page), default=str),
             project, 'wiki', pagename + '.json')
        if not wiki_page.wikiText:
            log.debug('skip blank wiki page %s' % wiki_page.path)
            continue
        pages[pagename] = wiki_page.wikiText

    # PageApp does not provide a useful way to determine the Project Home special wiki page
    # so use some heuristics
    homepage = None
    if '$ProjectHome' in pages and options.default_wiki_text not in pages['$ProjectHome']:
        homepage = pages.pop('$ProjectHome')
    elif 'HomePage' in pages and options.default_wiki_text not in pages['HomePage']:
        homepage = pages.pop('HomePage')
    elif '$ProjectHome' in pages:
        homepage = pages.pop('$ProjectHome')
    elif 'HomePage' in pages:
        homepage = pages.pop('HomePage')
    else:
        log.warn('did not find homepage')

    if homepage:
        save(homepage, project, 'wiki', 'homepage_text.markdown')
        for img_ref in find_image_references(homepage):
            filename = img_ref.split('/')[-1]
            if '://' in img_ref:
                img_url = img_ref
            else:
                img_url = project.path + '/wiki/' + img_ref
            download_file('wiki', img_url, project.id,
                          'wiki', 'homepage', filename)

    for path, text in pages.items():
        if options.default_wiki_text in text:
            log.debug('skipping default wiki page %s' % path)
        else:
            save(text, project, 'wiki', path + '.markdown')
            for img_ref in find_image_references(text):
                filename = img_ref.split('/')[-1]
                if '://' in img_ref:
                    img_url = img_ref
                else:
                    img_url = project.path + '/wiki/' + img_ref
                download_file('wiki', img_url, project.id,
                              'wiki', path, filename)


def _dir_sql(created_on, project, dir_name, rel_path):
    assert options.neighborhood_shortname
    if not rel_path:
        parent_directory = "'1'"
    else:
        parent_directory = "(SELECT pfs_path FROM pfs_path WHERE path_name = '%s/')" % rel_path
    sql = """
    UPDATE pfs
      SET file_crtime = '%s'
      WHERE source_pk = (SELECT project.project FROM project WHERE project.project_name = '%s.%s')
      AND source_table = 'project'
      AND pfs_type = 'd'
      AND pfs_name = '%s'
      AND parent_directory = %s;
    """ % (created_on, convert_project_shortname(project.path), options.neighborhood_shortname,
           dir_name, parent_directory)
    return sql


def get_files(project):
    frs = make_client(options.api_url, 'FrsApp')
    valid_pfs_filename = re.compile(
        r'(?![. ])[-_ +.,=#~@!()\[\]a-zA-Z0-9]+(?<! )$')
    pfs_output_dir = os.path.join(
        os.path.abspath(options.output_dir), 'PFS', convert_project_shortname(project.path))
    sql_updates = ''

    def handle_path(obj, prev_path):
        path_component = obj.title.strip().replace(
            '/', ' ').replace('&', '').replace(':', '')
        path = os.path.join(prev_path, path_component)
        if not valid_pfs_filename.match(path_component):
            log.error('Invalid filename: "%s"' % path)
        save(json.dumps(dict(obj), default=str),
             project, 'frs', path + '.json')
        return path

    frs_mapping = {}

    for pkg in frs.service.getPackageList(s, project.id).dataRows:
        pkg_path = handle_path(pkg, '')
        pkg_details = frs.service.getPackageData(s, pkg.id)  # download count
        save(json.dumps(dict(pkg_details), default=str),
             project, 'frs', pkg_path + '_details.json')

        for rel in frs.service.getReleaseList(s, pkg.id).dataRows:
            rel_path = handle_path(rel, pkg_path)
            frs_mapping[rel['id']] = rel_path
            # download count
            rel_details = frs.service.getReleaseData(s, rel.id)
            save(json.dumps(dict(rel_details), default=str),
                 project, 'frs', rel_path + '_details.json')

            for file in frs.service.getFrsFileList(s, rel.id).dataRows:
                details = frs.service.getFrsFileData(s, file.id)

                file_path = handle_path(file, rel_path)
                save(json.dumps(dict(file,
                                     lastModifiedBy=details.lastModifiedBy,
                                     lastModifiedDate=details.lastModifiedDate,
                                     ),
                                default=str),
                     project,
                     'frs',
                     file_path + '.json'
                     )
                if not options.skip_frs_download:
                    download_file('frs', rel.path + '/' + file.id,
                                  pfs_output_dir, file_path)
                    mtime = int(mktime(details.lastModifiedDate.timetuple()))
                    os.utime(os.path.join(pfs_output_dir, file_path),
                             (mtime, mtime))

            # releases
            created_on = int(mktime(rel.createdOn.timetuple()))
            mtime = int(mktime(rel.lastModifiedOn.timetuple()))
            if os.path.exists(os.path.join(pfs_output_dir, rel_path)):
                os.utime(os.path.join(pfs_output_dir, rel_path),
                         (mtime, mtime))
            sql_updates += _dir_sql(created_on, project,
                                    rel.title.strip(), pkg_path)
        # packages
        created_on = int(mktime(pkg.createdOn.timetuple()))
        mtime = int(mktime(pkg.lastModifiedOn.timetuple()))
        if os.path.exists(os.path.join(pfs_output_dir, pkg_path)):
            os.utime(os.path.join(pfs_output_dir, pkg_path), (mtime, mtime))
        sql_updates += _dir_sql(created_on, project, pkg.title.strip(), '')
    # save pfs update sql for this project
    with open(os.path.join(options.output_dir, 'pfs_updates.sql'), 'a') as out:
        out.write('/* %s */' % project.id)
        out.write(sql_updates)
    save(json.dumps(frs_mapping), project, 'frs_mapping.json')


def get_parser(defaults):
    optparser = OptionParser(
        usage=('%prog [--options] [projID projID projID]\n'
               'If no project ids are given, all projects will be migrated'))
    optparser.set_defaults(**defaults)

    # Command-line-only options
    optparser.add_option(
        '--extract-only', action='store_true', dest='extract',
        help='Store data from the TeamForge API on the local filesystem; not load into Allura')
    optparser.add_option(
        '--load-only', action='store_true', dest='load',
        help='Load into Allura previously-extracted data')
    optparser.add_option(
        '--config-file', dest='config_file',
        help='Load options from config file')

    # Command-line options with defaults in config file
    optparser.add_option(
        '--api-url', dest='api_url', help='e.g. https://hostname/ce-soap50/services/')
    optparser.add_option(
        '--attachment-url', dest='attachment_url')
    optparser.add_option(
        '--default-wiki-text', dest='default_wiki_text',
        help='used in determining if a wiki page text is default or changed')
    optparser.add_option(
        '-u', '--username', dest='username')
    optparser.add_option(
        '-p', '--password', dest='password')
    optparser.add_option(
        '-o', '--output-dir', dest='output_dir')
    optparser.add_option(
        '--list-project-ids', action='store_true', dest='list_project_ids')
    optparser.add_option(
        '-n', '--neighborhood', dest='neighborhood',
        help='Neighborhood full name, to load in to')
    optparser.add_option(
        '--n-shortname', dest='neighborhood_shortname',
        help='Neighborhood shortname, for PFS extract SQL')
    optparser.add_option(
        '--skip-thread-import-id-when-reloading', action='store_true',
        dest='skip_thread_import_id_when_reloading'
    )
    optparser.add_option(
        '--skip-frs-download', action='store_true', dest='skip_frs_download')
    optparser.add_option(
        '--skip-wiki', action='store_true', dest='skip_wiki')
    optparser.add_option(
        '--skip-unsupported-check', action='store_true', dest='skip_unsupported_check')

    return optparser

re_username = re.compile(r"^[a-z\-0-9]+$")


def make_valid_sf_username(orig_username):
    sf_username = orig_username.replace('_', '-').lower()

    # FIXME username translation is hardcoded here:
    sf_username = dict(
        rlevy='ramilevy',
        mkeisler='mkeisler',
        bthale='bthale',
        mmuller='mattjustmull',
        MalcolmDwyer='slagheap',
        tjyang='tjyang',
        manaic='maniac76',
        srinid='cnudav',
        es='est016',
        david_peyer='david-mmi',
        okruse='ottokruse',
        jvp='jvpmoto',
        dmorelli='dmorelli',
    ).get(sf_username, sf_username + '-mmi')

    if not re_username.match(sf_username):
        adjusted_username = ''.join(
            ch for ch in sf_username[:-4]
            if ch.isalnum() or ch == '-') + '-mmi'
        log.error('invalid sf_username characters: %s Changing it to %s',
                  sf_username, adjusted_username)
        sf_username = adjusted_username
    if len(sf_username) > 15:
        adjusted_username = sf_username[0:15 - 4] + '-mmi'
        log.error('invalid sf_username length: %s   Changing it to %s',
                  sf_username, adjusted_username)
        sf_username = adjusted_username
    return sf_username

if __name__ == '__main__':
    logging.basicConfig(level=logging.WARN)
    log.setLevel(logging.DEBUG)
    main()


def test_make_valid_sf_username():
    tests = {
        # basic
        'foo': 'foo-mmi',
        # lookup
        'rlevy': 'ramilevy',
        # too long
        'u012345678901234567890': 'u0123456789-mmi',
        'foo^213': 'foo213-mmi'
    }
    for k, v in tests.items():
        assert make_valid_sf_username(k) == v


def test_convert_post_content():
    nbhd = Object()
    nbhd.url_prefix = '/motorola/'
    text = '''rel100? or ?rel101 or rel102 or rel103a or rel104'''
    mapping = dict(
        rel100='rel/100/',
        rel101='rel/101/',
        rel102='rel/102/',
        rel103='rel/103/',
        rel104='rel/104/')
    converted = convert_post_content(mapping, 'foo', text, nbhd)
    assert 'href="/projects/foo.motorola/files/rel/100' in converted, converted
    assert 'href="/projects/foo.motorola/files/rel/101' in converted, converted
    assert 'href="/projects/foo.motorola/files/rel/102' in converted, converted
    assert 'href="/projects/foo.motorola/files/rel/103' not in converted, converted
    assert 'href="/projects/foo.motorola/files/rel/104' in converted, converted


def test_convert_markup():

    markup = '''
!this is the first headline
Please note that this project is for distributing, discussing, and supporting the open source software we release.

[http://www.google.com]

[SourceForge |http://www.sf.net]

[$ProjectHome/myimage.jpg]
[$ProjectHome/anotherimage.jpg]

!!! Project Statistics

|[sf:frsStatistics]|[sf:artifactStatistics]|
    '''

    new_markup = wiki2markdown(markup)
    assert '\n[[img src=myimage.jpg]]\n[[img src=anotherimage.jpg]]\n' in new_markup
    assert '\n###this is the first' in new_markup
    assert '<http://www.google.com>' in new_markup
    assert '[SourceForge ](http://www.sf.net)' in new_markup
    assert '\n# Project Statistics' not in new_markup
    assert '[sf:frsStatistics]' not in new_markup
