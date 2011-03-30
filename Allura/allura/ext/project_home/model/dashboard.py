import os
import shutil
import logging
from datetime import datetime
from contextlib import contextmanager

from tg import config
from tg.decorators import Decoration
import chardet
from tg import c, g, request
from pymongo.errors import OperationFailure

from ming import schema
from ming.orm.base import state, session, mapper
from ming.orm.mapped_class import MappedClass
from ming.orm.property import FieldProperty, RelationProperty, ForeignIdProperty

from allura.lib.helpers import push_config
from allura.model import Project, Artifact, AppConfig

log = logging.getLogger(__name__)

class PortalConfig(Artifact):
    class __mongometa__:
        name='portal_config'
    type_s = 'Project Portal Configuration'

    _id = FieldProperty(schema.ObjectId)
    user_id = ForeignIdProperty('User')
    layout_class = FieldProperty(str)
    layout = FieldProperty([
            {'name':str,
             'content':[
                    {'mount_point':str,
                     'widget_name':str }
                    ]
             }])

    @classmethod
    def current(cls):
        result = cls.query.get(user_id=c.user._id)
        if result is None:
            result = cls(user_id=c.user._id,
                         layout_class='onecol',
                         layout=[dict(name='content',
                                      content=[dict(mount_point='home',
                                                    widget_name='welcome')
                                               ])])
        return result

    def rendered_layout(self):
        return [
            dict(name=div.name,
                 content=[ render_widget(**w)
                           for w in div.content]
                 )
            for div in self.layout ]
            

    def url(self):
        return self.app_config.script_name()

    def index(self):
        return None

def render_widget(mount_point, widget_name):
    app = c.project.app_instance(mount_point)
    method = getattr(app.widget(app), widget_name)
    with push_config(c, app=app):
        result = method()
    if isinstance(result, dict):
        deco = Decoration.get(method)
        template_vars = dict((k,v) for k,v in result.iteritems())
        return deco.do_render_response(template_vars)
    return result

MappedClass.compile_all()
