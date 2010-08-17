from urllib import unquote
from webob import exc

from tg import expose, request, response, redirect
from allura.lib.security import require, has_artifact_access
from allura.controllers import BaseController

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
            return self.AttachmentControllerClass(filename), args
        else:
            raise exc.HTTPNotFound

class AttachmentController(BaseController):
    AttachmentClass = None
    edit_perm = 'edit'

    def _check_security(self):
        require(has_artifact_access('read', self.artifact))

    def __init__(self, filename):
        self.filename = filename
        self.attachment = self.AttachmentClass.query.get(filename=filename)
        if self.attachment is None:
            self.attachment = self.AttachmentClass.by_metadata(filename=filename).first()
        if self.attachment is None:
            raise exc.HTTPNotFound()
        self.thumbnail = self.AttachmentClass.by_metadata(filename=filename).first()
        self.artifact = self.attachment.artifact

    @expose()
    def index(self, delete=False, embed=True, **kw):
        if request.method == 'POST':
            require(has_artifact_access(self.edit_perm, self.artifact))
            if delete:
                self.attachment.delete()
                if self.thumbnail:
                    self.thumbnail.delete()
            redirect(request.referer)
        with self.attachment.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = fp.content_type.encode('utf-8')
            response.content_type = fp.content_type.encode('utf-8')
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename

    @expose()
    def thumb(self, embed=True):
        with self.thumbnail.open() as fp:
            filename = fp.metadata['filename'].encode('utf-8')
            response.headers['Content-Type'] = ''
            response.content_type = fp.content_type.encode('utf-8')
            if not embed:
                response.headers.add('Content-Disposition',
                                     'attachment;filename=%s' % filename)
            return fp.read()
        return self.filename
