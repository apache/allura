from activitystream import base

class Node(base.NodeBase):
    @property
    def node_id(self):
        return "%s:%s" % (self.__mongometa__.name, self._id)

class ActivityObject(base.ActivityObjectBase):
    @property
    def activity_name(self):
        """Override this for each Artifact type."""
        return "%s %s" % (self.__mongometa__.name.capitalize(), self._id)

    @property
    def activity_url(self):
        return self.url()
