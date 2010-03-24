from ming import Document, Field
from ming import schema as S
from ming import Session

class MigrationInfo(Document):
    class __mongometa__:
        name='_flyway_migration_info'
        session = Session()
    _id = Field(S.ObjectId)
    versions = Field({str:int})
