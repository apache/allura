import ew

class SVNRevisionWidget(ew.Widget):
    template='jinja:svn_revision_widget.html'
    params=['value', 'prev', 'next']
    value=None
    prev=next=None
