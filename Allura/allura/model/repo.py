from datetime import datetime

from ming import Document, Field
from ming import schema as S

from .session import main_doc_session

class Commit(Document):
    class __mongometa__:
        name = 'repo_ci'
        session = main_doc_session
        indexes = [
            ('parent_ids',),
            ('child_ids',),
            ('repo_ids',)]
    User = dict(name=str, email=str, date=datetime)

    _id = Field(str)
    tree_id = Field(str)
    committed = Field(User)
    authored = Field(User)
    message = Field(str)
    parent_ids = Field([str])
    child_ids = Field([str])
    repo_ids = Field([S.ObjectId()])

    def __repr__(self):
        return '%s %s' % (
            self._id[:7], self.summary)

    @property
    def summary(self):
        if self.message:
            summary = []
            for line in self.message.splitlines():
                line = line.rstrip()
                if line: summary.append(line)
                else: return ' '.join(summary)
            return ' '.join(summary)
        return ''

class Tree(Document):
    class __mongometa__:
        name = 'repo_tree'
        session = main_doc_session
    ObjType=S.OneOf('blob', 'tree', 'submodule')

    _id = Field(str)
    tree_ids = Field([dict(name=str, id=str)])
    blob_ids = Field([dict(name=str, id=str)])
    other_ids = Field([dict(name=str, id=str, type=ObjType)])

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

class BasicBlock(Document):
    class __mongometa__:
        name = 'repo_basic_block'
        session = main_doc_session
        indexes = [
            ('commit_ids',) ]

    _id = Field(str)
    parent_commit_ids = Field([str])
    commit_ids = Field([str])
    commit_times = Field([datetime])

    def __repr__(self):
        return '%s: (P %s, T %s..%s (%d commits))' % (
            self._id[:6],
            [ oid[:6] for oid in self.parent_commit_ids ],
            self.commit_ids[0][:6],
            self.commit_ids[-1][:6],
            len(self.commit_ids))
