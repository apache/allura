from ming.orm import FieldProperty
from ming import schema as S
from datetime import datetime, timedelta
from ming.orm import session, Mapper

from allura.model.session import main_orm_session
from allura.model.contrib_stats import Stats

class UserStats(Stats):
    class __mongometa__:
        name='userstats'
        session = main_orm_session
        unique_indexes = [ '_id', 'user_id']

    tot_logins_count = FieldProperty(int, if_missing = 0)
    last_login = FieldProperty(datetime)
    lastmonthlogins=FieldProperty([datetime])
    user_id = FieldProperty(S.ObjectId)

    @classmethod
    def create(cls, user):
        stats = cls.query.get(user_id = user._id)
        if stats:
            return stats
        stats = cls(user_id=user._id,
            registration_date = datetime.utcnow())
        user.stats_id = stats._id
        session(stats).flush(stats)
        session(user).flush(user)
        return stats

    def getLastMonthLogins(self):
        self.checkOldArtifacts()
        return len(self.lastmonthlogins)

    def checkOldArtifacts(self):
        super(UserStats, self).checkOldArtifacts()
        now = datetime.utcnow()
        for l in self.lastmonthlogins:
            if now - l > timedelta(30):
                self.lastmonthlogins.remove(l)

    def addLogin(self, login_datetime):
        if (not self.last_login) or (login_datetime > self.last_login):
            self.last_login = login_datetime
        self.tot_logins_count += 1
        self.lastmonthlogins.append(login_datetime)
        self.checkOldArtifacts()
        
Mapper.compile_all()
