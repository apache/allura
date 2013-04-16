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

class TaskValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        try:
            mod, func = value.rsplit('.', 1)
        except ValueError:
            raise fe.Invalid('Invalid task name. Please provide the full '
                    'dotted path to the python callable.', value, state)
        try:
            mod = __import__(mod, fromlist=[str(func)])
        except ImportError:
            raise fe.Invalid('Could not import "%s"' % value, value, state)

        try:
            task = getattr(mod, func)
        except AttributeError:
            raise fe.Invalid('Module has no attribute "%s"' % func, value, state)

        if not hasattr(task, 'post'):
            raise fe.Invalid('"%s" is not a task.' % value, value, state)
        return task

class UserValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        from allura import model as M
        user = M.User.by_username(value)
        if not user:
            raise fe.Invalid('Invalid username', value, state)
        return user

class PathValidator(fev.FancyValidator):
    def _to_python(self, value, state):
        from allura import model as M

        parts = value.strip('/').split('/')
        if len(parts) < 2:
            raise fe.Invalid("You must specify at least a neighborhood and "
                "project, i.e. '/nbhd/project'", value, state)
        elif len(parts) == 2:
            nbhd_name, project_name, app_name = parts[0], parts[1], None
        elif len(parts) > 2:
            nbhd_name, project_name, app_name = parts[0], parts[1], parts[2]

        path_parts = {}
        nbhd_url_prefix = '/%s/' % nbhd_name
        nbhd = M.Neighborhood.query.get(url_prefix=nbhd_url_prefix)
        if not nbhd:
            raise fe.Invalid('Invalid neighborhood: %s' % nbhd_url_prefix, value, state)

        project = M.Project.query.get(shortname=project_name, neighborhood_id=nbhd._id)
        if not project:
            raise fe.Invalid('Invalid project: %s' % project_name, value, state)

        path_parts['project'] = project
        if app_name:
            app = project.app_instance(app_name)
            if not app:
                raise fe.Invalid('Invalid app mount point: %s' % app_name, value, state)
            path_parts['app'] = app

        return path_parts

class JsonValidator(fev.FancyValidator):
    """Validates a string as JSON and returns the original string"""
    def _to_python(self, value, state):
        try:
            json.loads(value)
        except ValueError, e:
            raise fe.Invalid('Invalid JSON: ' + str(e), value, state)
        return value

class JsonConverter(fev.FancyValidator):
    """Deserializes a string to JSON and returns a Python object"""
    def _to_python(self, value, state):
        try:
            obj = json.loads(value)
        except ValueError, e:
            raise fe.Invalid('Invalid JSON: ' + str(e), value, state)
        return obj

class CreateTaskSchema(fe.Schema):
    task = TaskValidator(not_empty=True, strip=True)
    task_args = JsonConverter(if_missing=dict(args=[], kwargs={}))
    user = UserValidator(strip=True, if_missing=None)
    path = PathValidator(strip=True, if_missing={}, if_empty={})

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
