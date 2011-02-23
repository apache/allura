import logging
from collections import defaultdict
from datetime import datetime, time

import ming

from .session import main_doc_session

log = logging.getLogger(__name__)

class Stats(ming.Document):
    class __mongometa__:
        session = main_doc_session
        name='stats'

class CPA(ming.Document):
    class __mongometa__:
        session = main_doc_session
        name='content_production_activities'
        indexes = [
            'type', 'class_name', 'project_id', 'project_shortname', 'app_config_id', 'when' ]

    @classmethod
    def post(cls, type, obj):
        d = dict(
                type=type,
                class_name='%s.%s' % (
                    obj.__class__.__module__,
                    obj.__class__.__name__),
                project_id=None,
                project_shortname='',
                app_config_id=obj.app_config_id,
                tool_name='',
                mount_point='',
                when=datetime.utcnow())
        if obj.app_config:
            d.update(
                project_id=obj.app_config.project_id,
                project_shortname=obj.app_config.project.shortname,
                tool_name=obj.app_config.tool_name,
                mount_point=obj.app_config.options.mount_point)
        doc = cls.make(d)
        doc.m.insert()

    @classmethod
    def stats(cls, since=None):
        result = defaultdict(lambda:dict(create=0, modify=0, delete=0))
        if since:
            q = dict(when={'$gt':datetime.combine(since, time.min)})
        else:
            q = {}
        for doc in cls.m.find(q).sort([('tool_name', 1), ('class_name', 1)]):
            result[doc.tool_name, doc.class_name][doc.type] += 1
        result = sorted(result.iteritems())
        return [ dict(v, tool_name=k[0], class_name=k[1])
                 for k,v in result]
