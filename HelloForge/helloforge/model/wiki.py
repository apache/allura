Quick Ming Example
=========================

Here is some sample code from a TG project that uses ming:: 

    class Artifact(Document):
        class __mongometa__:
            session = ProjectSession(Session.by_name('main'))
            name='artifact'

        # Artifact base schema
        _id = Field(S.ObjectId)
        project_id = Field(S.String, if_missing=lambda:c.project._id)
        plugin_verson = Field(
            S.Object,
            { str: str },
            if_missing=lambda:{c.app.config.name:c.app.__version__})
        acl = Field({str:[str]})