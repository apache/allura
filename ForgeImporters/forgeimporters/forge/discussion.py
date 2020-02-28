import os
import json
from dateutil.parser import parse

from tg import tmpl_context as c
from tg import app_globals as g
from ming.orm import session, ThreadLocalORMSession

from tg import (
    expose,
    flash,
    redirect
)

from tg.decorators import (
    with_trailing_slash,
    without_trailing_slash
)

from forgeimporters.base import (
    ToolImportForm,
    ToolImportController,
    File,
    ToolImporter,
    get_importer_upload_path,
    save_importer_upload
)

from allura import model as M   
from allura.lib.decorators import require_post
from allura.lib import validators as v 
from allura.lib import helpers as h
from allura.lib.plugin import ImportIdConverter

from forgediscussion import utils, import_support
from forgediscussion import model as DM

class ForgeDiscussionImportForm(ToolImportForm):
    discussions_json = v.JsonFile(not_empty=True)


class ForgeDiscussionImportController(ToolImportController):
    import_form = ForgeDiscussionImportForm

    @with_trailing_slash
    @expose('jinja:forgeimporters.forge:templates/discussion/index.html')
    def index(self, **kw):
        return dict(importer=self.importer, target_app=self.target_app)

    @without_trailing_slash
    @expose()
    @require_post()
    def create(self, discussions_json, mount_point, mount_label, **kw):
        # TODO: delete debug output
        self.importer.clear_pending(c.project) # TODO: Delete this line
        if self.importer.enforce_limit(c.project):
            print("import 1")
            save_importer_upload(c.project, 'discussion.json', json.dumps(discussions_json))
            print("import 2")
            self.importer.post(mount_point=mount_point, mount_label=mount_label)
            print("import 3")
            flash('Discussion import has begun. Your new discussion will be available when the import is complete')
            
        else:
            print("import limit")
            flash('There are too many imports pending at this time. Please wait and try again.', 'error')
        print("import none	")

        redirect(c.project.url() + 'admin/')


class ForgeDiscussionImporter(ToolImporter):
    source = 'Allura'
    target_app_ep_names = 'discussion'
    controller = ForgeDiscussionImportController
    tool_label = 'Discussion'
    tool_description = 'Import an allura discussion.'


    def __init__(self, *args, **kwargs):
        super(ForgeDiscussionImporter, self).__init__(*args, **kwargs)


    def _load_json(self, project):
        upload_path = get_importer_upload_path(project)
        full_path = os.path.join(upload_path, 'discussion.json')
        with open(full_path) as fp:
            return json.load(fp)


    def import_tool(self, project, user, mount_point=None,
                     mount_label=None, **kw):
        
        print("import_tool")
        discussion_json = self._load_json(project)

        mount_point = mount_point or 'discussion'
        mount_label = mount_label or 'Discussion'

        app = project.install_app('discussion', mount_point, mount_label, 
			import_id={ 'source': self.source }
		)
        ThreadLocalORMSession.flush_all()

        with h.push_config(c, app=app):

            # Deleting the forums that are created by default
            self.__clear_forums(app)
           
            try:
                M.session.artifact_orm_session._get().skip_mod_date = True

                for forum_json in discussion_json['forums']:

                    print("forum_json: ", forum_json)

                    new_forum = dict(
                                    app_config_id = app.config._id,
                                    shortname=forum_json['shortname'],
                                    #discussion_id=forum_json.get('discussion_id', None),
                                    #_id=forum_json.get('_id', None),
                                    description=forum_json['description'],
                                    name=forum_json['name'],
                                    create='on',
                                    parent='',
                                    members_only=False,
                                    anon_posts=False,
                                    monitoring_email=None,
                    )

                    print("New Forum:", new_forum)

                    forum = utils.create_forum(app, new_forum=new_forum)

                    for thread_json in forum_json["threads"]:
                        thread = forum.get_discussion_thread(dict(
                                            headers=dict(Subject=thread_json['subject'])))[0]

                        #if "_id" in thread_json:
                        #    thread._id = thread_json["_id"]
                        if "import_id" in thread_json:
                            thread.import_id = thread_json["import_id"]
                        #if "discussion_id" in thread_json:
                        #    thread.discussion_id = thread_json["discussion_id"]

                        print("Thread: " + str(thread))

                        self.add_posts(thread, thread_json['posts'], app)

                    session(forum).flush(forum)
                    session(forum).expunge(forum)

                    print("Forum '%s' created" % (new_forum["shortname"]))

                M.AuditLog.log(
                    "import tool %s from exported Allura JSON" % (
                        app.config.options.mount_point,
                    ),
                    project=project,
                    user=user,
                    url=app.url,
                )

                g.post_event('project_updated')
                ThreadLocalORMSession.flush_all()
                return app
            except Exception:
                h.make_app_admin_only(app)
                raise
            finally:
                M.session.artifact_orm_session._get().skip_mod_date = False
                                     

    def __clear_forums(self, app):
      forums = app.forums
      for forum in forums:
          forum.delete()


    def get_user(self, username):
        if username is None:
            return M.User.anonymous()
        user = M.User.by_username(username)
        if not user:
            print("No user with " + str(username) +  " found! (" + str(user) + ")")
            user = M.User.anonymous()
        return user


    def annotate(self, text, user, username, label=''):
        if username and user.is_anonymous() and username != 'nobody':
            return '*Originally%s by:* %s\n\n%s' % (label, username, text)
        return text


    def add_posts(self, thread, posts, app):
        for post_json in posts:
            print("Author: ", post_json["author"])
            user = self.get_user(post_json["author"])
            print("User", user)
            with h.push_config(c, user=user, app=app):
                p = thread.add_post(
                        subject=post_json['subject'],
                        text=post_json['text'], 
                        ignore_security=True,
                )

                if "slug" in post_json.keys():
                    p.slug = post_json['slug']
                if "last_edited" in post_json and post_json["last_edited"] != None:
                    print("Last edited: " + str(post_json["last_edited"]))
                    p.last_edit_date = parse(post_json["last_edited"])
                if "timestamp" in post_json:
                    p.timestamp = parse(post_json["timestamp"])

                try:
                    p.add_multiple_attachments([File(a['url'])
                                                for a in post_json['attachments']])
                except:
                    print("Could not add attachemtns to post")

