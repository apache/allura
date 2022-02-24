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

'''This is the main controller module for the Files Plugin.'''

import logging
from six.moves.urllib.parse import unquote

from tg import config, redirect, expose, flash
from tg.decorators import with_trailing_slash, without_trailing_slash
from tg import tmpl_context as c, app_globals as g
from tg import request, response
from jinja2.exceptions import TemplateNotFound

from allura.app import Application
from allura.controllers import BaseController
from allura.lib.decorators import require_post
from allura.lib.widgets.subscriptions import SubscribeForm
from allura.lib.security import require_access
from allura import model as M
from allura.controllers import attachments as att
from allura import version
from allura.model.timeline import TransientActor


from bson import ObjectId
from webob import exc

# local imports ##
from forgefiles.model.files import UploadFolder, UploadFiles, Upload

log = logging.getLogger(__name__)


class FilesApp(Application):
    """Files plugin for the Allura platform"""

    __version__ = version.__version__
    tool_label = 'Files'
    tool_description = """Upload executables for your project.
        You may maintain version specific executables as well."""
    default_mount_label = 'Files'
    default_mount_point = 'files'
    uninstallable = True
    ordinal = 9
    max_instances = 1

    def __init__(self, project, config):
        Application.__init__(self, project, config)
        self.root = FilesController()

    def install(self, project):
        'Set up any default permissions and roles here'
        self.config.options['project_name'] = project.name
        super().install(project)
        role_anon = M.ProjectRole.by_name('*anonymous')._id
        self.config.acl = [
            M.ACE.allow(role_anon, 'read'),
        ]

    def uninstall(self, project):
        "Remove all the tool's artifacts from the database"
        app_config_id = {'app_config_id': c.app.config._id}
        Upload.query.remove(app_config_id)
        UploadFolder.query.remove(app_config_id)
        file_objects = UploadFiles.query.find(app_config_id).all()
        for file_object in file_objects:
            file_object.delete()
        super().uninstall(project)

    def has_linked_download(self):
        return UploadFiles.query.find({
            'app_config_id': c.app.config._id, 'linked_to_download': True, 'disabled': False}).count()


def get_parent_folders(linked_file_object=None):

    '''Returns the list of the parent folders for the current file or folder'''

    parent_folder = linked_file_object.parent_folder if linked_file_object else None
    parent_folders_list = []
    while parent_folder:
        parent_folders_list.append(str(parent_folder._id))
        parent_folder = parent_folder.parent_folder
    parent_folders_list = list(set(parent_folders_list))
    return parent_folders_list


