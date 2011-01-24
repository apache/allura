from pylons import c
from formencode import validators as fev

import ew as ew_core
import ew.jinja2_ew as ew

from allura.lib import validators as V
from allura.lib import helpers as h
from allura.lib.widgets import form_fields as ffw
from allura.lib.widgets import forms as ff
from allura import model as M

class NullValidator(fev.FancyValidator):
    perform_validation=True

    def _to_python(self, value, state): return value
    def _from_python(self, value, state): return value

# Discussion forms
class ModerateThread(ew.SimpleForm):
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text=None)
    class buttons(ew_core.NameList):
        delete=ew.SubmitButton(label='Delete Thread')

class ModeratePost(ew.SimpleForm):
    template='jinja:widgets/moderate_post.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text=None)

class FlagPost(ew.SimpleForm):
    template='jinja:widgets/flag_post.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text=None)

class AttachPost(ff.ForgeForm):
    defaults=dict(
        ff.ForgeForm.defaults,
        submit_text='Attach File',
        enctype='multipart/form-data')

    @property
    def fields(self):
        fields = [
            ew.InputField(name='file_info', field_type='file', label='New Attachment')
        ]
        return fields

class ModeratePosts(ew.SimpleForm):
    template='jinja:widgets/moderate_posts.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text=None)
    def resources(self):
        for r in super(ModeratePosts, self).resources(): yield r
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
      }(jQuery));''')

class PostFilter(ff.ForgeForm):
    defaults=dict(
        ew.SimpleForm.defaults,
        submit_text=None,
        method='GET')
    fields = [
        ew.FieldSet(label='Post Filter', fields=[
                ew.SingleSelectField(
                    name='status',
                    label='Show posts with status',
                    options=[
                        ew.Option(py_value='-', label='Any'),
                        ew.Option(py_value='spam', label='Spam'),
                        ew.Option(py_value='pending', label='Pending moderation'),
                        ew.Option(py_value='ok', label='Ok')],
                    if_missing='-'),
                ew.IntField(name='flag',
                            label='Show posts with at least "n" flags',
                            css_class='text',
                            if_missing=0),
                ew.SubmitButton(label='Filter Posts')
                ])
        ]

class TagPost(ff.ForgeForm):

    # this ickiness is to override the default submit button
    def __call__(self, **kw):
        result = super(TagPost, self).__call__(**kw)
        submit_button = ffw.SubmitButton(label=result['submit_text'])
        result['extra_fields'] = [submit_button]
        result['buttons'] = [submit_button]
        return result

    fields=[ffw.LabelEdit(label='Labels',name='labels', className='title')]

    def resources(self):
        for r in ffw.LabelEdit(name='labels').resources(): yield r

class EditPost(ff.ForgeForm):
    template='jinja:widgets/edit_post.html'
    defaults=dict(
        ff.ForgeForm.defaults,
        show_subject=False,
        value=None,
        att_name='file_info')

    @property
    def fields(self):
        fields = []
        fields.append(ffw.AutoResizeTextarea(
            name='text',
            attrs={'style':'min-height:7em; width:97%'}))
        fields.append(ew.HiddenField(name='forum', if_missing=None))
        if ew_core.widget_context.widget:
            # we are being displayed
            if ew_core.widget_context.render_context.get('show_subject', self.show_subject):
                fields.append(ew.TextField(name='subject'))
        else:
            # We are being validated
            validator = fev.UnicodeString(not_empty=True, if_missing='')
            fields.append(ew.TextField(name='subject', validator=validator))
            fields.append(NullValidator(name=self.att_name))
        return fields

    def resources(self):
        for r in ew.TextField(name='subject').resources(): yield r
        for r in ffw.AutoResizeTextarea(name='text').resources(): yield r
        yield ew.JSScript('''$(document).ready(function () {
            $("a.attachment_form_add_button").click(function(evt){
                $(this).hide();
                $(".attachment_form_fields", this.parentNode).show();
                evt.preventDefault();
            });
            $("a.cancel_edit_post").click(function(evt){
                $("textarea", this.parentNode).val($("input.original_value", this.parentNode).val());
                $(".attachment_form_fields input", this.parentNode).val('');
                evt.preventDefault();
            });
         });''')

class NewTopicPost(EditPost):
    template='jinja:widgets/new_topic_post.html'
    defaults=dict(
        EditPost.defaults,
        show_subject = True,
        forums=None)

class _ThreadsTable(ew.TableField):
    template='jinja:widgets/threads_table.html'
    class hidden_fields(ew_core.NameList):
        _id=ew.HiddenField(validator=V.Ming(M.Thread))
    class fields(ew_core.NameList):
        num_replies=ew.HTMLField(show_label=True, label='Num Posts')
        num_views=ew.HTMLField(show_label=True)
        last_post=ew.HTMLField(text="${value and value.summary()}", show_label=True)
        subscription=ew.Checkbox(suppress_label=True, show_label=True)
    fields.insert(0, ew.LinkField(
            label='Subject', text="${value['subject']}",
            href="${value['url']()}", show_label=True))

class SubscriptionForm(ew.SimpleForm):
    template='jinja:widgets/subscription_form.html'
    value=None
    threads=None
    show_discussion_email=False
    show_actions=False
    show_subject=False
    allow_create_thread=False
    limit=None
    page=0
    count=0
    submit_text='Update Subscriptions'
    params=['value', 'threads', 'show_actions', 'limit', 'page', 'count',
            'show_discussion_email', 'show_subject', 'allow_create_thread']
    class fields(ew_core.NameList):
        page_list=ffw.PageList()
        page_size=ffw.PageSize()
        threads=_ThreadsTable()
    def resources(self):
        for r in super(SubscriptionForm, self).resources(): yield r
        yield ew.JSScript('''
        $(window).load(function () {
            $('tbody').children(':even').addClass('even');
            $('.discussion_subscription_form').each(function () {
                var discussion = this;
                var follow_btn = $('.follow', discussion);
                var email_btn = $('.email', discussion);
                var action_holder = $('h2.title small');
                action_holder.append(follow_btn);
                action_holder.append(email_btn);
                follow_btn.show();
                email_btn.show();
                $('.submit', discussion).button();
                follow_btn.click(function (ele) {
                    $('.follow_form', discussion).submit();
                    return false;
                });
            });
        });''')

# Widgets
class HierWidget(ew_core.Widget):
    widgets = {}

    def prepare_context(self, context):
        response = super(HierWidget, self).prepare_context(context)
        response['widgets'] = self.widgets
        for w in self.widgets.values():
            w.parent_widget = self
        return response

    def resources(self):
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r

class Attachment(ew_core.Widget):
    template='jinja:widgets/attachment.html'
    params=['value', 'post']
    value=None
    post=None

class DiscussionHeader(HierWidget):
    template='jinja:widgets/discussion_header.html'
    params=['value']
    value=None
    widgets=dict(
        edit_post=EditPost(submit_text='New Thread'))

class ThreadHeader(HierWidget):
    template='jinja:widgets/thread_header.html'
    params=['value', 'page', 'limit', 'count', 'show_moderate']
    value=None
    page=None
    limit=None
    count=None
    show_moderate=False
    widgets=dict(
        page_list=ffw.PageList(),
        page_size=ffw.PageSize(),
        moderate_thread=ModerateThread(),
        tag_post=TagPost())

class Post(HierWidget):
    template='jinja:widgets/post_widget.html'
    defaults=dict(
        HierWidget.defaults,
        value=None,
        indent=0,
        page=0,
        limit=25,
        show_subject=False,
        suppress_promote=False)
    widgets=dict(
        moderate_post=ModeratePost(),
        edit_post=EditPost(submit_text='Save'),
        attach_post=AttachPost(submit_text='Attach'),
        attachment=Attachment())
    def resources(self):
        for r in super(Post, self).resources(): yield r
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r
        yield ew.JSLink('js/jquery.lightbox_me.js')
        yield ew.JSScript('''
        (function () {
            $('div.discussion-post').each(function () {
                var post = this;
                $('.submit', post).button();
                $('.flag_post, .delete_post', post).click(function (ele) {
                    this.parentNode.submit();
                    return false;
                });
                if($('a.edit_post', post)){
                    $('a.edit_post', post).click(function (ele) {
                        $('.display_post', post).hide();
                        $('.edit_post_form', post).show();
                        $('.edit_post_form textarea', post).focus();
                        return false;
                    });
                    $("a.cancel_edit_post", post).click(function(evt){
                        $('.display_post', post).show();
                        $('.edit_post_form', post).hide();
                    });
                }
                if($('.reply_post', post)){
                    $('.reply_post', post).click(function (ele) {
                        $('.reply_post_form', post).show();
                        $('.reply_post_form textarea', post).focus();
                        return false;
                    });
                    $('.reply_post', post).button();
                }
                if($('.add_attachment', post)){
                    $('.add_attachment', post).click(function (ele) {
                        $('.add_attachment_form', post).show();
                        return false;
                    });
                }
                if($('.promote_to_thread', post)){
                    $('.promote_to_thread', post).click(function (ele) {
                        $('.promote_to_thread_form', post).show();
                        return false;
                    });
                }
                if($('.shortlink', post)){
                    var popup = $('.shortlink_popup', post);
                    $('.shortlink', post).click(function(evt){
                        evt.preventDefault();
                        popup.lightbox_me();
                        $('input', popup).select();
                    });
                    $('.close', popup).bind('click', function() {
                        popup.hide();
                    });
                }
            });
        }());
        ''')

class PostThread(ew_core.Widget):
    template='jinja:widgets/post_thread.html'
    defaults=dict(
        ew_core.Widget.defaults,
        value=None,
        indent=0,
        page=0,
        limit=25,
        show_subject=False,
        suppress_promote=False,
        parent=None)

class Thread(HierWidget):
    template='jinja:widgets/thread_widget.html'
    name='thread'
    defaults=dict(
        HierWidget.defaults,
        value=None,
        page=None,
        limit=50,
        count=None,
        show_subject=False,
        new_post_text='+ New Comment')
    widgets=dict(
        page_list=ffw.PageList(),
        thread_header=ThreadHeader(),
        post_thread=PostThread(),
        post=Post(),
        edit_post=EditPost(submit_text='Submit'))
    def resources(self):
        for r in super(Thread, self).resources(): yield r
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r
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
                        mod_thread_form.show();
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
                    thread_tag[0].style.display='block';
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

class Discussion(HierWidget):
    template='jinja:widgets/discussion.html'
    defaults=dict(
        HierWidget.defaults,
        value=None,
        threads=None,
        show_discussion_email=False,
        show_subject=False,
        allow_create_thread=False)
    widgets=dict(
        discussion_header=DiscussionHeader(),
        edit_post=EditPost(submit_text='New Topic'),
        subscription_form=SubscriptionForm())
    
    def resources(self):
        for r in super(Discussion, self).resources(): yield r
