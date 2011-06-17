from pylons import g, c

import ew as ew_core
from ew import jinja2_ew as ew
import formencode
from formencode import validators as fev

from allura import model as M
from allura.lib import validators as V
from allura.lib import security
from allura.lib.widgets import forms as ff

from bson import ObjectId

class CardField(ew._Jinja2Widget):
    template = 'jinja:allura.ext.admin:templates/admin_widgets/card_field.html'
    defaults = dict(
        ew_core.Widget.defaults,
        id=None,
        name='Deck',
        icon_name='group',
        items=None,
        roles=[],
        settings_href=None)

    def item_display(self, item):
        return repr(item)

    def item_id(self, item):
        return repr(item)

    def resources(self):
        yield ew.CSSScript('''.deck li input, .deck li select {
margin: 2px 0 2px 3px;
width: 148px;
}''')
        yield ew.JSScript('''$(function() {
    $('.active-card').each(function() {
        var newitem = $('.new-item', this);
        var adder = $('.adder', this);
        var deleters = $('.deleter', this);
        newitem.remove();
        newitem.removeClass('new-item');
        deleters.click(function(evt) {
            evt.stopPropagation();
            evt.preventDefault();
            var $this = $(this);
            $this.closest('li').remove();
        });
        adder.click(function(evt) {
            evt.stopPropagation();
            evt.preventDefault();
            newitem.clone().insertBefore(adder.closest('li'));
        });
    });
});''')

class GroupCard(CardField):
    new_item=ew.InputField(field_type='text', attrs=dict(placeholder='type a username'))

    def item_display(self, item):
        return item.user.username

    def item_id(self, item):
        return item.user._id

    def role_name(self, role_id):
        return M.ProjectRole.query.get(_id=ObjectId(role_id)).name

class _GroupSelect(ew.SingleSelectField):

    def options(self):
        auth_role = M.ProjectRole.authenticated()
        anon_role = M.ProjectRole.anonymous()
        options = [
            ew.Option(py_value=role._id, label=role.name)
            for role in c.project.named_roles ]
        options.append(ew.Option(py_value=auth_role._id, label=auth_role.name))
        options.append(ew.Option(py_value=anon_role._id, label=anon_role.name))
        return options

class PermissionCard(CardField):
    new_item = _GroupSelect()

    def item_display(self, role):
        return role.name

    def item_id(self, role):
        return role._id


class GroupSettings(ew.SimpleForm):
    submit_text=None

    class hidden_fields(ew_core.NameList):
        _id = ew.HiddenField(
            validator=V.Ming(M.ProjectRole))

    class fields(ew_core.NameList):
        name = ew.InputField(label='Name')

    class buttons(ew_core.NameList):
        save = ew.SubmitButton(label='Save')
        delete = ew.SubmitButton(label='Delete Group')

class NewGroupSettings(ff.AdminForm):
    submit_text='Save'
    class fields(ew_core.NameList):
        name = ew.InputField(label='Name')

class ScreenshotAdmin(ff.AdminForm):
    defaults=dict(
        ff.AdminForm.defaults,
        enctype='multipart/form-data')

    @property
    def fields(self):
        fields = [
            ew.InputField(name='screenshot', field_type='file', label='New Screenshot'),
            ew.InputField(name='caption', field_type="text", label='Caption')
        ]
        return fields

class MetadataAdmin(ff.AdminForm):
    template = 'jinja:allura.ext.admin:templates/admin_widgets/metadata_admin.html'
    defaults=dict(
        ff.AdminForm.defaults,
        show_export_control=False,
        enctype='multipart/form-data')

    class fields(ew_core.NameList):
        name = ew.InputField(field_type='text',
                             label='Name',
                             validator=formencode.All(
                                fev.UnicodeString(not_empty=True, max=40),
                                V.MaxBytesValidator(max=40)),
                             attrs=dict(maxlength=40,
                                        title="This is the publicly viewable name of the project, and will appear on project listings. It should be what you want to see as the project title in search listing."))
        short_description = ew.TextArea(label='Summary'                                ,
                                        validator=formencode.All(
                                            fev.UnicodeString(not_empty=True, max=255),
                                            V.MaxBytesValidator(max=255)),
                                        attrs=dict(title="Add a short one or two sentence summary for your project."))
        icon = ew.InputField(field_type="file", label='Icon')
        external_homepage = ew.InputField(field_type="text", label='Homepage')
        support_page = ew.InputField(field_type="text", label='Support Page')
        support_page_url = ew.InputField(field_type="text", label='Support Page URL')
        removal = ew.InputField(field_type="text", label='Removal')
        moved_to_url = ew.InputField(field_type="text", label='Moved Project to URL')
        export_controlled = ew.InputField(field_type="text", label='Export Control')
        delete =  ew.InputField(field_type="hidden", label='Delete')
        delete_icon =  ew.InputField(field_type="hidden", label='Delete Icon')
        undelete =  ew.InputField(field_type="hidden", label='Undelete')