import json
from bson import ObjectId
import formencode as fe
from formencode import validators as fev
from . import helpers as h
from datetime import datetime

class Ming(fev.FancyValidator):

    def __init__(self, cls, **kw):
        self.cls = cls
        super(Ming, self).__init__(**kw)

    def _to_python(self, value, state):
        result = self.cls.query.get(_id=value)
        if result is None:
            try:
                result = self.cls.query.get(_id=ObjectId(value))
            except:
                pass
        return result

    def _from_python(self, value, state):
        return value._id

class UniqueOAuthApplicationName(fev.UnicodeString):

    def _to_python(self, value, state):
        from allura import model as M
        app = M.OAuthConsumerToken.query.get(name=value)
        if app is not None:
            raise fe.Invalid('That name is already taken, please choose another', value, state)
        return value

class NullValidator(fev.Validator):

    def to_python(self, value, state):
        return value

    def from_python(self, value, state):
        return value

    def validate(self, value, state):
        return value

class MaxBytesValidator(fev.FancyValidator):
    max=255

    def _to_python(self, value, state):
        value = h.really_unicode(value or '').encode('utf-8')
        if len(value) > self.max:
            raise fe.Invalid("Please enter a value less than %s bytes long." % self.max, value, state)
        return value

    def from_python(self, value, state):
        return h.really_unicode(value or '')

class JsonValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        try:
            json.loads(value)
        except ValueError, e:
            raise fe.Invalid('Invalid JSON: ' + str(e), value, state)
        return value

class DateValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        value = convertDate(value)
        if not value:
            raise fe.Invalid(
                "Please enter a valid date in the format DD/MM/YYYY.",
                value, state)
        return value

class TimeValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        value = convertTime(value)
        if not value:
            raise fe.Invalid(
                "Please enter a valid time in the format HH:MM.",
                value, state)
        return value

class OneOfValidator(fev.FancyValidator):
    def __init__(self, validvalues, not_empty = True):
        self.validvalues = validvalues
        self.not_empty = not_empty
        super(OneOfValidator, self).__init__()

    def _to_python(self, value, state):
        if not value.strip():
            if self.not_empty:
                raise fe.Invalid("This field can't be empty.", value, state)
            else:
                return None
        if not value in self.validvalues:
            allowed = ''
            for v in self.validvalues:
                if allowed != '':
                    allowed = allowed + ', '
                allowed = allowed + '"%s"' % v
            raise fe.Invalid(
                "Invalid value. The allowed values are %s." %allowed,
                value, state)
        return value

class MapValidator(fev.FancyValidator):
    def __init__(self, mapvalues, not_empty = True):
        self.map = mapvalues
        self.not_empty = not_empty
        super(MapValidator, self).__init__()

    def _to_python(self, value, state):
        if not value.strip():
            if self.not_empty:
                raise fe.Invalid("This field can't be empty.", value, state)
            else:
                return None
        conv_value = self.map.get(value)
        if not conv_value:
            raise fe.Invalid(
                "Invalid value. Please, choose one of the valid values.",
                value, state)
        return conv_value

def convertDate(datestring):
    formats = ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', '%Y\%m\%d', '%Y %m %d',
               '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%Y', '%d\%m\%Y', '%d %m %Y']

    for f in formats:
        try:
            date = datetime.strptime(datestring, f)       
            return date
        except:
            pass
    return None

def convertTime(timestring):
    formats = ['%H:%M', '%H.%M', '%H %M', '%H,%M']

    for f in formats:
        try:
            time = datetime.strptime(timestring, f)       
            return {'h':time.hour, 'm':time.minute}
        except:
            pass
    return None
