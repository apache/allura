from urllib import unquote
from webob import exc

from tg import expose, request, response, redirect
from ming.utils import LazyProperty

from allura.lib.security import require, has_artifact_access
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
        require(has_artifact_access('read', self.artifact))

    def __init__(self, filename, artifact):
        self.filename = filename
        self.artifact = artifact

    @LazyProperty
    def attachment(self):
        metadata = self.AttachmentClass.metadata_for(self.artifact)
        metadata_query = dict(
            ('metadata.%s' % k, v)
            for k, v in metadata.iteritems())
        attachment = self.AttachmentClass.query.get(filename=self.filename, **metadata_query)
        if attachment is None:
            attachment = self.AttachmentClass.by_metadata(filename=self.filename, **metadata).first()
        if attachment is None:
            raise exc.HTTPNotFound
        return attachment

    @LazyProperty
    def thumbnail(self):
        thumbnail = self.AttachmentClass.by_metadata(filename=self.attachment.filename).first()
        if thumbnail is None:
            raise exc.HTTPNotFound
        return thumbnail
        
    @expose()
    def index(self, delete=False, embed=True, **kw):
        if request.method == 'POST':
            require(has_artifact_access(self.edit_perm, self.artifact))
            if delete:
                self.attachment.delete()
                try:
                    if self.thumbnail:
                        self.thumbnail.delete()
                except exc.HTTPNotFound:
                    pass
            redirect(request.referer)
        with self.attachment.open() as fp:
            if fp is None:
                raise exc.HTTPNotFound()
            filename = fp.metadata['filename'].encode('utf-8')
            if fp.content_type is None:
                fp.content_type = 'application/octet-stream'
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
