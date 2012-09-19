import pymongo
import pylons
pylons.c = pylons.tmpl_context
from pylons import c
from ming.orm import FieldProperty, ForeignIdProperty, session
from datetime import datetime
from allura.model.auth import User
from allura import model as M


class ShortUrl(M.Artifact):

    class __mongometa__:
        name = 'short_urls'
        unique_indexes = ['short_name']

    type_s = 'ShortUrl'
    full_url = FieldProperty(str)
    short_name = FieldProperty(str)
    description = FieldProperty(str)
    private = FieldProperty(bool)
    create_user = ForeignIdProperty(User)
    created = FieldProperty(datetime, if_missing=datetime.utcnow)
    last_updated = FieldProperty(datetime, if_missing=datetime.utcnow)

    @property
    def user(self):
        return User.query.get(_id=self.create_user)

    @classmethod
    def upsert(cls, shortname):
        u = cls.query.get(short_name=shortname, app_config_id=c.app.config._id)
        if u is not None:
            return u
        try:
            u = cls(short_name=shortname, app_config_id=c.app.config._id)
            session(u).flush(u)
        except pymongo.errors.DuplicateKeyError:
            session(u).expunge(u)
            u = cls.query.get(short_name=shortname,
                    app_config_id=c.app.config._id)
        return u

    def index(self):
        result = M.Artifact.index(self)
        result.update(
            full_url_s=self.full_url,
            short_name_s=self.short_name,
            description_s=self.description,
            title_s='%s => %s' % (self.url(), self.full_url),
            type_s=self.type_s)
        return result

    def url(self):
        return self.app.url + self.short_name