class FilesController(BaseController):
    """Root controller for the Files Application"""

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgefiles:templates/files.html')
    def index(self):

        '''Index method for the Root controller'''

        require_access(c.app, 'read')
        folder_object = None
        file_object = None

        upload_object = Upload.query.get(app_config_id=c.app.config._id)
        self.attachment = AttachmentsController(upload_object)
        file_objects = UploadFiles.query.find({'app_config_id': c.app.config._id, 'parent_folder_id': None})
        file_objects = file_objects.sort([('created_date', -1)]).all()
        folder_objects = UploadFolder.query.find({'app_config_id': c.app.config._id, 'parent_folder_id': None})
        folder_objects = folder_objects.sort([('created_date', -1)]).all()
        if c.user in c.project.admins():
            M.Mailbox.subscribe(type='direct')
        c.subscribe_form = SubscribeForm(thing='files')
        tool_subscribed = M.Mailbox.subscribed()
        if tool_subscribed:
            subscribed = M.Mailbox.subscribed()
        else:
            subscribed = False
        file_object = UploadFiles.query.get(app_config_id=c.app.config._id, linked_to_download=True)
        parents = get_parent_folders(linked_file_object=file_object)
        return dict(file_objects=file_objects,
                    folder_objects=folder_objects, folder_object=folder_object, file_object=file_object,
                    subscribed=subscribed, parents=parents)

    def get_parent_folder_url(self, parent_folder_id):

        ''' Returns the url,parent_folder and id of parent_folder object if object is there'''

        if (parent_folder_id == 'None') or (not parent_folder_id):
            parent_folder_id = None
            parent_folder = None
            url = c.app.url
        else:
            parent_folder = UploadFolder.query.get(_id=ObjectId(parent_folder_id), app_config_id=c.app.config._id)
            parent_folder_id = ObjectId(parent_folder._id)
            url = parent_folder.url()
        return parent_folder_id, parent_folder, url

    @require_post()
    @expose()
    def create_folder(self, parent_folder_id=None, folder_name=None):

        '''Controller method for creating a folder. The folder is stored in UploadFolder collection'''

        require_access(c.app, 'create')
        parent_folder_id, parent_folder, url = self.get_parent_folder_url(parent_folder_id)
        if folder_name:
            folder_object = UploadFolder.query.find({
                'app_config_id': c.app.config._id, 'folder_name': folder_name,
                'parent_folder_id': parent_folder_id}).first()
            if folder_object:
                flash('Folder with the same name already exists!')
            else:
                folder_object = UploadFolder(folder_name=folder_name)
                folder_object.parent_folder_id = parent_folder_id
                parent = parent_folder
                while parent:
                    parent.folder_ids.append(str(folder_object._id))
                    parent = parent.parent_folder
                flash('Folder is created successfully')
                g.director.create_activity(c.user, 'created', folder_object, related_nodes=[c.project])
        else:
            flash('Folder is not created successfully')
        return redirect(url)

    @require_post()
    @expose()
    def upload_file(self, parent_folder_id=None, file_upload=None, filename=None):

        '''Controller method for creating a folder. The folder is stored in UploadFolder collection'''

        require_access(c.app, 'create')
        parent_folder_id, parent_folder, url = self.get_parent_folder_url(parent_folder_id)
        if file_upload is not None:
            file_object = UploadFiles.query.find({
                'app_config_id': c.app.config._id, 'filename': filename,
                'parent_folder_id': parent_folder_id}).first()
            if file_object:
                flash('File with the same name already exists!')
            else:
                upload_object = Upload(
                    app_config_id=c.app.config._id, filename=filename, filetype=file_upload.type)
                attach_object = upload_object.attach(
                    filename, file_upload.file, parent_folder_id=parent_folder_id)
                if attach_object.parent_folder:
                    upload_object.file_url = attach_object.parent_folder.url()
                else:
                    upload_object.file_url = c.app.url
                parent = parent_folder
                while parent:
                    parent.file_ids.append(str(attach_object._id))
                    parent = parent.parent_folder
                flash('File is uploaded successfully')
                g.director.create_activity(c.user, 'uploaded', upload_object, related_nodes=[c.project])
        else:
            flash('File is not uploaded successfully')
        return redirect(url)

    @require_post()
    @expose()
    def delete_file(self, file_id=None):

        '''Controller method to delete a file'''

        file_object = UploadFiles.query.get(_id=ObjectId(file_id), app_config_id=c.app.config._id)
        upload_object = Upload.query.get(_id=file_object.artifact_id, app_config_id=c.app.config._id)
        file_name = file_object.filename
        transient_actor = TransientActor(activity_name=file_name)
        url = c.app.url
        if file_id is not None:
            require_access(upload_object, 'delete')
            self.delete_file_from_db(file_id=file_id)
            parent_folder = file_object.parent_folder
            if parent_folder:
                url = parent_folder.url()
            flash('File is successfully deleted')
            g.director.create_activity(c.user, 'deleted the file', transient_actor, related_nodes=[c.project])
        else:
            flash('File is not deleted')
        return redirect(url)

    def delete_file_from_db(self, file_id=None):

        '''Method to delete a file from db'''

        file_object = UploadFiles.query.get(_id=ObjectId(file_id), app_config_id=c.app.config._id)
        Upload.query.remove({'_id': file_object.artifact_id, 'app_config_id': c.app.config._id})
        file_object.delete()

    def delete_folder_recursively(self, folder_id):

        '''This method is called recursively to delete folder in a hierarchy'''

        sub_file_objects = UploadFiles.query.find(dict({
            'app_config_id': c.app.config._id, 'parent_folder_id': ObjectId(folder_id)})).all()
        for file_object in sub_file_objects:
            self.delete_file_from_db(file_id=file_object._id)
        sub_folder_objects = UploadFolder.query.find({
            'app_config_id': c.app.config._id, 'parent_folder_id': ObjectId(folder_id)}).all()
        for folder_object in sub_folder_objects:
            self.delete_folder_recursively(folder_object._id)
        UploadFolder.query.remove({'_id': ObjectId(folder_id), 'app_config_id': c.app.config._id})

    @without_trailing_slash
    @require_post()
    @expose('jinja:forgefiles:templates/files.html')
    def delete_folder(self, folder_id=None):

        '''Controller method to delete a folder'''

        folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
        folder_name = folder_object.folder_name
        transient_actor = TransientActor(activity_name=folder_name)
        url = c.app.url
        if folder_id is not None:
            require_access(folder_object, 'delete')
            self.delete_folder_recursively(folder_id)
            if folder_object.parent_folder:
                url = folder_object.parent_folder.url()
            flash('Folder is deleted Successfully')
            g.director.create_activity(c.user, 'deleted the folder', transient_actor, related_nodes=[c.project])
        else:
            flash('Folder is not deleted')
        return redirect(url)

    @without_trailing_slash
    @require_post()
    @expose()
    def link_file(self, file_id=None, status=None):

        '''Controller method to link a file to the download button'''

        linkable_file_object = UploadFiles.query.get(_id=ObjectId(file_id), app_config_id=c.app.config._id)
        upload_object = Upload.query.get(_id=linkable_file_object.artifact_id, app_config_id=c.app.config._id)
        require_access(upload_object, 'link')
        if status == 'False':
            linkable_file_object.linked_to_download = False
        else:
            file_objects = UploadFiles.query.find({'app_config_id': c.app.config._id}).all()
            for file_object in file_objects:
                if file_object.linked_to_download:
                    file_object.linked_to_download = False
            linkable_file_object.linked_to_download = True

    @expose()
    def download_file(self, filename=None):

        '''Controller method to download a file'''

        if filename:
            request_path = request.path.split(c.app.url)[-1].rstrip('/')
            request_path = unquote(request_path)
            linked_file_object = UploadFiles.query.find({
                'app_config_id': c.app.config._id, 'filename': filename, 'path': request_path, 'disabled': False,
            }).first()
        else:
            linked_file_object = UploadFiles.query.find({
                'app_config_id': c.app.config._id, 'linked_to_download': True, 'disabled': False,
            }).first()
        if linked_file_object:
            try:
                if not c.user.is_anonymous():
                    M.Mailbox.subscribe(type='direct')
                return linked_file_object.serve(embed=False)
            except Exception as e:
                log.exception('%s error to download the file', e)
        else:
            flash('No artifact available')
        return redirect(c.app.url)

    @require_post()
    @expose()
    def edit_folder(self, folder_id=None, folder_name=None):

        '''Controller method to edit the folder name'''

        url = c.app.url
        folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
        if folder_object:
            require_access(folder_object, 'update')
            folder_object.folder_name = folder_name
            flash("Folder name edited successfully")
            if folder_object.parent_folder:
                url = folder_object.parent_folder.url()
        else:
            flash("Folder name not edited")
        redirect(url)

    @require_post()
    @expose()
    def edit_file(self, file_id=None, file_name=None):

        '''Controller method to edit the file name'''

        url = c.app.url
        file_object = UploadFiles.query.get(_id=ObjectId(file_id), app_config_id=c.app.config._id)
        upload_object = Upload.query.get(_id=file_object.artifact_id, app_config_id=c.app.config._id)
        if file_object:
            require_access(upload_object, 'update')
            upload_object.filename = file_name
            file_object.filename = file_name
            flash("File name edited successfully")
            if file_object.parent_folder:
                url = file_object.parent_folder.url()
        else:
            flash("File not edited")
        return redirect(url)

    @require_post()
    @expose()
    def publish_folder(self, folder_id=None, remarks=None):

        '''Controller which publishes the folder. It send update about the publishing of the folder.'''

        folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
        url = c.app.url
        if folder_object:
            require_access(folder_object, 'publish')
            folder_object.published = True
            folder_object.remarks = remarks
            mailbox_object = M.Mailbox.query.find({'app_config_id': c.app.config._id}).all()
            user_ids = [i.user_id for i in mailbox_object]
            admins = [i._id for i in c.project.admins()]
            user_ids += admins
            user_ids = list(set(user_ids))
            from allura.tasks import mail_tasks
            from allura.lib import helpers as h
            template_name = ''
            try:
                for i in user_ids:
                    user_object = M.User.query.get(_id=i)
                    template_name = 'forgefiles:/templates/mail.html'
                    text = g.jinja2_env.get_template(template_name).render(dict(
                        base_url=config.get('base_url'), user_object=user_object, project=c.project,
                        remarks=remarks, folder_object=folder_object, project_owner=c.user,
                        domain=config.get('domain')
                    ))
                    email_addr = user_object.get_pref('email_address')
                    if email_addr:
                        mail_tasks.sendsimplemail.post(
                            fromaddr=g.noreply,
                            reply_to=g.noreply,
                            toaddr=email_addr,
                            subject='{} - {} Release Update'.format(config.get('site_name'), c.project.name),
                            message_id=h.gen_message_id(),
                            text=text)
                if folder_object.parent_folder:
                    url = folder_object.parent_folder.url()
                flash('Successfully Published')
            except TemplateNotFound:
                log.exception('%s Template not found' % (template_name))
                log.info('Folder %s is not published successfully' % (folder_object.folder_name))
                flash('Folder is not published successfully')
        return redirect(url)

    @require_post()
    @expose()
    def disable_folder(self, folder_id=None, status=None):

        '''Controller method to disable the folder.'''

        folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
        if status == 'True':
            disable_status = True
            text = 'disabled'
        else:
            disable_status = False
            text = 'enabled'
        if folder_object:
            require_access(folder_object, 'disable')
            folder_object.disabled = disable_status
            '''Disabling Child folders & files of the current folder '''

            for child_folder_id in folder_object.folder_ids:
                child_folder_object = UploadFolder.query.get(
                    _id=ObjectId(child_folder_id), app_config_id=c.app.config._id)
                if child_folder_object:
                    child_folder_object.disabled = disable_status
            for child_file_id in folder_object.file_ids:
                child_file_object = UploadFiles.query.get(_id=ObjectId(child_file_id), app_config_id=c.app.config._id)
                if child_file_object:
                    child_file_object.disabled = disable_status
            flash('Folder %s successfully' % (text))
        else:
            flash('No folder exists')

    @require_post()
    @expose()
    def disable_file(self, file_id=None, status=None):

        '''Controller method to disable the file.'''

        file_object = UploadFiles.query.get(_id=ObjectId(file_id), app_config_id=c.app.config._id)
        upload_object = Upload.query.get(_id=file_object.artifact_id, app_config_id=c.app.config._id)
        if status == 'True':
            disable_status = True
            text = 'disabled'
        else:
            disable_status = False
            text = 'enabled'
        if file_object:
            require_access(upload_object, 'disable')
            file_object.disabled = disable_status
            flash('File %s successfully' % (text))
        else:
            flash('No file exists')

    @expose('json:')
    @require_post()
    def subscribe(self, subscribe=None, unsubscribe=None):

        '''Controller method that subscribes an user to the files plugin.'''

        if subscribe:
            M.Mailbox.subscribe(type='direct')
        elif unsubscribe:
            M.Mailbox.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(),
        }

    def get_folder_object(self, folder_id=None):
        '''Returns the folder object for input folder id'''
        folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
        return folder_object

    @expose('jinja:forgefiles:templates/create_folder.html')
    def get_parent_for_create_folder(self, folder_id=None):
        '''Returns the parent object of the input folder id'''
        folder_object = self.get_folder_object(folder_id)
        return dict(folder_object=folder_object)

    @expose('jinja:forgefiles:templates/upload_file.html')
    def get_parent_for_upload_file(self, folder_id=None):
        '''Returns the parent object of the input folder id'''
        folder_object = self.get_folder_object(folder_id)
        return dict(folder_object=folder_object)

    def get_folder_file_object(self, object_id=None):
        '''Returns corresponding file or folder object for the input id '''
        folder_object = UploadFolder.query.get(_id=ObjectId(object_id), app_config_id=c.app.config._id)
        file_object = UploadFiles.query.get(_id=ObjectId(object_id), app_config_id=c.app.config._id)
        return dict(folder_object=folder_object, file_object=file_object)

    @expose('jinja:forgefiles:templates/edit.html')
    def get_editable_object(self, object_id=None):
        '''Returns object id of the folder or file to be edited'''
        object_dict = self.get_folder_file_object(object_id)
        return object_dict

    @expose('jinja:forgefiles:templates/delete.html')
    def get_deletable_object(self, object_id=None):
        '''Returns object id of the folder or file to be deleted'''
        object_dict = self.get_folder_file_object(object_id)
        return object_dict

    @expose('jinja:forgefiles:templates/publish_folder.html')
    def get_publishable_folder(self, folder_id=None):
        '''Returns the status and folder object if the folder can be published or not'''
        linked_file_object = UploadFiles.query.get(
            app_config_id=c.app.config._id, linked_to_download=True, disabled=False)
        parent_folders = get_parent_folders(linked_file_object=linked_file_object)
        if folder_id:
            folder_object = UploadFolder.query.get(_id=ObjectId(folder_id), app_config_id=c.app.config._id)
            status = str(folder_object._id) in parent_folders
        else:
            folder_object = None
            status = False
        return dict(folder_object=folder_object, status=status)

    @expose()
    def _lookup(self, name, *remainder):
        ''' Class method which is used to call individual files controller class'''
        if not remainder:
            argument = name
        else:
            argument = remainder[-1]
        if argument == 'createFolder':
            argument = None
        return IndividualFilesController(argument), remainder


