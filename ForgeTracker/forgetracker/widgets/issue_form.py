import tw.forms as twf

issue_form = twf.TableForm('issue_form', action='save_issue', children=[
    twf.HiddenField('issue_num'),
    twf.TextField('summary'),
    twf.Spacer(),
    twf.TextArea('description', suppress_label=True),
    twf.TextField('reported_by'),
    twf.TextField('assigned_to'),
    twf.TextField('milestone'),

    twf.SingleSelectField('status', options=['open', 'unread', 'accepted', 'pending', 'closed'])
])
