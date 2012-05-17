import shutil
import logging
import traceback

from pylons import c

from allura.lib.decorators import task
from allura.lib.repository import RepositoryApp
from allura.lib import helpers as h
from allura.tasks.mail_tasks import sendmail

@task
def init(**kwargs):
    from allura import model as M
    c.app.repo.init()
    M.Notification.post_user(
        c.user, c.app.repo, 'created',
        text='Repository %s/%s created' % (
            c.project.shortname, c.app.config.options.mount_point))

@task
def clone(
    cloned_from_path,
    cloned_from_name,
    cloned_from_url):
    try:
        from allura import model as M
        c.app.repo.init_as_clone(
            cloned_from_path,
            cloned_from_name,
            cloned_from_url)
        M.Notification.post_user(
            c.user, c.app.repo, 'created',
            text='Repository %s/%s created' % (
                c.project.shortname, c.app.config.options.mount_point))
        if not c.project.suppress_emails:
            sendmail(
                destinations=[str(c.user._id)],
                fromaddr=u'SourceForge.net <noreply+project-upgrade@in.sf.net>',
                reply_to=u'noreply@in.sf.net',
                subject=u'SourceForge Repo Clone Complete',
                message_id=h.gen_message_id(),
                text=u''.join([
                    u'Clone of repo %s in project %s from %s is complete. Your repo is now ready to use.\n'
                ]) % (c.app.config.options.mount_point, c.project.shortname, cloned_from_url))
    except:
        sendmail(
            destinations=['sfengineers@geek.net'],
            fromaddr=u'SourceForge.net <noreply+project-upgrade@in.sf.net>',
            reply_to=u'noreply@in.sf.net',
            subject=u'SourceForge Repo Clone Failure',
            message_id=h.gen_message_id(),
            text=u''.join([
                u'Clone of repo %s in project %s from %s failed.\n',
                u'\n',
                u'%s',
            ]) % (c.app.config.options.mount_point, c.project.shortname, cloned_from_url, traceback.format_exc()))
        if not c.project.suppress_emails:
            sendmail(
                destinations=[str(c.user._id)],
                fromaddr=u'SourceForge.net <noreply+project-upgrade@in.sf.net>',
                reply_to=u'noreply@in.sf.net',
                subject=u'SourceForge Repo Clone Failed',
                message_id=h.gen_message_id(),
                text=u''.join([
                    u'Clone of repo %s in project %s from %s failed. ',
                    u'The SourceForge engineering team has been notified.\n',
                ]) % (c.app.config.options.mount_point, c.project.shortname, cloned_from_url))

@task
def reclone(*args, **kwargs):
    from allura import model as M
    from ming.orm import ThreadLocalORMSession
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        repo.delete()
    ThreadLocalORMSession.flush_all()
    M.MergeRequest.query.remove(dict(
            app_config_id=c.app.config._id))
    clone(*args, **kwargs)

@task
def refresh(**kwargs):
    c.app.repo.refresh()

@task
def uninstall(**kwargs):
    from allura import model as M
    repo = c.app.repo
    if repo is not None:
        shutil.rmtree(repo.full_fs_path, ignore_errors=True)
        repo.delete()
    M.MergeRequest.query.remove(dict(
            app_config_id=c.app.config._id))
    super(RepositoryApp, c.app).uninstall(c.project)
    from ming.orm import ThreadLocalORMSession
    ThreadLocalORMSession.flush_all()

@task
def nop():
    log = logging.getLogger(__name__)
    log.info('nop')
