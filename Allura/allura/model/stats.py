import logging

import ming

from .session import main_doc_session

log = logging.getLogger(__name__)

class Stats(ming.Document):
    class __mongometa__:
        session = main_doc_session
        name='stats'

