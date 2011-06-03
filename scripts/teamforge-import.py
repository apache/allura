import logging
from getpass import getpass
from optparse import OptionParser
from pylons import c
import re
import os
import os.path
from time import mktime
import json
from urlparse import urlparse
from urllib import FancyURLopener
from pprint import pprint
from datetime import datetime

from suds.client import Client
from suds import WebFault
from ming.orm.ormsession import ThreadLocalORMSession
from ming.base import Object

from allura import model as M
from allura.lib import helpers as h
from allura.lib import utils

log = logging.getLogger('teamforge-import')

'''

http://help.collab.net/index.jsp?topic=/teamforge520/reference/api-services.html

http://www.open.collab.net/nonav/community/cif/csfe/50/javadoc/index.html?com/collabnet/ce/soap50/webservices/page/package-summary.html

'''

options = None
s = None # security token
users = set()

def make_client(api_url, app):
    return Client(api_url + app + '?wsdl', location=api_url + app)

def main():
    global options, s
    optparser = OptionParser(usage='''%prog [--options] [projID projID projID]\nIf no project ids are given, all projects will be migrated''')
    optparser.add_option('--api-url', dest='api_url', help='e.g. https://hostname/ce-soap50/services/')
    optparser.add_option('--attachment-url', dest='attachment_url', default='/sf/%s/do/%s/')
    optparser.add_option('--default-wiki-text', dest='default_wiki_text', default='PRODUCT NAME HERE', help='used in determining if a wiki page text is default or changed')
    optparser.add_option('-u', '--username', dest='username')
    optparser.add_option('-p', '--password', dest='password')
    optparser.add_option('-o', '--output-dir', dest='output_dir', default='teamforge-export/')
    optparser.add_option('--list-project-ids', action='store_true', dest='list_project_ids')
    optparser.add_option('--extract-only', action='store_true', dest='extract', help='Store data from the TeamForge API on the local filesystem; not load into Allura')
    optparser.add_option('--load-only', action='store_true', dest='load', help='Load into Allura previously-extracted data')
    optparser.add_option('-n', '--neighborhood', dest='neighborhood')
    optparser.add_option('--skip-frs-download', action='store_true', dest='skip_frs_download')
    optparser.add_option('--skip-unsupported-check', action='store_true', dest='skip_unsupported_check')
    options, project_ids = optparser.parse_args()

    # neither specified, so do both
    if not options.extract and not options.load:
        options.extract = True
        options.load = True


    if options.extract:
        c = make_client(options.api_url, 'CollabNet')
        api_v = c.service.getApiVersion()
        if not api_v.startswith('5.4.'):
            log.warning('Unexpected API Version %s.  May not work correctly.' % api_v)

        s = c.service.login(options.username, options.password or getpass('Password: '))
        teamforge_v = c.service.getVersion(s)
        if not teamforge_v.startswith('5.4.'):
            log.warning('Unexpected TeamForge Version %s.  May not work correctly.' % teamforge_v)

    if options.load:
        if not options.neighborhood:
            log.error('You must specify a neighborhood when loading')
            return
        try:
            nbhd = M.Neighborhood.query.get(name=options.neighborhood)
        except:
            log.exception('error querying mongo')
            log.error('This should be run as "paster script production.ini ../scripts/teamforge-import.py -- ...options.."')
            return
        assert nbhd

    if not project_ids:
        if not options.extract:
            log.error('You must specify project ids')
            return
        projects = c.service.getProjectList(s)
        project_ids = [p.id for p in projects.dataRows]

    if options.list_project_ids:
        print ' '.join(project_ids)
        return

    if not os.path.exists(options.output_dir):
        os.makedirs(options.output_dir)
    for pid in project_ids:
        if options.extract:
            try:
                project = c.service.getProjectData(s, pid)
                log.info('Project: %s %s %s' % (project.id, project.title, project.path))
                out_dir = os.path.join(options.output_dir, project.id)
                if not os.path.exists(out_dir):
                    os.mkdir(out_dir)

                get_project(project, c)
                get_files(project)
                get_homepage_wiki(project)
                get_discussion(project)
                get_news(project)
                if not options.skip_unsupported_check:
                    check_unsupported_tools(project)
            except:
                log.exception('Error extracting %s' % pid)

        if options.load:
            try:
                project = create_project(pid, nbhd)
            except:
                log.exception('Error creating %s' % pid)

    if options.extract:
        log.info('Users encountered: %s', len(users))
        with open(os.path.join(options.output_dir, 'usernames.json'), 'w') as out:
            out.write(json.dumps(list(users)))

