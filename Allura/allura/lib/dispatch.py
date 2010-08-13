assert False, 'This module is obsolete'

from webob import exc

def default(func):
    class TempController(object):
        def __init__(self, controller):
            self.controller = controller
        def default(self, *args, **kwargs):
            return func(self.controller, *args, **kwargs)
    if hasattr(func, 'decoration'):
        TempController.default.im_func.decoration = func.decoration
    def _lookup(self, *remainder):
        remainder = [ 'default' ] + list(remainder)
        return TempController(self), remainder
    return _lookup

def _dispatch(self, state, remainder):
    stack = []
    current_controller = state.controller
    while True:
        if hasattr(current_controller, '_check_security'):
            current_controller._check_security()
        # Check for index method
        if not remainder:
            if self._is_exposed(current_controller, 'index'):
                state.add_method(current_controller.index, remainder)
                return state
            else:
                raise exc.HTTPNotFound
        next = remainder.pop(0)
        # Check exposed method
        if self._is_exposed(current_controller, next):
            state.add_method(
                getattr(current_controller, next), remainder)
            return state
        # Check subcontroller
        stack.append((current_controller, remainder))
        try:
            current_controller = getattr(current_controller, next)
            state.add_controller(next, current_controller)
        except AttributeError, err:
            handler, remainder, stack = _find_error_handler(stack)
            if not handler:
                raise exc.HTTPNotFound
            current_controller, remainder = handler(next, *remainder)
            state.add_controller(next, current_controller)
            remainder = list(remainder)

def _find_error_handler(stack):
    while stack:
        cur, remainder = stack.pop()
        if hasattr(cur, '_lookup'):
            return cur._lookup, remainder, stack
    return None, [], []
