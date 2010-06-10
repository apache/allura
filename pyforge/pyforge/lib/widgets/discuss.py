from pylons import c

import ew

from pyforge.lib import validators as V
from pyforge.lib import helpers as h
from pyforge.lib.widgets import form_fields as ffw
from pyforge import model as M

# Discussion forms
class ModerateThread(ew.SimpleForm):
    class buttons(ew.WidgetsList):
        delete=ew.SubmitButton(label='Delete Thread')
    submit_text=None

class ModeratePost(ew.SimpleForm):
    template='genshi:pyforge.lib.widgets.templates.moderate_post'
    submit_text=None

class FlagPost(ew.SimpleForm):
    template='genshi:pyforge.lib.widgets.templates.flag_post'
    submit_text=None

class AttachPost(ew.SimpleForm):
    submit_text='Attach File'
    enctype='multipart/form-data'
    class fields(ew.WidgetsList):
        file_info=ew.InputField(field_type='file')

class ModeratePosts(ew.SimpleForm):
    template='genshi:pyforge.lib.widgets.templates.moderate_posts'
    submit_text=None
    def resources(self):
        for r in super(ModeratePosts, self).resources(): yield r
        yield ew.JSScript('''
      (function($){
          var tbl = $('form table');
          var checkboxes = $('input[type=checkbox]', tbl);
          $('a[href=#]', tbl).click(function() {
              checkboxes.each(function() {
                  if(this.checked) { this.checked = false; }
                  else { this.checked = true; }
              });
              return false;
          });
      }(jQuery));''')

class PostFilter(ew.SimpleForm):
    submit_text=None
    method='GET'
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

class TagPost(ew.SimpleForm):

    # this ickiness is to override the default submit button
    def __call__(self, **kw):
        result = super(TagPost, self).__call__(**kw)
        submit_button = ffw.SubmitButton(label=result['submit_text'])
        result['extra_fields'] = [submit_button]
        result['buttons'] = [submit_button]
        return result

    fields=[ffw.LabelEdit(label='Tags',name='labels', className='title')]

    def resources(self):
        for r in ffw.LabelEdit(name='labels').resources(): yield r

class EditPost(ew.SimpleForm):
    show_subject=False
    value=None
    template='pyforge.lib.widgets.templates.edit_post'
    params=['value']

    @property
    def fields(self):
        def _():
            if getattr(c, 'widget', '') != '':
                if c.widget.response.get('show_subject', self.show_subject):
                    yield ew.TextField(name='subject')
            else:
                yield ew.TextField(name='subject', if_missing=None)
            yield ffw.MarkdownEdit(name='text')
        return _()

    def resources(self):
        for r in ew.TextField(name='subject').resources(): yield r
        for r in ffw.MarkdownEdit(name='text').resources(): yield r

class _ThreadsTable(ew.SimpleForm):
    template='pyforge.lib.widgets.templates.threads_table'
    class hidden_fields(ew.WidgetsList):
        _id=ew.HiddenField(validator=V.Ming(M.Thread))
    class fields(ew.WidgetsList):
        num_replies=ew.HTMLField(show_label=True, label='Num Posts')
        num_views=ew.HTMLField(show_label=True)
        last_post=ew.HTMLField(text="${value and value.summary()}", show_label=True)
        subscription=ew.Checkbox(suppress_label=True, show_label=True)
    fields.insert(0, ew.LinkField(
            label='Subject', text="${value['subject']}",
            href="${value['url']()}", show_label=True))

class SubscriptionForm(ew.SimpleForm):
    template='pyforge.lib.widgets.templates.subscription_form'
    value=None
    show_discussion_email=False
    show_subject=False
    allow_create_thread=False
    params=['value',
            'show_discussion_email', 'show_subject', 'allow_create_thread']
    class fields(ew.WidgetsList):
        threads=_ThreadsTable()
        new_topic = EditPost(submit_text='New Topic', if_missing=None)
    submit_text='Update Subscriptions'
    def resources(self):
        for r in super(SubscriptionForm, self).resources(): yield r
        yield ew.JSScript('''
        $(window).load(function() {
            $('tbody').children(':even').addClass('even');
            $('.discussion_subscription_form').each(function(){
                var discussion = this;
                $('.submit', discussion).button();
                if($('.new_topic', discussion)){
                    $('.new_topic', discussion).click(function(ele){
                        $('.new_topic_form', discussion).show();
                        return false;
                    });
                }
                $('.follow', discussion).click(function(ele){
                    $('.follow_form', discussion).submit();
                    return false;
                });
            });
        });''')

# Widgets
class HierWidget(ew.Widget):
    widgets = {}

    def __call__(self, **kw):
        response = super(HierWidget, self).__call__(**kw)
        response['widgets'] = self.widgets
        return response

    def resources(self):
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r

