import logging

from pylons import c
from allura.lib.decorators import task

log = logging.getLogger(__name__)

@task
def launch_bicho(shortname):
    log.info("TASK: Launching Bicho tool", shortname);
#    from forgediscussion import model as DM
#    forum = DM.Forum.query.get(
#        shortname=shortname, app_config_id=c.app.config._id)
#    if forum is None:
#        log.error("Error looking up forum: %r", shortname)
#        return
#    forum.update_stats()
