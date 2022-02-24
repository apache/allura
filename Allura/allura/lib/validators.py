#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

import json
import re
from bson import ObjectId
import formencode as fe
from formencode import validators as fev
from tg import tmpl_context as c
from . import helpers as h
from datetime import datetime
import six
from urllib.parse import urlparse
from ipaddress import ip_address
import socket


class URL(fev.URL):
    # allows use of IP address instead of domain name
    require_tld = False

    url_re = re.compile(r'''
        ^(http|https)://
        (?:[%:\w]*@)?                              # authenticator
        (?:                                        # ip or domain
        (?P<ip>(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))|
        (?P<domain>[a-z0-9][a-z0-9\-]{,62}\.)*     # subdomain
        (?P<tld>[a-z]{2,63}|xn--[a-z0-9\-]{2,59})  # top level domain
        )
        (?::[0-9]{1,5})?                           # port
        # files/delims/etc
        (?P<path>/[a-z0-9\-\._~:/\?#\[\]@!%\$&\'\(\)\*\+,;=]*)?
        $
    ''', re.I | re.VERBOSE)


class URLIsPrivate(URL):

    def _to_python(self, value, state):
        value = super(URLIsPrivate, self)._to_python(value, state)
        url_components = urlparse(value)
        try:
            host_ip = socket.gethostbyname(url_components.netloc)
        except socket.gaierror:
            raise fev.Invalid("Invalid URL.", value, state)
        parse_ip = ip_address(host_ip)
        if parse_ip and parse_ip.is_private:
            raise fev.Invalid("Invalid URL.", value, state)
        return value


class NonHttpUrl(URL):
    messages = {
        'noScheme': 'You must start your URL with a scheme',
    }
    add_http = False
    scheme_re = re.compile(r'^[a-z][a-z0-9.+-]*:', re.I)
    url_re = re.compile(r'''
        ^([a-z][a-z0-9.+-]*)://
        (?:[%:\w]*@)?                              # authenticator
        (?:                                        # ip or domain
        (?P<ip>(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))|
        (?P<domain>[a-z0-9][a-z0-9\-]{,62}\.)*     # subdomain
        (?P<tld>[a-z]{2,63}|xn--[a-z0-9\-]{2,59})  # top level domain
        )
        (?::[0-9]{1,5})?                           # port
        # files/delims/etc
        (?P<path>/[a-z0-9\-\._~:/\?#\[\]@!%\$&\'\(\)\*\+,;=]*)?
        $
    ''', re.I | re.VERBOSE)


class UnicodeString(fev.UnicodeString):
    """
    Override UnicodeString to fix bytes handling.
    Specifically ran into problems with its 'tooLong' check is running on bytes incorrectly and getting wrong length
    And sometimes would return b'foo' when we wanted 'foo'

    Fixed elsewhere like this too:
        https://github.com/formencode/formencode/issues/2#issuecomment-378410047
        https://github.com/sightmachine/formencode/commit/665c9d0141dacb2dc84fb7d20ad3f8c0a5fe5e2d
    """
    encoding = None


# make UnicodeString fix above work through this String alias, just like formencode aliases String
String = UnicodeString if str is str else fev.ByteString


class Ming(fev.FancyValidator):

    def __init__(self, cls, **kw):
        self.cls = cls
        super().__init__(**kw)

    def _to_python(self, value, state):
        result = self.cls.query.get(_id=value)
        if result is None:
            try:
                result = self.cls.query.get(_id=ObjectId(value))
            except Exception:
                pass
        return result

    def _from_python(self, value, state):
        if isinstance(value, ObjectId):
            return value
        else:
            return value._id


class UniqueOAuthApplicationName(UnicodeString):

    def _to_python(self, value, state):
        from allura import model as M
        app = M.OAuthConsumerToken.query.get(name=value, user_id=c.user._id)
        if app is not None:
            raise fe.Invalid(
                'That name is already taken, please choose another', value, state)
        return value


class NullValidator(fev.Validator):

    def to_python(self, value, state):
        return value

    def from_python(self, value, state):
        return value

    def validate(self, value, state):
        return value


class MaxBytesValidator(fev.FancyValidator):
    max = 255

    def _to_python(self, value, state):
        value_bytes = h.really_unicode(value or '').encode('utf-8')
        if len(value_bytes) > self.max:
            raise fe.Invalid("Please enter a value less than %s bytes long." %
                             self.max, value, state)
        return value

    def from_python(self, value, state):
        return h.really_unicode(value or '')


class MountPointValidator(UnicodeString):

    def __init__(self, app_class,
                 reserved_mount_points=('feed', 'index', 'icon', '_nav.json'), **kw):
        super(self.__class__, self).__init__(**kw)
        self.app_class = app_class
        self.reserved_mount_points = reserved_mount_points

    def _to_python(self, value, state):
        mount_point, App = value, self.app_class
        if not App.relaxed_mount_points:
            mount_point = mount_point.lower()
        if not App.validate_mount_point(mount_point):
            raise fe.Invalid('Mount point "%s" is invalid' % mount_point,
                             value, state)
        if mount_point in self.reserved_mount_points:
            raise fe.Invalid('Mount point "%s" is reserved' % mount_point,
                             value, state)
        if c.project and c.project.app_instance(mount_point) is not None:
            raise fe.Invalid(
                'Mount point "%s" is already in use' % mount_point,
                value, state)
        return mount_point

    def empty_value(self, value):
        base_mount_point = mount_point = self.app_class.default_mount_point
        i = 0
        while True:
            if not c.project or c.project.app_instance(mount_point) is None:
                return mount_point
            mount_point = base_mount_point + '-%d' % i
            i += 1


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
            raise fe.Invalid('Module has no attribute "%s"' %
                             func, value, state)

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


