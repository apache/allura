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
                project_id=S.ObjectId(if_missing=lambda:c.project._id),
                mount_point=S.String(if_missing=lambda:c.app.config.options.mount_point),
                artifact_type=S.Binary, # pickled class
                artifact_id=S.Anything(if_missing=None)))

    def validate(self, value, **kw):
        result = self._base_schema.validate(value)
        if result.get('artifact_type') is None:
            return dict(project_id=None,
                        mount_point=None,
                        artifact_type=None,
                        artifact_id=None)
        return ArtifactReference(result)
