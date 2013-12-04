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
from ming.odm import Mapper
from activitystream import base
from allura.lib import security


class ActivityNode(base.NodeBase):
    @property
    def node_id(self):
        return "%s:%s" % (self.__class__.__name__, self._id)


class ActivityObject(base.ActivityObjectBase):
    @property
    def activity_name(self):
        """Override this for each Artifact type."""
        return "%s %s" % (self.__mongometa__.name.capitalize(), self._id)

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
        return "%s:%s" % (self.__class__.__name__, self._id)

    def has_activity_access(self, perm, user):
        """Return True if user has perm access to this object, otherwise
        return False.
        """
        return security.has_access(self, perm, user, self.project)


def perm_check(user):
    def _perm_check(activity):
        """Return True if c.user has 'read' access to this activity,
        otherwise return False.
        """
        extras_dict = activity.obj.activity_extras
        if not extras_dict: return True
        allura_id = extras_dict.get('allura_id')
        if not allura_id: return True
        classname, _id = allura_id.split(':', 1)
        cls = Mapper.by_classname(classname).mapped_class
        try:
            _id = bson.ObjectId(_id)
        except bson.errors.InvalidId:
            pass
        obj = cls.query.get(_id=_id)
        return obj and obj.has_activity_access('read', user)
    return _perm_check