def folder_breadcrumbs(folder_object=None):
    ''' Function to create a breadcrumbs for folders '''
    list_object = folder_object.path.split('/')
    second_list = []
    length = 0
    urls = {}
    for i in list_object:
        length += len(i)
        folder_object = UploadFolder.query.get(folder_name=i)
        urls[str(i)] = str(folder_object.url())
        if length in range(1, (61-len(list_object[-1])+1)):
            second_list.append(i)
    second_list.append('...')
    second_list.append(list_object[-1])
    string = '/'.join(second_list)
    if length > 61:
        return string, urls
    else:
        return folder_object.path, urls


# handle requests for individual folder,file objects
class IndividualFilesController(BaseController):
    """Handle requests for a specific folder/file objects"""

    def __init__(self, arg):
        path = request.path.split(c.app.url)[-1].rstrip('/')
        if path == arg:
            path = arg
        path = unquote(path)
        arg = unquote(arg)
        self.folder_object = UploadFolder.query.find({
            'app_config_id': ObjectId(c.app.config._id), 'folder_name': arg, 'path': path}).first()
        self.file_object = UploadFiles.query.find({
            'app_config_id': ObjectId(c.app.config._id), 'filename': arg, 'path': path}).first()
        methods = ('create_folder', 'upload_file', 'delete_file', 'delete_folder', 'subscribe')
        if (not self.folder_object) and (not self.file_object) and (arg not in methods):
            log.exception('No Folder/File object found')
            raise exc.HTTPNotFound()
        else:
            pass

    def _check_security(self):
        require_access(c.app, 'read')

    @expose('jinja:forgefiles:templates/files.html')
    @with_trailing_slash
    def index(self):
        ''' Index method of individual folder/file objects'''
        require_access(c.app, 'read')
        folder_objects = None
        file_objects = None
        folder_path, urls = '', ''
        if self.folder_object:
            folder_objects = UploadFolder.query.find({
                'app_config_id': c.app.config._id, 'parent_folder_id': self.folder_object._id})
            folder_objects = folder_objects.sort([('created_date', -1)]).all()
            file_objects = UploadFiles.query.find({
                'app_config_id': c.app.config._id, 'parent_folder_id': self.folder_object._id})
            file_objects = file_objects.sort([('created_date', -1)]).all()
            folder_path, urls = folder_breadcrumbs(folder_object=self.folder_object)
        elif self.file_object:
            return FilesController().download_file(filename=self.file_object.filename)
        if c.user in c.project.admins():
            M.Mailbox.subscribe(type='direct')
        c.subscribe_form = SubscribeForm(thing='files')
        tool_subscribed = M.Mailbox.subscribed()
        if tool_subscribed:
            subscribed = M.Mailbox.subscribed()
        else:
            subscribed = False
        file_object = UploadFiles.query.get(app_config_id=c.app.config._id, linked_to_download=True)
        parents = get_parent_folders(linked_file_object=file_object)

        return dict(folder_objects=folder_objects,
                    file_objects=file_objects, folder_object=self.folder_object, file_object=self.file_object,
                    subscribed=subscribed, parents=parents, folder_path=folder_path, urls=urls)

    @require_post()
    @expose()
    def create_folder(self, parent_folder_id=None, folder_name=None):
        return FilesController().create_folder(parent_folder_id=parent_folder_id, folder_name=folder_name)

    @require_post()
    @expose()
    def upload_file(self, parent_folder_id=None, filename=None, file_upload=None):
        return FilesController().upload_file(
            parent_folder_id=parent_folder_id, filename=filename, file_upload=file_upload)

    @require_post()
    @expose()
    def delete_file(self, file_id=None):
        return FilesController().delete_file(file_id=file_id)

    @expose('json:')
    @require_post()
    def subscribe(self, subscribe=None, unsubscribe=None):
        if subscribe:
            M.Mailbox.subscribe(type='direct')
        elif unsubscribe:
            M.Mailbox.unsubscribe()
        return {
            'status': 'ok',
            'subscribed': M.Mailbox.subscribed(),
        }

    @expose()
    def _lookup(self, name, *remainder):
        if not remainder:
            argument = name
        else:
            argument = remainder[-1]
        return IndividualFilesController(argument), remainder


class AttachmentController(att.AttachmentController):
    AttachmentClass = UploadFiles
    edit_perm = 'update'


class AttachmentsController(att.AttachmentsController):
    AttachmentControllerClass = AttachmentController