def get_project(project, c):
    cats = make_client(options.api_url, 'CategorizationApp')

    data = c.service.getProjectData(s, project.id)
    access_level = { 1: 'public', 4: 'private', 3: 'gated community'}[
        c.service.getProjectAccessLevel(s, project.id)
    ]
    admins = c.service.listProjectAdmins(s, project.id).dataRows
    members = c.service.getProjectMemberList(s, project.id).dataRows
    groups = c.service.getProjectGroupList(s, project.id).dataRows
    categories = cats.service.getProjectCategories(s, project.id).dataRows
    save(json.dumps(dict(
            data = dict(data),
            access_level = access_level,
            admins = map(dict, admins),
            members = map(dict, members),
            groups = map(dict, groups),
            categories = map(dict, categories),
        ), default=str),
        project, project.id+'.json')

    if len(groups):
        log.warn('Project has groups %s' % groups)
    for u in admins:
        if not u.status != 'active':
            log.warn('inactive admin %s' % u)
        if u.superUser:
            log.warn('super user admin %s' % u)

    global users
    users |= set(u.userName for u in admins)
    users |= set(u.userName for u in members)

def get_user(orig_username):
    'returns an allura User object'
    sf_username = orig_username.replace('_','-').lower()

    # FIXME username translation is hardcoded here:
    sf_username = dict(
        rlevy = 'ramilevy',
        mkeisler = 'mkeisler',
        bthale = 'bthale',
        mmuller = 'mattjustmull',
        MalcolmDwyer = 'slagheap',
        tjyang = 'tjyang',
        manaic = 'maniac76',
        srinid = 'cnudav',
        es = 'est016',
        david_peyer = 'david-mmi',
        okruse = 'ottokruse',
        jvp = 'jvpmoto',
        dmorelli = 'dmorelli',
    ).get(sf_username, sf_username + '-mmi')

    #u = M.User.by_username(sf_username)

    # FIXME: temporary:
    import random
    bogus = 'user%02d' % random.randrange(1,20)
    try:
        u = M.User.by_username(bogus)
    except:
        # try again
        return get_user(orig_username)

    assert u
    return u

def convert_project_shortname(teamforge_path):
    'convert from TeamForge to SF, and validate early'
    tf_shortname = teamforge_path.split('.')[-1]
    sf_shortname = tf_shortname.replace('_','-')

    # FIXME hardcoded translations
    sf_shortname = {
        'i1': 'motorola-i1',
        'i9': 'motorola-i9',
        'devplatformforocap': 'ocap-dev-pltfrm',
    }.get(sf_shortname, sf_shortname)

    if not 3 <= len(sf_shortname) <= 15:
        raise ValueError('Project name length must be between 3 & 15, inclusive: %s (%s)' %
                         (sf_shortname, len(sf_shortname)))
    return sf_shortname


# FIXME hardcoded
skip_perms_usernames = set([
    'faisal_saeed','dsarkisian','debonairamit','nishanthiremath','Bhuvnesh','bluetooth','cnkurzke','makow2','jannes1','Joel_Hegberg','Farroc','brian_chen','eirikur',
    'dmitry_flyorov','bipingm','MornayJo','ibv','b_weisshaar','k9srb','johnmmills','a_gomolitsky','filim','kapoor','ljzegers','jrukes','dwilson9','jlin','quickie',
    'johnbell','nnikolenko','Gaetan','Giannetta','Katia','jackhan','jacobwangus','adwankar','dinobrusco','qbarnes','ilmojung','clifford_chan','nbaig','fhutchi1',
    'rinofarina','baiyanbin','muralidhar','duanyiruo','bredding','mkolkey','manvith','nanduk','engyihan','deepsie','dabon','dino_jiang','mattrose','peter_j_wilhelm',
    'emx2500','jmcguire','lfilimowski','guruppandit','abhilashisme','edwinhm','rabbi','ferrans','guna','kevin_robinson','adathiruthi','kochen','onehap','kalanithi',
    'jamesn','obu001','chetanv','Avinash','HugoBoss','Han_Wei','mhooper','g16872','mfcarignano','jim_burke','kevin','arunkarra','adam_feng','pavan_scm','kostya_katz',
    'ppazderka','eileenzhuang','pyammine','judyho','ashoykh','rdemento','ibrahim','min_wang','arvind_setlur','moorthy_karthik','daniel_nelson','dms','esnmurthy',
    'rasa_bonyadlou','prashantjoshi','edkeating','billsaez','cambalindo','jims','bozkoyun','andry_deltsov','bpowers','manuel_milli','maryparsons','spriporov','yutianli',
    'xiebin','tnemeth1','udayaps','zzzzuser','timberger','sbarve1','zarman','rwallace67','thangavelu_arum','yuhuaixie','tingup','sekchai','sasanplus','rupal','sebastien_hertz',
    'sab8123','rony_lim','slava_kirillin','smwest','wendydu_yq','sco002','RonFred','spatnala','vd','Sunny','tthompson','sunijams','slaw','rodovich','zhangqingqi82','venki',
    'yuntaom','xiaojin','walterciocosta','straus','Thomas','stupka','wangyu','yaowang','wisekb','tyler_louie','smartgarfield','shekar_mahalingam',
    'venkata_akella','v_yellapragada','vavasthi','rpatel','zhengfang','sweetybala','vap','sergey','ymhuang','spatel78745'
])

