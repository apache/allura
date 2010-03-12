from pylons import c
from formencode import validators as fev

import ew

from pyforge.lib import validators as V
from pyforge.lib.widgets import discuss as DW

from forgeforum import model as M

class _ForumSummary(ew.Widget):
    template='forgeforum.widgets.templates.forum_summary'
    params=['value', 'show_label', 'label', 'name']
    name=None
    value=None
    show_label = True
    label=None

class _ForumsTable(ew.TableField):
    class hidden_fields(ew.WidgetsList):
        _id=ew.HiddenField(validator=V.Ming(M.ForumThread))
    class fields(ew.WidgetsList):
        num_topics=ew.HTMLField(show_label=True, label='Topics')
        num_posts=ew.HTMLField(show_label=True, label='Posts')
        last_post=ew.HTMLField(text="${value and value.summary()}",
                               show_label=True)
        subscribed=ew.Checkbox(suppress_label=True, show_label=True)
    fields.insert(0, _ForumSummary())

class ForumSubscriptionForm(ew.SimpleForm):
    class fields(ew.WidgetsList):
        forums=_ForumsTable()
    submit_text='Update Subscriptions'

class _ThreadsTable(DW._ThreadsTable):
    class fields(ew.WidgetsList):
        num_replies=ew.HTMLField(show_label=True, label='Num Replies')
        num_views=ew.HTMLField(show_label=True)
        flags=ew.HTMLField(show_label=True, text="${unicode(', '.join(value))}")
        last_post=ew.HTMLField(text="${value and value.summary()}", show_label=True)
        subscription=ew.Checkbox(suppress_label=True, show_label=True)
    fields.insert(0, ew.LinkField(
            label='Subject', text="${value['subject']}",
            href="${value['url']()}", show_label=True))

class ThreadSubscriptionForm(DW.SubscriptionForm):
    class fields(ew.WidgetsList):
        threads=_ThreadsTable()

class AnnouncementsTable(DW._ThreadsTable):
    class fields(ew.WidgetsList):
        num_replies=ew.HTMLField(show_label=True, label='Num Replies')
        num_views=ew.HTMLField(show_label=True)
        flags=ew.HTMLField(show_label=True, text="${unicode(', '.join(value))}")
        last_post=ew.HTMLField(text="${value and value.summary()}", show_label=True)
    fields.insert(0, ew.LinkField(
            label='Subject', text="${value['subject']}",
            href="${value['url']()}", show_label=True))
    name='announcements'
    
class _ForumSelector(ew.SingleSelectField):
    def _options(self):
        return [
            ew.Option(label=f.name, py_value=f, html_value=f.shortname)
            for f in c.app.forums ]
    def to_python(self, value, state):
        result = M.Forum.query.get(shortname=value)
        if not result:
            raise fev.Invalid('Illegal forum shortname: %s' % value, value, state)
        return result
    def from_python(self, value, state):
        return value.shortname

class ModerateThread(ew.SimpleForm):
    submit_text='Save Changes'
    class fields(ew.WidgetsList):
        forum=_ForumSelector(label='New Forum')
        flags=ew.CheckboxSet(options=['Sticky', 'Announcement'])
    class buttons(ew.WidgetsList):
        delete=ew.SubmitButton(label='Delete Thread')

class ModeratePost(ew.SimpleForm):
    submit_text=None
    fields=[
        ew.FieldSet(legend='Promote post to its own thread', fields=[
                ew.TextField(name='subject', label='Thread title'),
                ew.SubmitButton(name='promote', label='Promote to thread')])]
    class buttons(ew.WidgetsList):
        spam=ew.SubmitButton(label='Spam Post')
        delete=ew.SubmitButton(label='Delete Post')

class ForumHeader(DW.DiscussionHeader):
    template='forgeforum.widgets.templates.forum_header'
    widgets=dict(DW.DiscussionHeader.widgets,
                 announcements_table=AnnouncementsTable(),
                 forum_subscription_form=ForumSubscriptionForm())

class ThreadHeader(DW.ThreadHeader):
    template='forgeforum.widgets.templates.thread_header'
    show_subject=True
    show_moderate=True
    widgets=dict(DW.ThreadHeader.widgets,
                 moderate_thread=ModerateThread(),
                 announcements_table=AnnouncementsTable())

class Post(DW.Post):
    show_subject=True
    widgets=dict(DW.Post.widgets,
                 moderate_post=ModeratePost())

class Thread(DW.Thread):
    params=['show_subject']
    show_subject=True
    widgets=dict(DW.Thread.widgets,
                 thread_header=ThreadHeader(),
                 post=Post())

class Forum(DW.Discussion):
    allow_create_thread=True
    show_discussion_email = True
    show_subject = True
    widgets=dict(DW.Discussion.widgets,
                 discussion_header=ForumHeader(),
                 forum_subscription_form=ForumSubscriptionForm(),
                 subscription_form=ThreadSubscriptionForm()
                 )
