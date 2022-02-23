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

''' This is the Collection module for the Files plugin.
Upload, UploadFolder & UploadFile are the collections'''

from datetime import datetime

from six.moves.urllib.parse import quote
import re
import typing

from ming import schema as S
from ming.orm import Mapper
from ming.orm import FieldProperty, ForeignIdProperty, RelationProperty
from bson import ObjectId

from tg import tmpl_context as c

from allura.model.artifact import VersionedArtifact
from allura.model.auth import AlluraUserProperty, User
from allura.model.session import project_orm_session, artifact_orm_session
from allura.model.filesystem import File
from allura.model.timeline import ActivityObject
from allura.lib import helpers as h

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


README_RE = re.compile(r'^README(\.[^.]*)?$', re.IGNORECASE)


class Upload(VersionedArtifact, ActivityObject):

    ''' The Upload collection for files. '''

    class __mongometa__:
        name = 'upload'
        session = project_orm_session

    query: 'Query[Upload]'

    type_s = 'Upload'

    _id = FieldProperty(S.ObjectId)
    filename = FieldProperty(str)
    filetype = FieldProperty(str)
    project_id = ForeignIdProperty('Project', if_missing=lambda: c.project._id)
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    project = RelationProperty('Project', via='project_id')
    file_url = None

    @classmethod
    def attachment_class(cls):
        return UploadFiles

    @property
    def activity_name(self):
        return self.filename

    @property
    def activity_url(self):
        return self.file_url


class UploadFolder(VersionedArtifact, ActivityObject):

    ''' The UploadFolder collection is for the Folders. Every folder is an object of this class.'''

    class __mongometa__:
        name = 'upload_folder'
        session = project_orm_session

    query: 'Query[UploadFolder]'

    type_s = 'UploadFolder'

    _id = FieldProperty(S.ObjectId)
    folder_name = FieldProperty(str)
    project_id = ForeignIdProperty('Project', if_missing=lambda: c.project._id)
    parent_folder_id = ForeignIdProperty('UploadFolder')
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id = ForeignIdProperty('User', if_missing=lambda: c.user._id)
    parent_folder = RelationProperty('UploadFolder', via='parent_folder_id')
    project = RelationProperty('Project', via='project_id')
    path = FieldProperty(str)
    published = FieldProperty(bool, if_missing=False)
    remarks = FieldProperty(str)
    disabled = FieldProperty(bool, if_missing=False)
    folder_ids = FieldProperty([str])
    file_ids = FieldProperty([str])
    author = RelationProperty(User, via='author_id')

    def url(self):
        parent_folder = self.parent_folder
        if parent_folder:
            string = ''
            while parent_folder:
                string += parent_folder.folder_name + '/'
                parent_folder = parent_folder.parent_folder
            list_obj = string.rsplit('/')[::-1]
            string = '/'.join(list_obj)
            string = string.lstrip('/')
            url_str = c.app.url + string + '/' + self.folder_name
            self.path = string + '/' + self.folder_name
        else:
            url_str = c.app.url + self.folder_name
            self.path = self.folder_name
        return quote(url_str)

    def folder_id(self):
        return str(self._id)

    @property
    def activity_name(self):
        return self.folder_name

    @property
    def activity_url(self):
        parent_folder = self.parent_folder
        if parent_folder:
            return parent_folder.url()
        else:
            return c.app.url


class UploadFiles(File):

    '''The UploadFiles collection is for the Files. Any file which is uploaded is treated as an Upload object'''

    thumbnail_size = (255, 255)
    ArtifactType = Upload


    class __mongometa__:
        name = 'upload_files'
        session = project_orm_session
        indexes = [
            ('app_config_id', 'parent_folder_id', 'filename'),
            ('app_config_id', 'linked_to_download', 'disabled'),
            ('app_config_id', 'filename', 'path'),
        ]

        def before_save(data):
            _session = artifact_orm_session._get()
            skip_last_updated = getattr(_session, 'skip_last_updated', False)
            data['mod_date'] = datetime.utcnow()
            if c.project and not skip_last_updated:
                c.project.last_updated = datetime.utcnow()

    query: 'Query[UploadFiles]'

    artifact_id = FieldProperty(S.ObjectId)
    app_config_id = FieldProperty(S.ObjectId)
    type = FieldProperty(str)
    project_id = FieldProperty(S.ObjectId)
    parent_folder_id = ForeignIdProperty('UploadFolder')
    created_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    mod_date = FieldProperty(datetime, if_missing=datetime.utcnow)
    author_id: ObjectId = AlluraUserProperty(if_missing=lambda: c.user._id)
    parent_folder = RelationProperty('UploadFolder', via='parent_folder_id')
    linked_to_download = FieldProperty(bool, if_missing=False)
    path = FieldProperty(str)
    disabled = FieldProperty(bool, if_missing=False)
    author = RelationProperty(User, via='author_id')

    @property
    def artifact(self):

        '''Returns the Artifact object'''

        return self.ArtifactType.query.get(_id=self.artifact_id)

    def url(self):

        '''Returns the URL of the uploaded file'''

        parent_folder = self.parent_folder
        if parent_folder:
            string = ''
            while parent_folder:
                string += parent_folder.folder_name + '/'
                parent_folder = parent_folder.parent_folder
            list_obj = string.rsplit('/')[::-1]
            string = '/'.join(list_obj)
            string = string.lstrip('/')
            url_str = c.app.url + string + '/' + self.filename
            self.path = string + '/' + self.filename
        else:
            url_str = c.app.url + self.filename
            self.path = self.filename
        return quote(url_str)

    def readme(self):
        'returns (filename, unicode text) if a readme file is found'
        if README_RE.match(self.filename):
            name = self.filename
            obj_content = self.rfile().read(self.rfile().length)
            return (self.filename, h.really_unicode(obj_content))
        return None, None

    @classmethod
    def save_attachment(cls, filename, fp, content_type=None, **kwargs):
        filename = h.really_unicode(filename)
        original_meta = dict(type="project_file", app_config_id=c.app.config._id, project_id=c.project._id)
        original_meta.update(kwargs)
        fp.seek(0)
        return cls.from_stream(
            filename, fp, content_type=content_type,
            **original_meta)


Mapper.compile_all()
