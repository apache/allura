from datetime import datetime, timedelta

from bson import ObjectId

from . import model as TM


def tickets_stats_24hr():
    window = datetime.utcnow() - timedelta(hours=24)
    return TM.Ticket.query.find({'_id': {'$gte': ObjectId.from_datetime(window)}}).count()