def create_project(pid, nbhd):
    M.session.artifact_orm_session._get().skip_mod_date = True
    data = loadjson(pid, pid+'.json')
    #pprint(data)
    log.info('Loading: %s %s %s' % (pid, data.data.title, data.data.path))
    shortname = convert_project_shortname(data.data.path)

    project = M.Project.query.get(shortname=shortname)
    if not project:
        private = (data.access_level == 'private')
        log.debug('Creating %s private=%s' % (shortname, private))
        project = nbhd.register_project(shortname,
                                        get_user(data.data.createdBy),
                                        private_project=private)
    project.name = data.data.title
    project.short_description = data.data.description
    project.last_updated = datetime.strptime(data.data.lastModifiedDate, '%Y-%m-%d %H:%M:%S')
    # TODO: push last_updated to gutenberg?
    # TODO: try to set createdDate?

    role_admin = M.ProjectRole.by_name('Admin', project)
    admin_usernames = set()
    for admin in data.admins:
        if admin.userName in skip_perms_usernames:
            continue
        admin_usernames.add(admin.userName)
        user = get_user(admin.userName)
        c.user = user
        pr = user.project_role(project)
        pr.roles = [ role_admin._id ]
        ThreadLocalORMSession.flush_all()
    role_developer = M.ProjectRole.by_name('Developer', project)
    for member in data.members:
        if member.userName in skip_perms_usernames:
            continue
        if member.userName in admin_usernames:
            continue
        user = get_user(member.userName)
        pr = user.project_role(project)
        pr.roles = [ role_developer._id ]
        ThreadLocalORMSession.flush_all()
    project.labels = [cat.path.lstrip('projects/categorization.root.') for cat in data.categories]
    ThreadLocalORMSession.flush_all()

    if not project.app_instance('downloads'):
        project.install_app('Downloads', 'downloads')

    dirs = os.listdir(os.path.join(options.output_dir, pid))
    if 'wiki' in dirs:
        import_wiki(project,pid)
    if 'forum' in dirs:
        import_discussion(project,pid)
    if 'news' in dirs:
        import_news(project,pid)

    # TODO: categories as labels

    ThreadLocalORMSession.flush_all()
    return project

def import_wiki(project, pid):
    from forgewiki import model as WM
    pages = os.listdir(os.path.join(options.output_dir, pid, 'wiki'))
    # handle the homepage content
    if 'homepage_text.markdown' in pages:
        project.description = wiki2markdown(load(pid, 'wiki', 'homepage_text.markdown'))
    if 'HomePage.json' in pages and 'HomePage.markdown' in pages:
        wiki_app = project.app_instance('wiki')
        if not wiki_app:
            wiki_app = project.install_app('Wiki', 'wiki')
        h.set_context(project.shortname, 'wiki')
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
                    globals = WM.Globals.query.get(app_config_id=wiki_app.config._id)
                    if globals is not None:
                        globals.root = page_data.title
                    else:
                        globals = WM.Globals(app_config_id=wiki_app.config._id, root=page_data.title)
                p = WM.Page.upsert(page_data.title)
                p.viewable_by = ['all']
                p.text = wiki2markdown(content)
                # upload attachments
                if beginning in pages:
                    files = os.listdir(os.path.join(options.output_dir, pid, 'wiki', beginning))
                    for f in files:
                        with open(os.path.join(options.output_dir, pid, 'wiki', beginning, f)) as fp:
                            p.attach(f, fp, content_type=utils.guess_mime_type(f))
                if not p.history().first():
                    p.commit()
    ThreadLocalORMSession.flush_all()

