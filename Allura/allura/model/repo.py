from datetime import datetime

from ming import Document, Field
from ming import schema as S

from .session import main_doc_session

class Commit(Document):
    class __mongometa__:
        name = 'repo_ci'
        session = main_doc_session
        indexes = ('parent_ids')
    User = dict(name=str, email=str, date=datetime)

    _id = Field(str)
    tree_id = Field(str)
    committed = Field(User)
    authored = Field(User)
    message = Field(str)
    parent_ids = Field([str])
    child_ids = Field([str])

class Tree(Document):
    class __mongometa__:
        name = 'repo_tree'
        session = main_doc_session
    ObjType=S.OneOf('blob', 'tree', 'submodule')

    _id = Field(str)
    tree_ids = Field([dict(name=str, id=str)])
    blob_ids = Field([dict(name=str, id=str)])
    other_ids = Field([dict(name=str, id=str, type=str)])

class Trees(Document):
    class __mongometa__:
        name = 'repo_trees'
        session = main_doc_session

    _id = Field(str) # commit ID
    tree_ids = Field([str]) # tree IDs

class DiffInfo(Document):
    class __mongometa__:
        name = 'repo_diffinfo'
        session = main_doc_session

    _id = Field(str)
    differences = Field([dict(name=str, lhs_id=str, rhs_id=str)])
