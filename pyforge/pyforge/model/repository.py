from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from .artifact import Artifact

class Repository(Artifact):
    class __mongometa__:
        name='generic-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    path=FieldProperty(str)
    status=FieldProperty(str)
    email_address=''

    def url(self):
        return self.app_config.url() + self.name + '/'

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name)
        return result

MappedClass.compile_all()
