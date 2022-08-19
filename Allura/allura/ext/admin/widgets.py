#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from tg import tmpl_context as c

import ew as ew_core
from ew import jinja2_ew as ew
import formencode
from formencode import validators as fev

from allura import model as M
from allura.lib import validators as V
from allura.lib.widgets import forms as ff
from allura.lib.widgets import form_fields as ffw

from bson import ObjectId


class CardField(ew._Jinja2Widget):
    template = 'jinja:allura.ext.admin:templates/admin_widgets/card_field.html'
    sort_key = None
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
    new_item = ew.InputField(
        field_type='text', attrs=dict(placeholder='type a username'))
    sort_key = 'user.username'

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
            for role in c.project.named_roles]
        options.append(ew.Option(py_value=auth_role._id, label=auth_role.name))
        options.append(ew.Option(py_value=anon_role._id, label=anon_role.name))
        return options


class PermissionCard(CardField):
    new_item = _GroupSelect()
    sort_key = 'name'

    def item_display(self, role):
        return role.name

    def item_id(self, role):
        return role._id


class NewGroupSettings(ff.AdminFormResponsive):
    submit_text = 'Save'

    class fields(ew_core.NameList):
        name = ew.InputField(label='Name')


class ScreenshotAdmin(ff.ForgeFormResponsive):
    defaults = dict(
        ff.ForgeForm.defaults,
        enctype='multipart/form-data',
        submit_text='Upload',
        )

    @property
    def fields(self):
        fields = [
            ew.InputField(name='screenshot', field_type='file',
                          label='New Screenshot',
                          attrs={
                              'accept': 'image/*',
                              'required': 'true',
                              }),
            ew.InputField(name='caption',
                          field_type="text",
                          label='Caption',
                          attrs={
                              'title': "Reuse your project name in screenshot file names and create a caption to briefly describe each screenshot.",
                              'class': 'm-tooltip',
                          }
                          )
        ]
        return fields


class FeaturesField(ew.CompoundField):
    template = 'jinja:allura.ext.admin:templates/admin_widgets/features_field.html'
    fields = [ew.TextField(name='feature', attrs={'style': 'width:89%'})]

    def resources(self):
        yield ew.JSLink('allura/js/jquery-ui-1.13.2.min.js', location='body_top_js')
        yield ew.CSSLink('allura/css/smoothness/jquery-ui-1.13.2.min.css', compress=False)  # compress will also serve from a different location, breaking image refs


class MetadataAdmin(ff.AdminForm):
    template = 'jinja:allura.ext.admin:templates/admin_widgets/metadata_admin.html'
    defaults = dict(
        ff.AdminForm.defaults,
        enctype='multipart/form-data')

    class fields(ew_core.NameList):
        name = ew.InputField(field_type='text',
                             label='Name',
                             validator=formencode.All(
                                 V.UnicodeString(not_empty=True, max=40),
                                 V.MaxBytesValidator(max=40),
                             ),
                             attrs={'maxlength': 40,
                                    'title': "This is the publicly viewable name of the project, and will appear on project listings. It should be what you want to see as the project title in search listing.",
                                    'class': 'tooltip',
                                    })
        summary = ew.InputField(field_type="text", label='Short Summary',
                                validator=formencode.All(
                                    V.UnicodeString(max=70),
                                    V.MaxBytesValidator(max=70)),
                                attrs={'maxlength': 70,
                                       'title': 'Briefly state what your project is and what it does without repeating the project name. This summary appears in Google search results beneath the project name.',
                                       'class': 'tooltip',
                                       })
        short_description = ew.TextArea(label='Full Description',
                                        validator=V.UnicodeString(max=1000),
                                        attrs={
                                            'title': 'Describe the full functionality of your project using related keywords. The first sentence has the most impact on search. Provide unique content that calls out keywords and describes the merits of your project.',
                                            'class': 'tooltip'
                                        })
        # Apparently, child field must be CompoundField with custom template
        # for SortableRepeatedField to work properly, that's why FeaturesField
        # is not just ew.TextField
        features = ffw.SortableRepeatedField(
            label='Features',
            show_msg=False,
            show_button=False,
            append_to='bottom',
            extra_field_on_focus_name='feature',
            field=FeaturesField())
        icon = ew.FileField(label='Icon', attrs={'accept': 'image/*'},
                            validator=V.IconValidator())
        external_homepage = ew.InputField(field_type="text", label='Homepage',
                                          validator=fev.URL(add_http=True))
        video_url = ew.InputField(field_type="text", label="Video (YouTube)",
                                  attrs={'title': 'Paste in a Youtube URL', 'class': 'tooltip'},
                                  validator=V.YouTubeConverter())
        support_page = ew.InputField(field_type="text", label='Support Page')
        support_page_url = ew.InputField(
            field_type="text", label='Support Page URL',
            validator=fev.URL(add_http=True, if_empty=''))
        removal = ew.InputField(field_type="text", label='Removal')
        moved_to_url = ew.InputField(
            field_type="text", label='Moved Project to URL',
            validator=fev.URL(add_http=True, if_empty=''))
        delete = ew.InputField(field_type="hidden", label='Delete')
        delete_icon = ew.InputField(field_type="hidden", label='Delete Icon')
        undelete = ew.InputField(field_type="hidden", label='Undelete')
        tracking_id = ew.InputField(
            field_type="text", label="Google Analytics ID",
            attrs=(dict(placeholder='UA-123456-0', pattern='UA-[0-9]+-[0-9]+')))
        twitter_handle = ew.InputField(
            field_type="text", label='Twitter Handle')
        facebook_page = ew.InputField(field_type="text", label='Facebook page',
                                      validator=fev.URL(add_http=True))


class AuditLog(ew_core.Widget):
    template = 'jinja:allura.ext.admin:templates/widgets/audit.html'
    defaults = dict(
        ew_core.Widget.defaults,
        entries=None,
        limit=None,
        page=0,
        count=0)

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()

    def resources(self):
        for f in self.fields:
            yield from f.resources()


class BlockUser(ffw.Lightbox):
    defaults = dict(
        ffw.Lightbox.defaults,
        name='block-user-modal',
        trigger='a.block-user',
        content_template='allura.ext.admin:templates/widgets/block_user.html')


class BlockList(ffw.Lightbox):
    defaults = dict(
        ffw.Lightbox.defaults,
        name='block-list-modal',
        trigger='a.block-list',
        content_template='allura.ext.admin:templates/widgets/block_list.html')
