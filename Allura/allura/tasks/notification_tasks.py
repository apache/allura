import logging

from allura import model as M
from allura.lib.decorators import task

log = logging.getLogger(__name__)

@task
def notify(n_id, ref_id, topic):
    M.Mailbox.deliver(n_id, ref_id, topic)
    M.Mailbox.fire_ready()
