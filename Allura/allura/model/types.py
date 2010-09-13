import logging
import pickle
from pylons import c

from ming.base import Object
from ming import schema as S
from ming.utils import  LazyProperty

from allura.lib import helpers as h

log = logging.getLogger(__name__)

class ArtifactReference(Object):

    @LazyProperty
    def cls(self):
        try:
            return pickle.loads(str(self.artifact_type))
        except:
            log.exception('Error unpickling artifact reference class')
            return None

    @LazyProperty
    def artifact(self):
        if self.artifact_type is None: return None
        if self.cls is None: return None
        with h.push_context(self.project_id, self.mount_point):
            return self.cls.query.get(_id=self.artifact_id)

    def _exists(self):
        if self.artifact_type is None: return False
        if self.cls is None: return False
        with h.push_context(self.project_id, self.mount_point):
            return self.cls.query.get(_id=self.artifact_id)
            cls = pickle.loads(str(self.artifact_type))
            count = cls.query.find(dict(_id=self.artifact_id)).count()
            return count > 0

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
