from pylons import c
from pyforge.model import User
from formencode import validators as fev

import ew

class MarkdownEdit(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.markdown_edit'
    validator = fev.UnicodeString()
    params=['name','value','show_label']
    show_label=True
    name=None
    value=None

    def resources(self):
        yield ew.resource.JSLink('js/jquery.markitup.pack.js')
        yield ew.resource.JSLink('js/jquery.markitup.markdown.js')
        yield ew.resource.JSLink('js/sf_markitup.js')
        yield ew.resource.CSSLink('css/markitup.css')
        yield ew.resource.CSSLink('css/markitup_markdown.css')
        yield ew.resource.CSSLink('css/markitup_sf.css')

class UserTagEdit(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.user_tag_edit'
    validator = fev.UnicodeString()
    params=['name','user_tags', 'className', 'show_label']
    show_label=True
    name=None
    user_tags=None
    className=''

    def resources(self):
        yield ew.resource.JSLink('js/jquery.tag.editor.js')

class ProjectUserSelect(ew.InputField):
    template='genshi:pyforge.lib.widgets.templates.project_user_select'
    params=['name', 'value', 'size', 'all', 'users', 'show_label']
    show_label=True
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

class SubmitButton(ew.SubmitButton):
    attrs={'class':'ui-state-default ui-button ui-button-text'}
