from pylons import tmpl_context as c
from formencode import validators as fev
import ew as ew_core
import ew.jinja2_ew as ew


class FollowToggle(ew.SimpleForm):
    template='jinja:forgeactivity:templates/widgets/follow.html'
    defaults=dict(
        ew.SimpleForm.defaults,
        thing='project',
        action='follow',
        action_label='watch',
        icon='watch',
        following=False)

    class fields(ew_core.NameList):
        follow = ew.HiddenField(validator=fev.StringBool())

    def resources(self):
        yield ew.JSLink('activity_js/follow.js')

    def prepare_context(self, context):
        default_context = super(FollowToggle, self).prepare_context({})
        if c.project.is_user_project:
            default_context.update(
                thing=c.project.user_project_of.display_name,
                action_label='follow',
                icon='star',
            )
        else:
            default_context.update(thing=c.project.name)
        default_context.update(context)
        return default_context

    def success_message(self, following):
        context = self.prepare_context({})
        return u'You are {state} {action}ing {thing}.'.format(
            state='now' if following else 'no longer',
            action=context['action_label'],
            thing=context['thing'],
        )
