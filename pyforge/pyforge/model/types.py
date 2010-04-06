import pickle
from pylons import c

from ming.base import Object
from ming import schema as S

from pyforge.lib import helpers as h

class ArtifactReference(Object):

    def to_artifact(self):
        if self.artifact_type is None: return None
        with h.push_context(self.project_id, self.mount_point):
            cls = pickle.loads(str(self.artifact_type))
            obj = cls.query.get(_id=self.artifact_id)
            return obj

class ArtifactReferenceType(S.Object):

    def __init__(self):
        self._base_schema = S.Object(dict(
                project_id=S.ObjectId(if_missing=self.default_project_id),
                mount_point=S.String(if_missing=self.default_mount_point),
                artifact_type=S.Binary, # pickled class
                artifact_id=S.Anything(if_missing=None)))

    def default_project_id(self):
        try:
            return c.project._id
        except AttributeError:
            return None

    def default_mount_point(self):
        try:
            return c.app.config.options.mount_point
        except AttributeError:
            return None

    def validate(self, value, **kw):
        result = self._base_schema.validate(value)
        if result.get('artifact_type') is None:
            return dict(project_id=None,
                        mount_point=None,
                        artifact_type=None,
                        artifact_id=None)
        return ArtifactReference(result)
