from datetime import datetime, timedelta

from . import model as DM


def posts_24hr():
    window = datetime.utcnow() - timedelta(hours=24)
    return DM.ForumPost.query.find({'timestamp': {'$gte': window}}).count()
