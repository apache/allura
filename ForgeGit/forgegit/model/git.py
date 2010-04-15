from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.model import Repository

class GitRepository(Repository):
    class __mongometa__:
        name='git-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='GitRepository')
        return result

MappedClass.compile_all()