def import_discussion(project, pid):
    from forgediscussion import model as DM
    discuss_app = project.app_instance('discussion')
    if not discuss_app:
        discuss_app = project.install_app('Discussion', 'discussion')
    h.set_context(project.shortname, 'discussion')
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
    DM.Forum.query.remove(dict(app_config_id=discuss_app.config._id,shortname='general'))
    forums = os.listdir(os.path.join(options.output_dir, pid, 'forum'))
    for forum in forums:
        ending = forum[-5:]
        forum_name = forum[:-5]
        if '.json' == ending and forum_name in forums:
            forum_data = loadjson(pid, 'forum', forum)
            fo = DM.Forum.query.get(shortname=forum_name, app_config_id=discuss_app.config._id)
            if not fo:
                fo = DM.Forum(app_config_id=discuss_app.config._id, shortname=forum_name)
            fo.name = forum_data.title
            fo.description = forum_data.description
            fo_num_topics = 0
            fo_num_posts = 0
            topics = os.listdir(os.path.join(options.output_dir, pid, 'forum', forum_name))
            for topic in topics:
                ending = topic[-5:]
                topic_name = topic[:-5]
                if '.json' == ending and topic_name in topics:
                    fo_num_topics += 1
                    topic_data = loadjson(pid, 'forum', forum_name, topic)
                    to = DM.ForumThread.query.get(
                        subject=topic_data.title,
                        discussion_id=fo._id,
                        app_config_id=discuss_app.config._id)
                    if not to:
                        to = DM.ForumThread(
                            subject=topic_data.title,
                            discussion_id=fo._id,
                            app_config_id=discuss_app.config._id)
                    to_num_replies = 0
                    oldest_post = None
                    newest_post = None
                    posts = sorted(os.listdir(os.path.join(options.output_dir, pid, 'forum', forum_name, topic_name)))
                    for post in posts:
                        ending = post[-5:]
                        post_name = post[:-5]
                        if '.json' == ending:
                            to_num_replies += 1
                            post_data = loadjson(pid, 'forum', forum_name, topic_name, post)
                            p = DM.ForumPost.query.get(
                                _id='%s%s@import' % (post_name,str(discuss_app.config._id)),
                                thread_id=to._id,
                                discussion_id=fo._id,
                                app_config_id=discuss_app.config._id)
                            if not p:
                                p = DM.ForumPost(
                                    _id='%s%s@import' % (post_name,str(discuss_app.config._id)),
                                    thread_id=to._id,
                                    discussion_id=fo._id,
                                    app_config_id=discuss_app.config._id)
                            create_date = datetime.strptime(post_data.createdDate, '%Y-%m-%d %H:%M:%S')
                            p.timestamp = create_date
                            p.author_id = str(get_user(post_data.createdByUserName)._id)
                            p.text = post_data.content
                            p.status = 'ok'
                            if post_data.replyToId:
                                p.parent_id = '%s%s@import' % (post_data.replyToId,str(discuss_app.config._id))
                            slug, full_slug = p.make_slugs(parent = p.parent, timestamp = create_date)
                            p.slug = slug
                            p.full_slug = full_slug
                            if oldest_post == None or oldest_post.timestamp > create_date:
                                oldest_post = p
                            if newest_post == None or newest_post.timestamp < create_date:
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

