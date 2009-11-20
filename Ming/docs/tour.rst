Intro to Ming
======================

Ming lets you use an inner `__mongometa__` class to define schemas for your mongo documents:

::

    class Artifact(Document):
        class __mongometa__:
            session = ProjectSession(Session.by_name('main'))
            name='artifact'

        # Artifact base schema
        _id = Field(S.ObjectId)
        project_id = Field(S.String)
        plugin_verson = Field(S.Object,{ str: str },)
        acl = Field({str:[str]})
        