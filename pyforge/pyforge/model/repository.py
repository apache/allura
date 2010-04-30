import os

from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from .artifact import Artifact

class Repository(Artifact):
    class __mongometa__:
        name='generic-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    fs_path=FieldProperty(str)
    url_path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''

    def url(self):
        return self.app_config.url()

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name)
        return result

    @property
    def full_fs_path(self):
        return os.path.join(self.fs_path, self.name)

MappedClass.compile_all()
