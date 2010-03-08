from formencode import validators as fev

class Ming(fev.FancyValidator):

    def __init__(self, cls, **kw):
        self.cls = cls
        super(Ming, self).__init__(**kw)

    def _to_python(self, value, state):
        return self.cls.query.get(_id=value)

    def _from_python(self, value, state):
        return value._id
