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

from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from tg import app_globals as g

from allura.lib import utils
from allura.lib import validators as v
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as ff
from allura import model as M


class NullValidator(fev.FancyValidator):
    perform_validation = True
    accept_iterator = True

    def _to_python(self, value, state):
        return value

    def _from_python(self, value, state):
        return value

# Discussion forms


class ModerateThread(ff.CsrfForm):
    defaults = dict(
        ew.SimpleForm.defaults,
        submit_text=None)

    class buttons(ew_core.NameList):
        delete = ew.SubmitButton(label='Delete Thread')


class ModeratePost(ew.SimpleForm):
    template = 'jinja:allura:templates/widgets/moderate_post.html'
    defaults = dict(
        ew.SimpleForm.defaults,
        submit_text=None)


class AttachPost(ff.ForgeForm):
    defaults = dict(
        ff.ForgeForm.defaults,
        submit_text='Attach File',
        enctype='multipart/form-data')

    @property
    def fields(self):
        fields = [
            ew.InputField(name='file_info', field_type='file',
                          label='New Attachment')
        ]
        return fields


class ModeratePosts(ew.SimpleForm):
    template = 'jinja:allura:templates/widgets/moderate_posts.html'
    defaults = dict(
        ew.SimpleForm.defaults,
        submit_text=None)

    def resources(self):
        yield from super().resources()
        yield ew.JSScript('''
      (function($){
          var tbl = $('form table');
          var checkboxes = $('input[type=checkbox]', tbl);
          $('a[href=#]', tbl).click(function () {
              checkboxes.each(function () {
                  if(this.checked) { this.checked = false; }
                  else { this.checked = true; }
              });
              return false;
          });
          $('.col-checkbox').click(function(e){
            if (e.target.tagName === "INPUT") { return; };
            var checkbox = $(this).find('input[type=checkbox]').get(0);
            checkbox.checked = !checkbox.checked;
          });
      }(jQuery));''')


class PostFilter(ff.ForgeForm):
    defaults = dict(
        ew.SimpleForm.defaults,
        submit_text=None,
        method='GET')
    fields = [
        ew.HiddenField(
            name='page',
            validator=fev.Int()),
        ew.SingleSelectField(
                name='status',
                label='Filter By Status',
                options=[
                    ew.Option(py_value='-', label='Any'),
                    ew.Option(py_value='spam', label='Spam'),
                    ew.Option(py_value='pending',
                                label='Pending moderation'),
                    ew.Option(py_value='ok', label='Ok')],
                if_missing='pending'),
        ew.InputField(name='username',
                        label='Filter by Username'),
        ew.SubmitButton(label='Filter Posts')
    ]


class TagPost(ff.ForgeForm):

    # this ickiness is to override the default submit button
    def __call__(self, **kw):
        result = super().__call__(**kw)
        submit_button = ffw.SubmitButton(label=result['submit_text'])
        result['extra_fields'] = [submit_button]
        result['buttons'] = [submit_button]
        return result

    fields = [ffw.LabelEdit(label='Labels', name='labels', className='title')]

    def resources(self):
        yield from ffw.LabelEdit(name='labels').resources()


class EditPost(ff.ForgeForm):
    template = 'jinja:allura:templates/widgets/edit_post.html'
    antispam = True
    defaults = dict(
        ff.ForgeForm.defaults,
        show_subject=False,
        value=None,
        att_name='file_info')

    @property
    def fields(self):
        fields = ew_core.NameList()
        fields.append(ffw.MarkdownEdit(name='text'))
        fields.append(ew.HiddenField(name='forum', if_missing=None))
        fields.append(ew.Checkbox(name='subscribe', label='Subscribe', if_missing=False))
        if ew_core.widget_context.widget:
            # we are being displayed
            if ew_core.widget_context.render_context.get('show_subject', self.show_subject):
                fields.append(
                    ew.TextField(name='subject', attrs=dict(style="width:97%")))
        else:
            # We are being validated
            validator = v.UnicodeString(not_empty=True, if_missing='')
            fields.append(ew.TextField(name='subject', validator=validator))
            fields.append(NullValidator(name=self.att_name))
        return fields

    def resources(self):
        yield from ew.TextField(name='subject').resources()
        yield from ffw.MarkdownEdit(name='text').resources()
        yield ew.JSScript('''$(document).ready(function () {
            $("a.attachment_form_add_button").click(function(evt){
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
                evt.preventDefault();
            });
            $("a.cancel_edit_post").click(function(evt){
                evt.preventDefault();
                var form = this.parentNode;
                var orig_val = $("input.original_value", form).val();
                $("textarea", form).val(orig_val);
                get_cm(form).setValue(orig_val);
                $("input.attachment_form_fields", form).val('');
                $(this).closest('.reply_post_form').hide();
            });
         });''')


