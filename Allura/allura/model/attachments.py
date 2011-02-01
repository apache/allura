import urllib

from pylons import c
from ming.orm import FieldProperty
from ming import schema as S

from allura.lib import helpers as h

from .session import project_orm_session
from .filesystem import File

class BaseAttachment(File):
    thumbnail_size = (255, 255)
    ArtifactType=None

    class __mongometa__:
        name = 'attachment'
        polymorphic_on = 'attachment_type'
        polymorphic_identity=None
        session = project_orm_session
        indexes = [ 'artifact_id', 'app_config_id' ]

    artifact_id=FieldProperty(S.ObjectId)
    app_config_id=FieldProperty(S.ObjectId)
    type=FieldProperty(str)
    attachment_type=FieldProperty(str)

    @property
    def artifact(self):
        return self.ArtifactType.query.get(_id=self.artifact_id)

    def url(self):
        return self.artifact.url() + 'attachment/' + urllib.quote(self.filename)

    def is_embedded(self):
        from pylons import request
        return self.filename in request.environ.get('allura.macro.att_embedded', [])

    @classmethod
    def metadata_for(cls, artifact):
        return dict(
            artifact_id=artifact._id,
            app_config_id=artifact.app_config_id)

    @classmethod
    def save_attachment(cls, filename, fp, content_type=None, **kwargs):
        thumbnail_meta = dict(type="thumbnail", app_config_id=c.app.config._id)
        thumbnail_meta.update(kwargs)
        original_meta = dict(type="attachment", app_config_id=c.app.config._id)
        original_meta.update(kwargs)
        # Try to save as image, with thumbnail
        orig, thumbnail = cls.save_image(
            filename, fp,
            content_type=content_type,
            square=True, thumbnail_size=cls.thumbnail_size,
            thumbnail_meta=thumbnail_meta,
            save_original=True,
            original_meta=original_meta)
        if orig is not None:
            return orig, thumbnail

        # No, generic attachment
        return cls.from_stream(
            filename, fp, content_type=content_type,
            **original_meta)

