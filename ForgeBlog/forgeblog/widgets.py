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

import ew as ew_core
import ew.jinja2_ew as ew

from formencode import validators as fev

from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms
from allura import model as M
from allura.lib import validators as v


class BlogPager(ffw.PageList):
    template = 'jinja:forgeblog:templates/blog_widgets/page_list.html'


class BlogPostForm(forms.ForgeForm):
    template = 'jinja:forgeblog:templates/blog_widgets/post_form.html'
    enctype = 'multipart/form-data'

    @property
    def fields(self):
        return ew_core.NameList([
            ew.TextField(name='title',
                         validator=v.UnicodeString(not_empty=True,
                                                     messages={'empty': "You must provide a Title"}),
                         attrs=dict(placeholder='Enter your title here',
                                    title='Enter your title here',
                                    style='width: 425px')),
            ffw.MarkdownEdit(name='text',
                             show_label=False,
                             attrs=dict(
                                 placeholder='Enter your content here',
                                 title='Enter your content here')),
            ew.SingleSelectField(name='state',
                                 options=[
                                     ew.Option(py_value='draft', label='Draft'),
                                     ew.Option(py_value='published', label='Published')]),
            ffw.LabelEdit(name='labels',
                          placeholder='Add labels here',
                          title='Add labels here'),
            ew.InputField(name='attachment',
                          label='Attachment', field_type='file', attrs={'multiple': 'True'},
                          validator=fev.FieldStorageUploadConverter(if_missing=None)),
        ])

    def resources(self):
        yield from super().resources()
        yield ew.JSScript('''
            $(function() {
                $('input[name="title"]').focus();
            });
        ''')


class NewPostForm(BlogPostForm):

    @property
    def fields(self):
        fields = super().fields
        fields.append(ew.Checkbox(name='subscribe'))
        return fields


class EditPostForm(BlogPostForm):

    class buttons(ew_core.NameList):
        delete = ew.SubmitButton(label='Delete')


class ViewPostForm(ew_core.Widget):
    template = 'jinja:forgeblog:templates/blog_widgets/view_post.html'
    defaults = dict(
        ew_core.Widget.defaults,
        value=None,
        subscribed=None,
        base_post=None)

    def __call__(self, **kw):
        kw = super().__call__(**kw)
        kw['subscribed'] = \
            M.Mailbox.subscribed(artifact=kw.get('value'))
        return kw


class PreviewPostForm(ew_core.Widget):
    template = 'jinja:forgeblog:templates/blog_widgets/preview_post.html'
    defaults = dict(
        ew_core.Widget.defaults,
        value=None)
