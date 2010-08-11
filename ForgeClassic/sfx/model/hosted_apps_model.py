import json
from itertools import groupby

from pylons import c
import sqlalchemy as sa

from .sfx_model import tables as T

class HostedApp(object):
    _apps = None
    _app_index = {}

    def __init__(self, **kw):
        for k,v in kw.iteritems():
            setattr(self, k, v)

    @classmethod
    def all(cls):
        if cls._apps: return cls._apps
        metadata_types = [
            'application_url',
            'application_admin_url',
            'application_docs_url',
            'application_function',
            'application_desc',
            'application_rss_url' ]
        from_obj  = T.feature_grouping.join(
            T.sys_type_description,
            sa.and_(
                T.sys_type_description.c.type_table_name=='feature_grouping',
                T.sys_type_description.c.type_column_name=='feature_type',
                T.sys_type_description.c.type_value==T.feature_grouping.c.feature_type))
        from_obj = from_obj.join(
            T.object_metadata,
            sa.and_(
                T.feature_grouping.c.feature_grouping==T.object_metadata.c.target_pk,
                T.object_metadata.c.metadata_type.in_(metadata_types)))
        q = sa.select([
                T.feature_grouping.c.feature_type,
                T.sys_type_description.c.type_description,
                T.object_metadata.c.metadata_type,
                T.object_metadata.c.metadata_value],
                      order_by=[T.feature_grouping.c.feature_type],
                      from_obj=from_obj)
        cls._apps = []
        for (ftype, descr), subiter in groupby(q.execute(), lambda row:row[0:2]):
            kwargs = dict(
                feature_type=ftype,
                application_url=None,
                application_admin_url=None,
                application_docs_url=None,
                application_function=None,
                application_desc=None,
                application_rss_url=None,
                description=descr)
            for row in subiter:
                kwargs[row[T.object_metadata.c.metadata_type]] = \
                    row[T.object_metadata.c.metadata_value]
            cls._apps.append(cls(**kwargs))
        cls._app_index = dict((ha.feature_type, ha) for ha in cls._apps)
        return cls._apps

    def __repr__(self):
        return '<HostedApp %s>' % self.feature_type

    @classmethod
    def enabled_features(cls, project=None):
        if project is None: project = c.project
        q = sa.select(
            [ T.feature_optin.c.feature_type ],
            whereclause=sa.and_(
                T.feature_optin.c.owner_table=='project',
                T.feature_optin.c.owner_pk==project.get_tool_data('sfx', 'group_id')))
        return [r[0] for r in q.execute() ]

    @classmethod
    def get(cls, feature_type, *args):
        cls.all()
        return cls._app_index.get(feature_type, *args)

    def format_column(self, colname):
        value = getattr(self, colname)
        value = value.replace('APPTYPE', 'apps')
        value = value.replace('INSTANCE', c.project.get_tool_data('sfx', 'unix_group_name'))
        return value

    def enable(self, user=None, project=None):
        if user is None: user = c.user
        if project is None: project = c.project
        self._queue_ha_operation('hostedapp_create', user, project)

    def disable(self, user=None, project=None):
        if user is None: user = c.user
        if project is None: project = c.project
        self._queue_ha_operation('hostedapp_disable', user, project)

    def addperm(self, user=None, project=None):
        if user is None: user = c.user
        if project is None: project = c.project
        self._queue_ha_operation('hostedapp_addperm', user, project,
                                 target_table='user',
                                 target_pk=c.user.get_tool_data('sfx', 'userid'))

    def _queue_ha_operation(self, op, user, project, **kw):
        op_detail = json.dumps(dict(
                kw,
                hostedapp_name=self.feature_type))
        stmt = T.backend_queue.insert(
            time_submitted=sa.func.UNIX_TIMESTAMP(),
            time_performed=0,
            submitter_table='user',
            submitter_pk=c.user.get_tool_data('sfx', 'userid'),
            target_table='project',
            target_pk=project.get_tool_data('sfx', 'group_id'),
            operation_type=op,
            operation_detail=op_detail,
            operation_status_type='pending',
            operation_status_detail='')
        stmt = T.feature_optin.insert()
        stmt.execute(
            feature_type=self.feature_type,
            owner_table='project',
            owner_pk=project.get_tool_data('sfx', 'group_id'))