class AnonymousValidator(fev.FancyValidator):

    def _to_python(self, value, state):
        from allura.model import User
        if value:
            if c.user == User.anonymous():
                raise fe.Invalid('Log in to Mark as Private', value, state)
            else:
                return value


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
            raise fe.Invalid('Invalid neighborhood: %s' %
                             nbhd_url_prefix, value, state)

        project = M.Project.query.get(
            shortname=nbhd.shortname_prefix + project_name,
            neighborhood_id=nbhd._id)
        if not project:
            raise fe.Invalid('Invalid project: %s' %
                             project_name, value, state)

        path_parts['project'] = project
        if app_name:
            app = project.app_instance(app_name)
            if not app:
                raise fe.Invalid('Invalid app mount point: %s' %
                                 app_name, value, state)
            path_parts['app'] = app

        return path_parts


class JsonValidator(fev.FancyValidator):

    """Validates a string as JSON and returns the original string"""

    def _to_python(self, value, state):
        try:
            json.loads(value)
        except ValueError as e:
            raise fe.Invalid('Invalid JSON: ' + str(e), value, state)
        return value


class JsonConverter(fev.FancyValidator):

    """
    Deserializes a string to JSON and returns a Python object
    Must be an object, not a simple literal
    """

    def _to_python(self, value, state):
        try:
            obj = json.loads(value)
        except ValueError as e:
            raise fe.Invalid('Invalid JSON: ' + str(e), value, state)
        if not isinstance(obj, dict):
            raise fe.Invalid('Not a dict (JSON object)', value, state)
        return obj


class JsonFile(fev.FieldStorageUploadConverter):

    """Validates that a file is JSON and returns the deserialized Python object

    """

    def _to_python(self, value, state):
        return JsonConverter.to_python(value.value)


class UserMapJsonFile(JsonFile):

    """Validates that a JSON file conforms to this format:

    {str:str, ...}

    and returns a deserialized or stringified copy of it.

    """

    def __init__(self, as_string=False):
        self.as_string = as_string

    def _to_python(self, value, state):
        value = super(self.__class__, self)._to_python(value, state)
        try:
            for k, v in value.items():
                if not(isinstance(k, str) and isinstance(v, str)):
                    raise
            return json.dumps(value) if self.as_string else value
        except Exception:
            raise fe.Invalid(
                'User map file must contain mapping of {str:str, ...}',
                value, state)


class CreateTaskSchema(fe.Schema):
    task = TaskValidator(not_empty=True, strip=True)
    task_args = JsonConverter(if_missing=dict(args=[], kwargs={}))
    user = UserValidator(strip=True, if_missing=None)
    path = PathValidator(strip=True, if_missing={}, if_empty={})


class CreateSiteNotificationSchema(fe.Schema):
    active = fev.StringBool(if_missing=False)
    impressions = fev.Int(not_empty=True)
    content = UnicodeString(not_empty=True)
    user_role = fev.FancyValidator(not_empty=False, if_empty=None)
    page_regex = fev.FancyValidator(not_empty=False, if_empty=None)
    page_tool_type = fev.FancyValidator(not_empty=False, if_empty=None)


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

    def __init__(self, validvalues, not_empty=True):
        self.validvalues = validvalues
        self.not_empty = not_empty
        super().__init__()

    def _to_python(self, value, state):
        if not value.strip():
            if self.not_empty:
                raise fe.Invalid("This field can't be empty.", value, state)
            else:
                return None
        if value not in self.validvalues:
            allowed = ''
            for v in self.validvalues:
                if allowed != '':
                    allowed = allowed + ', '
                allowed = allowed + '"%s"' % v
            raise fe.Invalid(
                "Invalid value. The allowed values are %s." % allowed,
                value, state)
        return value


class MapValidator(fev.FancyValidator):

    def __init__(self, mapvalues, not_empty=True):
        self.map = mapvalues
        self.not_empty = not_empty
        super().__init__()

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


class YouTubeConverter(fev.FancyValidator):
    """Takes a given YouTube URL. Ensures that the video_id
    is contained in the URL. Returns a clean URL to use for iframe embedding.

    REGEX: http://stackoverflow.com/a/10315969/25690
    """

    REGEX = (r'^(?:https?:\/\/)?(?:www\.)?' +
             r'(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=))' +
             r'((\w|-){11})(?:\S+)?$')

    def _to_python(self, value, state):
        match = re.match(YouTubeConverter.REGEX, value)
        if match:
            video_id = match.group(1)
            return f'www.youtube.com/embed/{video_id}?rel=0'
        else:
            raise fe.Invalid(
                "The URL does not appear to be a valid YouTube video.",
                value, state)


def convertDate(datestring):
    formats = ['%Y-%m-%d', '%Y.%m.%d', '%Y/%m/%d', r'%Y\%m\%d', '%Y %m %d',
               '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%Y', r'%d\%m\%Y', '%d %m %Y']

    for f in formats:
        try:
            date = datetime.strptime(datestring, f)
            return date
        except Exception:
            pass
    return None


def convertTime(timestring):
    formats = ['%H:%M', '%H.%M', '%H %M', '%H,%M']

    for f in formats:
        try:
            time = datetime.strptime(timestring, f)
            return {'h': time.hour, 'm': time.minute}
        except Exception:
            pass
    return None


class IconValidator(fev.FancyValidator):
    regex = '(jpg|jpeg|gif|png|bmp)$'

    def _to_python(self, value, state):
        p = re.compile(self.regex, flags=re.I)
        result = p.search(value.filename)

        if not result:
            raise fe.Invalid(
                'Project icons must be PNG, GIF, JPG, or BMP format.',
                value, state)

        return value