def import_news(project, pid):
    from forgeblog import model as BM
    posts = os.listdir(os.path.join(options.output_dir, pid, 'news'))
    if len(posts):
        news_app = project.app_instance('news')
        if not news_app:
            news_app = project.install_app('blog', 'news', mount_label='News')
        h.set_context(project.shortname, 'news')
        # make all the blog posts
        for post in posts:
            if '.json' == post[-5:]:
                post_data = loadjson(pid, 'news', post)
                p = BM.BlogPost.query.get(title=post_data.title,app_config_id=news_app.config._id)
                if not p:
                    p = BM.BlogPost(title=post_data.title,app_config_id=news_app.config._id)
                p.text = post_data.body
                create_date = datetime.strptime(post_data.createdOn, '%Y-%m-%d %H:%M:%S')
                p.timestamp = create_date
                p.mod_date = create_date
                p.state = 'published'
                if not p.slug:
                    p.make_slug()
                if not p.history().first():
                    p.commit()
                    ThreadLocalORMSession.flush_all()
                    M.Thread(discussion_id=p.app_config.discussion_id,
                           ref_id=p.index_id(),
                           subject='%s discussion' % p.title)
                user = get_user(post_data.createdByUsername)
                p.history().first().author=dict(
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
        log.warn('Migrating documents is not supported, but found %s docs' % doc_count)

    scm = make_client(options.api_url, 'ScmApp')
    for repo in scm.service.getRepositoryList(s, project.id).dataRows:
        log.warn('Migrating SCM repos is not supported, but found %s' % repo.repositoryPath)

    tasks = make_client(options.api_url, 'TaskApp')
    task_count = len(tasks.service.getTaskList(s, project.id, filters=None).dataRows)
    if task_count:
        log.warn('Migrating tasks is not supported, but found %s tasks' % task_count)

    tracker = make_client(options.api_url, 'TrackerApp')
    tracker_count = len(tracker.service.getArtifactList(s, project.id, filters=None).dataRows)
    if tracker_count:
        log.warn('Migrating trackers is not supported, but found %s tracker artifacts' % task_count)


def load(project_id, *paths):
    in_file = os.path.join(options.output_dir, project_id, *paths)
    with open(in_file) as input:
        content = input.read()
    return content

def loadjson(*args):
    # Object for attribute access
    return json.loads(load(*args), object_hook=Object)

def save(content, project, *paths):
    out_file = os.path.join(options.output_dir, project.id, *paths)
    if not os.path.exists(os.path.dirname(out_file)):
        os.makedirs(os.path.dirname(out_file))
    with open(out_file, 'w') as out:
        out.write(content)

class StatusCheckingURLopener(FancyURLopener):
  def http_error_default(self, url, fp, errcode, errmsg, headers):
        raise Exception(errcode)
statusCheckingURLopener = StatusCheckingURLopener()

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

    hostname = urlparse(options.api_url).hostname
    scheme = urlparse(options.api_url).scheme
    url = scheme + '://' + hostname + action_url + url_path
    log.debug('fetching %s' % url)
    statusCheckingURLopener.retrieve(url, out_file)
    return out_file

bracket_macro = re.compile(r'\[(.*?)\]')
h1 = re.compile(r'^!!!', re.MULTILINE)
h2 = re.compile(r'^!!', re.MULTILINE)
h3 = re.compile(r'^!', re.MULTILINE)
def wiki2markdown(markup):
    '''
    Partial implementation of http://help.collab.net/index.jsp?topic=/teamforge520/reference/wiki-wikisyntax.html
    '''
    def bracket_handler(matchobj):
        snippet = matchobj.group(1)
        # TODO: support [foo|bar.jpg]
        if snippet.startswith('sf:'):
            # can't handle these macros
            return matchobj.group(0)
        elif snippet.endswith('.jpg') or snippet.endswith('.gif') or snippet.endswith('.png'):
            filename = snippet.split('/')[-1]
            return '[[img src=%s]]' % filename
        elif '|' in snippet:
            text, link = snippet.split('|', 1)
            return '[%s](%s)' % (text, link)
        else:
            # regular link
            return '<%s>' % snippet
    markup = bracket_macro.sub(bracket_handler, markup)
    markup = h1.sub('#', markup)
    markup = h2.sub('##', markup)
    markup = h3.sub('###', markup)
    return markup

def find_image_references(markup):
    'yields filenames'
    for matchobj in bracket_macro.finditer(markup):
        snippet = matchobj.group(1)
        if snippet.endswith('.jpg') or snippet.endswith('.gif') or snippet.endswith('.png'):
            yield snippet

def get_news(project):
    '''
    Extracts news posts
    '''
    global users
    app = make_client(options.api_url, 'NewsApp')

    # find the forums
    posts = app.service.getNewsPostList(s, project.id)
    for post in posts.dataRows:
        save(json.dumps(dict(post), default=str), project, 'news', post.id+'.json')
        users.add(post.createdByUsername)

def get_discussion(project):
    '''
    Extracts discussion forums and posts
    '''
    global users
    app = make_client(options.api_url, 'DiscussionApp')

    # find the forums
    forums = app.service.getForumList(s, project.id)
    for forum in forums.dataRows:
        forumname = forum.path.split('.')[-1]
        log.info('Retrieving data for forum: %s' % forumname)
        save(json.dumps(dict(forum), default=str), project, 'forum', forumname+'.json')
        # topic in this forum
        topics = app.service.getTopicList(s, forum.id)
        for topic in topics.dataRows:
            save(json.dumps(dict(topic), default=str), project, 'forum', forumname, topic.id+'.json')
            # posts in this topic
            posts = app.service.getPostList(s, topic.id)
            for post in posts.dataRows:
                save(json.dumps(dict(post), default=str), project, 'forum', forumname, topic.id, post.id+'.json')
                users.add(post.createdByUserName)


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
        save(json.dumps(dict(wiki_page), default=str), project, 'wiki', pagename+'.json')
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
            download_file('wiki', project.path + '/wiki/' + img_ref, project.id, 'wiki', 'homepage', filename)

    for path, text in pages.iteritems():
        if options.default_wiki_text in text:
            log.debug('skipping default wiki page %s' % path)
        else:
            save(text, project, 'wiki', path+'.markdown')
            for img_ref in find_image_references(text):
                filename = img_ref.split('/')[-1]
                download_file('wiki', project.path + '/wiki/' + img_ref, project.id, 'wiki', path, filename)

def _dir_sql(created_on, project, dir_name, rel_path):
    if not rel_path:
        parent_directory = "'1'"
    else:
        parent_directory = "(SELECT pfs_path FROM pfs_path WHERE path_name = '%s/')" % rel_path
    sql = """
    UPDATE pfs
      SET file_crtime = '%s'
      WHERE source_pk = (SELECT project.project FROM project WHERE project.project_name = '%s')
      AND source_table = 'project'
      AND pfs_type = 'd'
      AND pfs_name = '%s'
      AND parent_directory = %s;
    """ % (created_on, convert_project_shortname(project.path), dir_name, parent_directory)
    return sql

def get_files(project):
    frs = make_client(options.api_url, 'FrsApp')
    valid_pfs_filename = re.compile(r'(?![. ])[-_ +.,=#~@!()\[\]a-zA-Z0-9]+(?<! )$')
    pfs_output_dir = os.path.join(os.path.abspath(options.output_dir), 'PFS', convert_project_shortname(project.path))
    sql_updates = ''

    def handle_path(obj, prev_path):
        path_component = obj.title.strip().replace('/', ' ').replace('&','').replace(':','')
        path = os.path.join(prev_path, path_component)
        if not valid_pfs_filename.match(path_component):
            log.error('Invalid filename: "%s"' % path)
        save(json.dumps(dict(obj), default=str),
            project, 'frs', path+'.json')
        return path

    for pkg in frs.service.getPackageList(s, project.id).dataRows:
        pkg_path = handle_path(pkg, '')
        pkg_details = frs.service.getPackageData(s, pkg.id) # download count
        save(json.dumps(dict(pkg_details), default=str),
             project, 'frs', pkg_path+'_details.json')

        for rel in frs.service.getReleaseList(s, pkg.id).dataRows:
            rel_path = handle_path(rel, pkg_path)
            rel_details = frs.service.getReleaseData(s, rel.id) # download count
            save(json.dumps(dict(rel_details), default=str),
                 project, 'frs', rel_path+'_details.json')

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
                     file_path+'.json'
                     )
                if not options.skip_frs_download:
                    download_file('frs', rel.path + '/' + file.id, pfs_output_dir, file_path)
                    mtime = int(mktime(details.lastModifiedDate.timetuple()))
                    os.utime(os.path.join(pfs_output_dir, file_path), (mtime, mtime))

            # releases
            created_on = int(mktime(rel.createdOn.timetuple()))
            mtime = int(mktime(rel.lastModifiedOn.timetuple()))
            if not options.skip_frs_download:
                os.utime(os.path.join(pfs_output_dir, rel_path), (mtime, mtime))
            sql_updates += _dir_sql(created_on, project, rel.title.strip(), pkg_path)
        # packages
        created_on = int(mktime(pkg.createdOn.timetuple()))
        mtime = int(mktime(pkg.lastModifiedOn.timetuple()))
        if not options.skip_frs_download:
            os.utime(os.path.join(pfs_output_dir, pkg_path), (mtime, mtime))
        sql_updates += _dir_sql(created_on, project, pkg.title.strip(), '')
    # save pfs update sql for this project
    with open(os.path.join(options.output_dir, 'pfs_updates.sql'), 'a') as out:
        out.write('/* %s */' % project.id)
        out.write(sql_updates)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARN)
    log.setLevel(logging.DEBUG)
    main()


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
    assert '\n# Project Statistics' in new_markup
    assert '<http://www.google.com>' in new_markup
    assert '[SourceForge ](http://www.sf.net)' in new_markup
    assert '[sf:frsStatistics]' in new_markup
