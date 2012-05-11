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
            filename=unquote(filename)
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
        attachment = self.AttachmentClass.query.get(filename=self.filename, **metadata)
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    @LazyProperty
    def thumbnail(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata['type'] = 'thumbnail'
        attachment = self.AttachmentClass.query.get(filename=self.filename, **metadata)
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
        return self.attachment.serve(False)

    @expose()
    def thumb(self, embed=True):
        return self.thumbnail.serve(embed)
