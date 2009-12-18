from tw.api import WidgetsList
from tw.forms import TableForm, CalendarDatePicker, SingleSelectField, TextField, TextArea

class IssueForm(TableForm):

    class fields(WidgetsList):
        #created_date
        #parent
        summary         = TextField()
        description     = TextArea()
        reported_by     = TextField()
        assigned_to     = TextField()
        milestone       = TextField()

        status_options  = enumerate(('open', 'unread', 'accepted', 'pending', 'closed'))
        status          = SingleSelectField(options=status_options)

create_issue_form = IssueForm("create_issue_form")
