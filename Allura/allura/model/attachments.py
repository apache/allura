from mimetypes import guess_type

from pylons import c
from ming.orm import FieldProperty
from ming import schema as S

from allura.lib import helpers as h

from .session import project_orm_session
from .filesystem import File

class BaseAttachment(File):
    thumbnail_size = (255, 255)

    class __mongometa__:
        name = 'attachment.files'
        session = project_orm_session
        indexes = ['metadata.filename']

    # Override the metadata schema here
    metadata=FieldProperty(dict(
            artifact_id=S.ObjectId,
            app_config_id=S.ObjectId,
            type=str,
            filename=str))

    @property
    def artifact(self):
        raise NotImplementedError, 'artifact'

    def url(self):
        return self.artifact.url() + 'attachment/' + self.filename

    def is_embedded(self):
        from pylons import request
        return self.metadata.filename in request.environ.get('allura.macro.att_embedded', [])

    @classmethod
    def metadata_for(cls, artifact):
        return dict(
            artifact_id=artifact._id,
            app_config_id=artifact.app_config_id)

    @classmethod
    def save_attachment(cls, filename, fp, **kwargs):
        content_type = kwargs.pop('content_type', None)
        if content_type is None:
            content_type = guess_type(filename)
            if content_type[0]: content_type = content_type[0]
            else: content_type = 'application/octet-stream'

        thumbnail_meta = dict(type="thumbnail", app_config_id=c.app.config._id)
        thumbnail_meta.update(kwargs)
        original_meta = dict(type="attachment", app_config_id=c.app.config._id)
        original_meta.update(kwargs)
        # Try to save as image, with thumbnail
        orig, thumbnail = cls.save_image(
            filename, fp, content_type=content_type,
            square=True, thumbnail_size=cls.thumbnail_size,
            thumbnail_meta=thumbnail_meta,
            save_original=True,
            original_meta=original_meta)
        if orig is not None:
            return orig, thumbnail

        # No, generic attachment
        with cls.create(
            content_type=content_type,
            filename=filename,
            **original_meta) as fp_w:
            fp_w.write(fp.read())
        orig = cls.query.get(filename=fp_w.name)
        return orig, None

