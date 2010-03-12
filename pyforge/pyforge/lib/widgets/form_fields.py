from pylons import c
from pyforge.model import User

import ew

class MarkdownEdit(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.markdown_edit'
    params=['name','value']
    name=None
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/wmd/wmd.js')

class UserTagEdit(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.user_tag_edit'
    params=['name','user_tags']
    name=None
    user_tags=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')

class ProjectUserSelect(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.project_user_select'
    params=['name', 'value', 'size', 'all', 'users']
    name=None
    value=None
    size=None
    all=False

    def __init__(self, **kw):
      self.users = User.query.find({'_id':{'$in':[role.user_id for role in c.project.roles]}}).all()
      if not isinstance(self.value, list):
          self.value=[self.value]
      super(ProjectUserSelect, self).__init__(**kw)

class AttachmentList(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.attachment_list'
    params=['attachments','edit_mode']
    attachments=None
    edit_mode=None