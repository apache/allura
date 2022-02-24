#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import bson
import logging

from ming.odm import Mapper
from tg import tmpl_context as c

from activitystream import ActivityDirector
from activitystream.base import NodeBase, ActivityObjectBase
from activitystream.managers import Aggregator as BaseAggregator

from allura.lib import security
from allura.tasks.activity_tasks import create_timelines

log = logging.getLogger(__name__)


class Director(ActivityDirector):

    """Overrides the default ActivityDirector to kick off background
    timeline aggregations after an activity is created.

    """

    def create_activity(self, actor, verb, obj, target=None,
                        related_nodes=None, tags=None):
        if c.project and c.project.notifications_disabled:
            return

        from allura.model.project import Project
        super().create_activity(actor, verb, obj,
                                              target=target,
                                              related_nodes=related_nodes,
                                              tags=tags)
        # aggregate actor and follower's timelines
        if actor.node_id:
            create_timelines.post(actor.node_id)
        # aggregate project and follower's timelines
        for node in [obj, target] + (related_nodes or []):
            if isinstance(node, Project):
                create_timelines.post(node.node_id)


class Aggregator(BaseAggregator):
    pass


class ActivityNode(NodeBase):

    @property
    def node_id(self):
        return f"{self.__class__.__name__}:{self._id}"


class ActivityObject(ActivityObjectBase):
    '''
    Allura's base activity class.
    '''

    @property
    def activity_name(self):
        """Override this for each Artifact type."""
        return f"{self.__mongometa__.name.capitalize()} {self._id}"

    @property
    def activity_url(self):
        return self.url()

    @property
    def activity_extras(self):
        """Return a BSON-serializable dict of extra stuff to store on the
        activity.
        """
        return {"allura_id": self.allura_id}

    @property
    def allura_id(self):
        """Return a string which uniquely identifies this object and which can
        be used to retrieve the object from mongo.
        """
        return f"{self.__class__.__name__}:{self._id}"

    def has_activity_access(self, perm, user, activity):
        """Return True if user has perm access to this object, otherwise
        return False.
        """
        if self.project is None or getattr(self, 'deleted', False):
            return False
        return security.has_access(self, perm, user, self.project)


class TransientActor(NodeBase, ActivityObjectBase):
    """An activity actor which is not a persistent Node in the network.

    """
    def __init__(self, activity_name):
        NodeBase.__init__(self)
        ActivityObjectBase.__init__(self)
        self.activity_name = activity_name


def get_activity_object(activity_object_dict):
    """Given a BSON-serialized activity object (e.g. activity.obj dict in a
    timeline), return the corresponding :class:`ActivityObject`.

    """
    extras_dict = activity_object_dict.activity_extras
    if not extras_dict:
        return None
    allura_id = extras_dict.get('allura_id')
    if not allura_id:
        return None
    classname, _id = allura_id.split(':', 1)
    cls = Mapper.by_classname(classname).mapped_class
    try:
        _id = bson.ObjectId(_id)
    except bson.errors.InvalidId:
        pass
    return cls.query.get(_id=_id)


def perm_check(user):
    """
    Return a function that returns True if ``user`` has 'read' access to a given activity,
    otherwise returns False.
    """
    def _perm_check(activity):
        obj = get_activity_object(activity.obj)
        return obj is None or obj.has_activity_access('read', user, activity)
    return _perm_check
