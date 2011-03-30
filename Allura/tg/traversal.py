'''Code to support pylons-style traversal on top of TG-style _lookup'''
from decorators import Decoration

class Resource(object):

    def __init__(self, controller):
        self._controller = controller
        sec = getattr(controller, '_check_security', lambda:None)
        sec()

    def __getitem__(self, name):
        name = name.encode('utf-8')
        remainder = []
        next = getattr(self._controller, name, None)
        if next is None:
            try:
                next, remainder = self._controller._lookup(name)
            except TypeError, te:
                if 'takes at least' not in te.args[0]: raise
                return CurriedResource(self._controller, [name])
        assert not remainder, 'Weird _lookup not supported'
        return Resource(next)

    def get_deco(self):
        func = self._controller
        deco = Decoration.get(func, False)
        if deco is None:
            func = getattr(func, 'index', None)
            deco = Decoration.get(func, False)
        return deco, func

class CurriedResource(object):

    def __init__(self, controller, path):
        self._controller = controller
        self._path = path

    def __getitem__(self, name):
        new_path = self._path + [name]
        try:
            next, remainder = self._controller._lookup(*new_path)
            assert not remainder, 'Weird _lookup not supported'
            return Resource(next)
        except TypeError, te:
            if 'takes at least' not in te.args[0]: raise
            return CurriedResource(self._controller, new_path)
