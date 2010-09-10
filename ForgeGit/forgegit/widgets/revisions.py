import ew

class GitRevisionWidget(ew.Widget):
    template='jinja:git_revision_widget.html'
    params=['value', 'prev', 'next']
    value=None
    prev=()
    next=()
