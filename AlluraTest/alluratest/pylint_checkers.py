import astroid

from pylint.checkers import BaseChecker, utils
from pylint.interfaces import IAstroidChecker


def register(linter):
    linter.register_checker(ExposedAPIHasKwargs(linter))


# FIXME?
BASE_ID = 76  # taken from https://github.com/edx/edx-lint/tree/master/edx_lint/pylint

class ExposedAPIHasKwargs(BaseChecker):

    __implements__ = (IAstroidChecker,)

    name = 'exposed-api-needs-kwargs'

    MESSAGE_ID = name
    msgs = {
        'E%d10' % BASE_ID: (
            "@expose'd method %s() looks like an API and needs **kwargs",
            MESSAGE_ID,
            "@expose'd API methods should have **kwargs to avoid an error when accessed with ?access_token=XYZ",
        ),
    }

    @utils.check_messages(MESSAGE_ID)
    def visit_function(self, node):
        # special TurboGears method name, doesn't need **kw
        if node.name == '_lookup':
            return

        # Assume @expose('json:') means its an API endpoint.  Not a perfect assumption:
        #  - could be an API endpoint used only for PUT/POST with no json result)
        #  - there are non-API endpoints that return json (for ajax)
        has_json_expose = False
        if node.decorators:
            for dec in node.decorators.nodes:
                if hasattr(dec, 'func'):  # otherwise its a @deco without parens
                    if getattr(dec.func, 'name', '') == 'expose':
                        for arg in dec.args:
                            if getattr(arg, 'value', '') in ('json', 'json:'):
                                has_json_expose = True

        if not has_json_expose:
            return

        if node.args.kwarg:
            return

        if not self.linter.is_message_enabled(self.MESSAGE_ID, line=node.fromlineno):
            return

        self.add_message(self.MESSAGE_ID, args=node.name, node=node)