class Attachment(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.attachment'
    params=['value', 'post']
    value=None
    post=None

class DiscussionHeader(HierWidget):
    template='genshi:pyforge.lib.widgets.templates.discussion_header'
    params=['value']
    value=None
    widgets=dict(
        edit_post=EditPost(submit_text='New Thread'))

class ThreadHeader(HierWidget):
    template='genshi:pyforge.lib.widgets.templates.thread_header'
    params=['value', 'offset', 'pagesize', 'total', 'show_moderate']
    value=None
    offset=None
    pagesize=None
    total=None
    show_moderate=False
    widgets=dict(
        moderate_thread=ModerateThread())

class PostHeader(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.post_header'
    params=['value']
    value=None

class PostThread(ew.Widget):
    template='genshi:pyforge.lib.widgets.templates.post_thread'
    params=['value']
    value=None

class Post(HierWidget):
    template='genshi:pyforge.lib.widgets.templates.post'
    params=['value', 'show_subject', 'indent', 'supress_promote']
    value=None
    indent=0
    show_subject=False
    supress_promote=False
    widgets=dict(
        flag_post=FlagPost(),
        moderate_post=ModeratePost(),
        edit_post=EditPost(submit_text='Edit Post'),
        attach_post=AttachPost(submit_text='Attach'),
        attachment=Attachment())
    def resources(self):
        for r in super(Post, self).resources(): yield r
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r
        yield ew.JSScript('''
        (function(){
            $('div.discussion-post').each(function(){
                var post = this;
                $('.submit', post).button();
                $('.flag_post, .delete_post', post).click(function(ele){
                    this.parentNode.submit();
                    return false;
                });
                if($('a.edit_post', post)){
                    $('a.edit_post', post).click(function(ele){
                        $('.display_post', post).hide();
                        $('.edit_post_form', post).show();
                        return false;
                    });
                }
                if($('.reply_post', post)){
                    $('.reply_post', post).click(function(ele){
                        $('.reply_post_form', post).show();
                        $('.reply_post_form textarea', post).focus()
                        return false;
                    });
                    $('.reply_post', post).button();
                }
                if($('.add_attachment', post)){
                    $('.add_attachment', post).click(function(ele){
                        $('.add_attachment_form', post).show();
                        return false;
                    });
                }
                if($('.promote_to_thread', post)){
                    $('.promote_to_thread', post).click(function(ele){
                        $('.promote_to_thread_form', post).show();
                        return false;
                    });
                }
            });
        })();
        ''')

class Thread(HierWidget):
    template='genshi:pyforge.lib.widgets.templates.thread'
    name='thread'
    params=['value', 'offset', 'pagesize', 'total', 'show_subject','new_post_text']
    value=None
    offset=None
    pagesize=None
    total=None
    show_subject=False
    new_post_text="+ New Comment"
    widgets=dict(
        thread_header=ThreadHeader(),
        post_thread=PostThread(),
        post=Post(),
        tag_post=TagPost(),
        edit_post=EditPost(submit_text='Submit'))
    def resources(self):
        for r in super(Thread, self).resources(): yield r
        for w in self.widgets.itervalues():
            for r in w.resources():
                yield r
        yield ew.JSScript('''
        $(document).ready(function(){
            var thread_reply = $('a.sidebar_thread_reply');
            var thread_tag = $('a.sidebar_thread_tag');
            var thread_spam = $('a.sidebar_thread_spam');
            var new_post_holder = $('#new_post_holder');
            var new_post_create = $('#new_post_create');
            var tag_thread_holder = $('#tag_thread_holder');
            var allow_moderate = $('#allow_moderate');
            if(new_post_create){
                new_post_create.click(function(e){
                    new_post_create.hide();
                    new_post_holder.show();
                });
            }
            if(thread_reply.length){
                if(new_post_holder.length){
                    thread_reply[0].style.display='block';
                    thread_reply.click(function(e){
                        new_post_create.hide();
                        new_post_holder.show();
                        // focus the submit to scroll to the bottom, then focus the subject for them to start typing
                        $('input[type="submit"]', new_post_holder).focus();
                        $('input[type="text"]', new_post_holder).focus();
                        return false;
                    });
                }
            }
            if(thread_tag.length){
                if(tag_thread_holder.length){
                    thread_tag[0].style.display='block';
                    thread_tag.click(function(e){
                        tag_thread_holder.show();
                        // focus the submit to scroll to the bottom, then focus the subject for them to start typing
                        $('input[type="submit"]', tag_thread_holder).focus();
                        $('input[type="text"]', tag_thread_holder).focus();
                        return false;
                    });
                }
            }
            if(thread_spam.length){
                if(allow_moderate.length){
                    thread_spam[0].style.display='block';
                }
            }
        });
        ''')

class Discussion(HierWidget):
    template='genshi:pyforge.lib.widgets.templates.discussion'
    params=['value',
            'show_discussion_email', 'show_subject', 'allow_create_thread']
    value=None
    show_discussion_email=False
    show_subject=False
    allow_create_thread=False
    widgets=dict(
        discussion_header=DiscussionHeader(),
        edit_post=EditPost(submit_text='New Topic'),
        subscription_form=SubscriptionForm())
    
    def resources(self):
        for r in super(Discussion, self).resources(): yield r
