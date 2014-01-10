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

from urllib import unquote
from webob import exc

from tg import expose, request, response, redirect
from ming.utils import LazyProperty

from allura.lib.security import require, has_access, require_access
from .base import BaseController


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

    def __init__(self, filename, artifact):
        self.filename = filename
        self.artifact = artifact

    @LazyProperty
    def attachment(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata['type'] = 'attachment'
        attachment = self.AttachmentClass.query.get(
            filename=self.filename, **metadata)
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    @LazyProperty
    def thumbnail(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata['type'] = 'thumbnail'
        attachment = self.AttachmentClass.query.get(
            filename=self.filename, **metadata)
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    @expose()
    def index(self, delete=False, **kw):
        if request.method == 'POST':
            require_access(self.artifact, self.edit_perm)
            if delete:
                self.attachment.delete()
                try:
                    if self.thumbnail:
                        self.thumbnail.delete()
                except exc.HTTPNotFound:
                    pass
            redirect(request.referer)
        embed = False
        if self.attachment.content_type and self.attachment.content_type.startswith('image/'):
            embed = True
        return self.attachment.serve(embed=embed)

    @expose()
    def thumb(self):
        return self.thumbnail.serve(embed=True)
