import logging
from datetime import datetime

import pymongo

from ming import schema as S
from ming.orm.ormsession import ThreadLocalORMSession
from ming.orm import session, state, MappedClass
from ming.orm import FieldProperty, RelationProperty, ForeignIdProperty

from .session import ProjectSession
from .session import main_doc_session, main_orm_session
from .session import project_doc_session, project_orm_session

log = logging.getLogger(__name__)


class ImportBatch(MappedClass):
    class __mongometa__:
        name='import_batch'
        session = main_orm_session

    _id = FieldProperty(S.ObjectId)
    date = FieldProperty(datetime, if_missing=datetime.utcnow)
    user_id = ForeignIdProperty('User')
    api_key = FieldProperty(str)
    project_id = ForeignIdProperty('Project')
    app_config_id = FieldProperty(S.ObjectId, if_missing=None)
    description = FieldProperty(str, if_missing='')

    user = RelationProperty('User')
    project = RelationProperty('Project')