class NewTopicPost(EditPost):
    template = 'jinja:allura:templates/widgets/new_topic_post.html'
    defaults = dict(
        EditPost.defaults,
        show_subject=True,
        forums=None)

    @property
    def fields(self):
        fields = super().fields
        fields.append(ew.InputField(name='attachment', label='Attachment', field_type='file',
                                    attrs={'multiple': 'True'},
                                    validator=fev.FieldStorageUploadConverter(if_missing=None)))
        return fields


class _ThreadsTable(ew.TableField):
    template = 'jinja:allura:templates/widgets/threads_table.html'

    class fields(ew_core.NameList):
        _id = ew.HiddenField(validator=v.Ming(M.Thread))
        subscription = ew.Checkbox(suppress_label=True)
        subject = ffw.DisplayOnlyField(label='Topic')
        url = ffw.DisplayOnlyField()
        num_replies = ffw.DisplayOnlyField(label='Posts')
        num_views = ffw.DisplayOnlyField(label='Views')
        last_post = ffw.DisplayOnlyField(label='Last Post')


class SubscriptionForm(ew.SimpleForm):
    template = 'jinja:allura:templates/widgets/subscription_form.html'
    value = None
    threads = None
    show_subject = False
    allow_create_thread = False
    limit = None
    page = 0
    count = 0
    submit_text = 'Update Subscriptions'
    params = ['value', 'threads', 'limit', 'page', 'count',
              'show_subject', 'allow_create_thread']

    class fields(ew_core.NameList):
        page_list = ffw.PageList()
        page_size = ffw.PageSize()

        # Careful! using the same name as the prop on the model will invoke the RelationalProperty,
        # causing all related entities to be (re)fetched.
        _threads = _ThreadsTable()

    def resources(self):
        yield from super().resources()
        yield ew.JSScript('''
        $(window).on('load', function () {
            $('tbody').children(':even').addClass('even');
        });''')

# Widgets


class HierWidget(ew_core.Widget):
    widgets = {}

    def prepare_context(self, context):
        response = super().prepare_context(context)
        response['widgets'] = self.widgets
        for w in self.widgets.values():
            w.parent_widget = self
        return response

    def resources(self):
        for w in self.widgets.values():
            yield from w.resources()


