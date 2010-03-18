import tw.forms as twf
from pylons import c
from forgetracker import model

ticket_form = twf.TableForm('ticket_form', action='../save_ticket', children=[
    twf.HiddenField('ticket_num'),
    twf.TextField('summary'),
    twf.Spacer(),
    twf.TextArea('description', suppress_label=True),
  # twf.TextField('assigned_to'),

    twf.SingleSelectField('milestone',
        options=lambda: model.Globals.query.get(app_config_id=c.app.config._id).milestone_names.split(',')),

    twf.SingleSelectField('status',
        options=lambda: model.Globals.query.get(app_config_id=c.app.config._id).status_names.split(','))
])
