import tw.forms as twf
from pylons import c
from forgetracker import model

bin_form = twf.TableForm('bin_form', action='../save_bin', children=[
    twf.TextField('summary'),
    twf.Spacer(),
    twf.TextField('terms'),

    twf.SingleSelectField('status',
        options=lambda: model.Globals.query.get(app_config_id=c.app.config._id).status_names.split(','))
])