class Attachment(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/attachment.html'
    params = ['value', 'post']
    value = None
    post = None


class ThreadHeader(HierWidget):
    template = 'jinja:allura:templates/widgets/thread_header.html'
    defaults = dict(
        HierWidget.defaults,
        value=None,
        page=None,
        limit=None,
        count=None,
        show_moderate=False)
    widgets = dict(
        page_list=ffw.PageList(),
        page_size=ffw.PageSize(),
        moderate_thread=ModerateThread(),
        tag_post=TagPost())


class Post(HierWidget):
    template = 'jinja:allura:templates/widgets/post_widget.html'
    defaults = dict(
        HierWidget.defaults,
        value=None,
        indent=0,
        page=0,
        limit=25,
        show_subject=False,
    )
    widgets = dict(
        moderate_post=ModeratePost(),
        edit_post=EditPost(submit_text='Post'),
        attach_post=AttachPost(submit_text='Attach'),
        attachment=Attachment())

    def resources(self):
        yield from super().resources()
        for w in self.widgets.values():
            yield from w.resources()
        yield ew.CSSScript('''
        div.moderate {
            color:grey;
        }
        ''')
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield ew.JSLink('js/post.js')


class PostThread(ew_core.Widget):
    template = 'jinja:allura:templates/widgets/post_thread.html'
    defaults = dict(
        ew_core.Widget.defaults,
        value=None,
        indent=0,
        page=0,
        limit=25,
        show_subject=False,
        parent=None,
        children=None)


class Thread(HierWidget):
    template = 'jinja:allura:templates/widgets/thread_widget.html'
    name = 'thread'
    defaults = dict(
        HierWidget.defaults,
        value=None,
        page=None,
        limit=50,
        count=None,
        posts=None,
        show_subject=False,
        new_post_text='+ New Comment')
    widgets = dict(
        page_list=ffw.PageList(),
        thread_header=ThreadHeader(),
        post_thread=PostThread(),
        post=Post(),
        edit_post=EditPost(submit_text='Submit'))

    def prepare_context(self, context):
        context = super().prepare_context(context)
        # bulk fetch backrefs to save on many queries within EW
        thread: M.Thread = context['value']

        page = context.get('page')
        limit = context.get('limit')
        limit, page, _ = g.handle_paging(limit, page)
        posts: list[M.Post] = thread.find_posts(page=page, limit=limit)

        context['posts'] = posts

        post_ids = [post._id for post in posts]
        post_index_ids = [post.index_id() for post in posts]

        # prefill refs
        refs = M.ArtifactReference.query.find(dict(_id={'$in': post_index_ids})).all()
        for post in posts:
            for ref in refs:
                if post.index_id() == ref._id:
                    post._ref = ref
                    break

        # prefill backrefs
        backrefs = M.ArtifactReference.query.find(dict(references={'$in': post_index_ids})).all()
        for post in posts:
            post._backrefs = [ref._id for ref in backrefs if post.index_id() in (ref.references or [])]

        # prefill attachments
        attachments = thread.attachment_class().query.find(
            dict(app_config_id=thread.app_config_id, artifact_id={'$in': post_ids}, type='attachment')).all()
        for post in posts:
            post._attachments = [att for att in attachments if post._id == att.post_id]
        return context

    def resources(self):
        yield from super().resources()
        for w in self.widgets.values():
            yield from w.resources()
        yield ew.JSScript('''
        $(document).ready(function () {
            var thread_tag = $('a.thread_tag');
            var thread_spam = $('a.sidebar_thread_spam');
            var tag_thread_holder = $('#tag_thread_holder');
            var allow_moderate = $('#allow_moderate');
            var mod_thread_link = $('#mod_thread_link');
            var mod_thread_form = $('#mod_thread_form');
            if (mod_thread_link.length) {
                if (mod_thread_form.length) {
                    mod_thread_link.click(function (e) {
                        mod_thread_form.toggle();
                        return false;
                    });
                }
            }
            if (thread_tag.length) {
                if (tag_thread_holder.length) {
                    var submit_button = $('input[type="submit"]', tag_thread_holder);
                    var cancel_button = $('<a href="#" class="btn link">Cancel</a>').click(function(evt){
                        evt.preventDefault();
                        tag_thread_holder.hide();
                        thread_tag.removeClass('active');
                    });
                    submit_button.after(cancel_button);
                    thread_tag.click(function (e) {
                        tag_thread_holder.show();
                        thread_tag.addClass('active');
                        // focus the submit to scroll to the form, then focus the subject for them to start typing
                        submit_button.focus();
                        $('input[type="text"]', tag_thread_holder).focus();
                        return false;
                    });
                }
            }
            if (thread_spam.length) {
                if (allow_moderate.length) {
                    thread_spam[0].style.display='block';
                }
            }
        });
        ''')
        yield ew.JSScript('''
            var global_reactions = %s;
        ''' % utils.get_reactions_json())
        yield ew.JSLink('js/reactions.js')
