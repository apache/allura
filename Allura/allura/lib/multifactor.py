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

import os
import logging
from collections import OrderedDict
from base64 import b32decode, b32encode
from time import time

import bson
import errno
from cryptography.hazmat.primitives.twofactor import InvalidToken

from tg import config
from pylons import app_globals as g
from paste.deploy.converters import asint
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.twofactor.totp import TOTP
from cryptography.hazmat.primitives.hashes import SHA1
import qrcode


log = logging.getLogger(__name__)


class TotpService(object):
    '''
    An interface for handling multifactor auth TOTP secret keys.  Common functionality
    is provided in this base class, and specific subclasses implement different storage options.
    A provider must implement :meth:`get_secret_key` and :meth:`set_secret_key`.

    To use a new provider, expose an entry point in setup.py::

        [allura.multifactor.totp_service]
        mytotp = foo.bar:MyTotpService

    Then in your .ini file, set ``auth.multifactor.totp.service=mytotp``
    '''

    @classmethod
    def get(cls):
        method = config.get('auth.multifactor.totp.service', 'mongodb')
        return g.entry_points['multifactor_totp'][method]()

    def Totp(self, key):
        # simple constructor helper

        if not key:
            key = os.urandom(20)  # == 160 bytes which is recommended

        totp = TOTP(key,
                    asint(config.get('auth.multifactor.totp.length', 6)),
                    SHA1(),
                    asint(config.get('auth.multifactor.totp.time', 30)),
                    backend=default_backend())

        totp.key = key  # for convenience, else you have to use `totp._hotp._key`

        return totp

    def verify(self, totp, code):
        code = code.replace(' ', '')  # Google authenticator puts a space in their codes
        code = bytes(code)  # can't be unicode

        # TODO prohibit re-use of a successful code, although it seems unlikely with a 30s window
        # see https://tools.ietf.org/html/rfc6238#section-5.2 paragraph 5

        # try the 1 previous time-window and current
        # per https://tools.ietf.org/html/rfc6238#section-5.2 paragraph 1
        windows = asint(config.get('auth.multifactor.totp.windows', 2))
        for time_window in range(windows):
            try:
                return totp.verify(code, time() - time_window*30)
            except InvalidToken:
                last_window = (time_window == windows - 1)
                if last_window:
                    raise

    def get_totp(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param bool generate_new: generate (but does not save) if one does not exist already
        :return:
        '''
        key = self.get_secret_key(user)
        return self.Totp(key)

    def get_qr_code(self, totp, user, **qrcode_params):
        qrcode_params.setdefault('box_size', 5)
        uri = totp.get_provisioning_uri(user.username, config['site_name'])
        qr = qrcode.make(uri, **qrcode_params)
        return qr

    def get_secret_key(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :return: key
        '''
        raise NotImplementedError('get_secret_key')

    def set_secret_key(self, user, key):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :param bytes key: may be `None` to clear out a key
        '''
        raise NotImplementedError('set_secret_key')


class MongodbTotpService(TotpService):
    '''
    Store in TOTP keys in mongodb.
    '''

    def get_secret_key(self, user):
        from allura import model as M
        if user.is_anonymous():
            return None
        record = M.TotpKey.query.get(user_id=user._id)
        if record:
            return record.key

    def set_secret_key(self, user, key):
        from allura import model as M
        if key is not None:
            key = bson.binary.Binary(key)
        M.TotpKey.query.update({'user_id': user._id},
                               {'user_id': user._id, 'key': key},
                               upsert=True)


class GoogleAuthenticatorFile(object):
    '''
    Parse & write server-side .google_authenticator files for PAM.
    https://github.com/google/google-authenticator/blob/master/libpam/FILEFORMAT
    '''

    def __init__(self):
        self.key = None
        self.options = OrderedDict()
        self.recovery_codes = []

    @classmethod
    def load(cls, contents):
        gaf = GoogleAuthenticatorFile()
        lines = contents.split('\n')
        b32key = lines[0]
        padding = '=' * (-len(b32key) % 8)
        gaf.key = b32decode(b32key + padding)
        for line in lines[1:]:
            if line.startswith('" '):
                opt_value = line[2:]
                if ' ' in opt_value:
                    opt, value = opt_value.split(' ', 1)
                else:
                    opt = opt_value
                    value = None
                gaf.options[opt] = value
            elif line:
                gaf.recovery_codes.append(line)
        return gaf

    def dump(self):
        lines = []
        lines.append(b32encode(self.key).replace('=', ''))
        for opt, value in self.options.iteritems():
            parts = ['"', opt]
            if value is not None:
                parts.append(value)
            lines.append(' '.join(parts))
        lines += self.recovery_codes
        lines.append('')
        return '\n'.join(lines)


class GoogleAuthenticatorPamFilesystemTotpService(TotpService):
    '''
    Store in home directories, compatible with the TOTP PAM module for Google Authenticator
    https://github.com/google/google-authenticator/tree/master/libpam
    '''

    @property
    def basedir(self):
        return config['auth.multifactor.totp.filesystem.basedir']

    def config_file(self, user):
        username = user.username
        if '/' in username:
            raise ValueError('Insecure username contains "/": %s' % username)
        return os.path.join(self.basedir, username, '.google_authenticator')

    def get_secret_key(self, user):
        try:
            with open(self.config_file(user)) as f:
                gaf = GoogleAuthenticatorFile.load(f.read())
                return gaf.key
        except IOError as e:
            if e.errno == errno.ENOENT:  # file doesn't exist
                return None
            else:
                raise

    def set_secret_key(self, user, key):
        if key is None:
            # this also deletes the recovery keys, since they're stored in the same file
            os.remove(self.config_file(user))
        else:
            userdir = os.path.dirname(self.config_file(user))
            if not os.path.exists(userdir):
                os.makedirs(userdir, 0700)
            try:
                with open(self.config_file(user)) as f:
                    gaf = GoogleAuthenticatorFile.load(f.read())
            except IOError as e:
                if e.errno == errno.ENOENT:  # file doesn't exist
                    gaf = GoogleAuthenticatorFile()
                    gaf.options['RATE_LIMIT'] = '3 30'
                    gaf.options['DISALLOW_REUSE'] = None
                    gaf.options['TOTP_AUTH'] = None
                else:
                    raise
            gaf.key = key
            with open(self.config_file(user), 'w') as f:
                f.write(gaf.dump())
