from allura.lib.decorators import task

@task
def notify(n_id, ref_id, topic):
    from allura import model as M
    M.Mailbox.deliver(n_id, ref_id, topic)
    M.Mailbox.fire_ready()
