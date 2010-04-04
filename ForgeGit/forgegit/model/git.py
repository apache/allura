from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.model import Artifact

class Repository(Artifact):
    class __mongometa__:
        name='git-repository'

    name=FieldProperty(str)
    tool=FieldProperty(str)
    path=FieldProperty(str)
    status=FieldProperty(str)

    def url(self):
        return self.app_config.url() + self.name + '/'

    def shorthand_id(self):
        return self.name

    def index(self):
        result = Artifact.index(self)
        result.update(
            name_s=self.name,
            type_s='GitRepository')
        return result

MappedClass.compile_all()
