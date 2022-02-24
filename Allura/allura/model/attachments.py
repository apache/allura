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

import typing

from tg import tmpl_context as c
from ming.orm import FieldProperty
from ming import schema as S

from allura.lib import helpers as h

from .session import project_orm_session
from .filesystem import File

if typing.TYPE_CHECKING:
    from ming.odm.mapper import Query


class BaseAttachment(File):
    thumbnail_size = (255, 255)
    ArtifactType = None

    class __mongometa__:
        name = 'attachment'
        polymorphic_on = 'attachment_type'
        polymorphic_identity = None
        session = project_orm_session
        indexes = ['artifact_id', 'app_config_id']

    query: 'Query[BaseAttachment]'

    artifact_id = FieldProperty(S.ObjectId)
    app_config_id = FieldProperty(S.ObjectId)
    type = FieldProperty(str)
    attachment_type = FieldProperty(str)

    @property
    def artifact(self):
        return self.ArtifactType.query.get(_id=self.artifact_id)

    def url(self):
        return self.artifact.url() + 'attachment/' + h.urlquote(self.filename)

    def is_embedded(self):
        from tg import request
        return self.filename in request.environ.get('allura.macro.att_embedded', [])

    @classmethod
    def metadata_for(cls, artifact):
        return dict(
            artifact_id=artifact._id,
            app_config_id=artifact.app_config_id)

    @classmethod
    def save_attachment(cls, filename, fp, content_type=None, **kwargs):
        filename = h.really_unicode(filename)
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
        else:
            # No, generic attachment
            # stream may have been partially consumed in a failed save_image
            # attempt
            fp.seek(0)
            return cls.from_stream(
                filename, fp, content_type=content_type,
                **original_meta)
