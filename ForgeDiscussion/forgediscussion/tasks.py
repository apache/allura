import logging

from tg import c
from allura.lib.decorators import task

log = logging.getLogger(__name__)

@task
def calc_forum_stats(shortname):
    from forgediscussion import model as DM
    forum = DM.Forum.query.get(
        shortname=shortname, app_config_id=c.app.config._id)
    if forum is None:
        log.error("Error looking up forum: %r", shortname)
        return
    forum.update_stats()

@task
def calc_thread_stats(thread_id):
    from forgediscussion import model as DM
    thread = DM.ForumThread.query.get(_id=thread_id)
    if thread is None:
        log.error("Error looking up thread: %r", thread_id)
    thread.update_stats()
