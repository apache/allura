from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.model import Repository

class HgRepository(Repository):
    class __mongometa__:
        name='hg-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='HgRepository')
        return result

MappedClass.compile_all()
