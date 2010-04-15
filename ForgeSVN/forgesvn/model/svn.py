from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty

from pyforge.model import Repository

class SVNRepository(Repository):
    class __mongometa__:
        name='svn-repository'

    def index(self):
        result = Repository.index(self)
        result.update(
            type_s='SVNRepository')
        return result

MappedClass.compile_all()
