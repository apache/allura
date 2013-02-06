import logging

from pylons import c
from allura.lib.decorators import task
from allura.lib import helpers as h

from allura import model as M

log = logging.getLogger(__name__)


@task
def update_bin_counts(app_config_id):
    app_config = M.AppConfig.query.get(_id=app_config_id)
    app = app_config.project.app_instance(app_config)
    with h.push_config(c, app=app):
        app.globals.update_bin_counts()
