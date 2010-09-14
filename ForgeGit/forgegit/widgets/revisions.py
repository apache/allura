import ew

class GitRevisionWidget(ew.Widget):
    template='jinja:git_widgets/revision.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
