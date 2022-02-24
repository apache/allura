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


import six
from six.moves.urllib.parse import unquote
from webob import exc

from tg import expose, request, redirect
from ming.utils import LazyProperty

from allura.lib.security import require_access
from allura.lib.utils import is_ajax
from allura import model as M
from .base import BaseController


# text/html, script, flash, image/svg+xml, etc are NOT secure to display directly in the browser
SAFE_CONTENT_TYPES = (
    'image/png', 'image/x-png',
    'image/jpeg', 'image/pjpeg', 'image/jpg',
    'image/gif',
    'image/bmp',
    'image/tiff',
    'image/x-icon',
)


class AttachmentsController(BaseController):
    AttachmentControllerClass = None

    def __init__(self, artifact):
        self.artifact = artifact

    @expose()
    def _lookup(self, filename=None, *args):
        if filename:
            if not args:
                filename = request.path.rsplit('/', 1)[-1]
            filename = unquote(filename)
            return self.AttachmentControllerClass(filename, self.artifact), args
        else:
            raise exc.HTTPNotFound


class AttachmentController(BaseController):
    AttachmentClass = None
    edit_perm = 'edit'

    def _check_security(self):
        require_access(self.artifact, 'read')
        if isinstance(self.artifact, M.Post):
            status = getattr(self.artifact, 'status', None)
            if status == 'pending':
                require_access(self.artifact, 'moderate')

    def __init__(self, filename, artifact):
        self.filename = filename
        self.artifact = artifact

    @property
    def attachments_query(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata['type'] = 'attachment'
        return dict(filename=self.filename, **metadata)

    @property
    def thumbnails_query(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata['type'] = 'thumbnail'
        return dict(filename=self.filename, **metadata)

    @LazyProperty
    def attachment(self):
        attachment = self.AttachmentClass.query.find(
            self.attachments_query
        ).sort('_id', -1).limit(1).first()
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    @LazyProperty
    def thumbnail(self):
        attachment = self.AttachmentClass.query.find(
            self.thumbnails_query
        ).sort('_id', -1).limit(1).first()
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    def handle_post(self, delete, **kw):
        require_access(self.artifact, self.edit_perm)
        if delete:
            # Remove all attachments with such filename. Since we're showing
            # only the most recent one we don't want previous attachments
            # with such filename (if there was any) to show up after delete
            self.AttachmentClass.query.remove(self.attachments_query)
            self.AttachmentClass.query.remove(self.thumbnails_query)

    @expose()
    def index(self, delete=False, **kw):
        if request.method == 'POST':
            self.handle_post(delete, **kw)
            if is_ajax(request):
                return
            redirect(six.ensure_text(request.referer or '/'))
        if self.artifact.deleted:
            raise exc.HTTPNotFound
        embed = False
        if self.attachment.content_type and self.attachment.content_type in SAFE_CONTENT_TYPES:
            embed = True
        return self.attachment.serve(embed=embed)

    @expose()
    def thumb(self, **kwargs):
        if self.artifact.deleted:
            raise exc.HTTPNotFound
        return self.thumbnail.serve(embed=True)
