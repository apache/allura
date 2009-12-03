class ConsumerDecoration(object):

    def __init__(self, func):
        self.func = func
        self.audit_keys = set()
        self.react_keys = set()

    @classmethod
    def get_decoration(cls, func, create=True):
        if create and not hasattr(func, 'consumer_decoration'):
            func.consumer_decoration = cls(func)
        return getattr(func, 'consumer_decoration', None)

class audit(object):

    def __init__(self, *binding_keys):
        self.binding_keys = binding_keys

    def __call__(self, func):
        deco = ConsumerDecoration.get_decoration(func)
        for bk in self.binding_keys:
            deco.audit_keys.add(bk)
        return func

class react(object):

    def __init__(self, *binding_keys):
        self.binding_keys = binding_keys

    def __call__(self, func):
        deco = ConsumerDecoration.get_decoration(func)
        for bk in self.binding_keys:
            deco.react_keys.add(bk)
        return func
        
