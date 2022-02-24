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
import random
import string
import tempfile
from collections import OrderedDict
from base64 import b32decode, b32encode
from time import time
import errno
import warnings

import bson
from allura.lib.exceptions import InvalidRecoveryCode, MultifactorRateLimitError
from tg import config
from tg import app_globals as g
from paste.deploy.converters import asint
with warnings.catch_warnings():  # ignore py2 CryptographyDeprecationWarning
    warnings.filterwarnings('ignore')
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.twofactor import InvalidToken
    from cryptography.hazmat.primitives.twofactor.totp import TOTP
    from cryptography.hazmat.primitives.hashes import SHA1
import qrcode
from ming.odm import session

from allura.model.multifactor import RecoveryCode
from allura.lib.utils import umask
import six


log = logging.getLogger(__name__)


def check_rate_limit(num_allowed, time_allowed, attempts):
    '''
    :param int num_allowed:
    :param int time_allowed:
    :param list[int] attempts:
    :return: tuple: ok (bool), attempts still in window (list[int])
    '''
    attempts_in_limit = []
    now = int(time())
    for prev_attempt in attempts:
        if now - prev_attempt <= time_allowed:
            attempts_in_limit.append(prev_attempt)
    attempts_in_limit.append(now)

    ok = len(attempts_in_limit) <= num_allowed
    return ok, attempts_in_limit


class TotpService:
    '''
    An interface for handling multifactor auth TOTP secret keys.  Common functionality
    is provided in this base class, and specific subclasses implement different storage options.
    A provider must implement :meth:`get_secret_key` and :meth:`set_secret_key` and :meth:`enforce_rate_limit`

    To use a new provider, expose an entry point in setup.py::

        [allura.multifactor.totp_service]
        mytotp = foo.bar:MyTotpService

    Then in your .ini file, set ``auth.multifactor.totp.service=mytotp``
    '''

    @classmethod
    def get(cls):
        '''
        :rtype: TotpService
        '''
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

    def verify(self, totp, code, user):
        code = code.replace(' ', '')  # Google authenticator puts a space in their codes
        code = six.ensure_binary(code)  # can't be text

        self.enforce_rate_limit(user)

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
        :param bytes|None key: may be `None` to clear out a key
        '''
        raise NotImplementedError('set_secret_key')

    def enforce_rate_limit(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :raises: MultifactorRateLimitError
        '''
        raise NotImplementedError('enforce_rate_limit')


class MongodbMultifactorCommon:

    def enforce_rate_limit(self, user):
        prev_attempts = user.get_tool_data('allura', 'multifactor_attempts') or []

        num_allowed = asint(config.get('auth.multifactor.rate_limit.num', 3))
        time_allowed = asint(config.get('auth.multifactor.rate_limit.time', 30))

        ok, attempts_in_limit = check_rate_limit(num_allowed, time_allowed, prev_attempts)

        user.set_tool_data('allura', multifactor_attempts=attempts_in_limit)

        if not ok:
            raise MultifactorRateLimitError


class MongodbTotpService(MongodbMultifactorCommon, TotpService):
    '''
    Store in TOTP keys in mongodb.
    '''

    def get_secret_key(self, user):
        from allura import model as M
        if user.is_anonymous():
            return None
        record = M.TotpKey.query.get(user_id=user._id)
        if record and record.key:
            return bytes(record.key)

    def set_secret_key(self, user, key):
        from allura import model as M
        if key is not None:
            key = bson.binary.Binary(key)
        M.TotpKey.query.update({'user_id': user._id},
                               {'user_id': user._id, 'key': key},
                               upsert=True)


class GoogleAuthenticatorFile:
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
        lines.append(six.ensure_text(b32encode(self.key)).replace('=', ''))
        for opt, value in self.options.items():
            parts = ['"', opt]
            if value is not None:
                parts.append(value)
            lines.append(' '.join(parts))
        lines += self.recovery_codes
        lines.append('')
        return '\n'.join(lines)


class GoogleAuthenticatorPamFilesystemMixin:

    @property
    def basedir(self):
        return config['auth.multifactor.totp.filesystem.basedir']

    def config_file(self, user):
        username = user.username
        if '/' in username:
            raise ValueError('Insecure username contains "/": %s' % username)
        return os.path.join(self.basedir, username, '.google_authenticator')

    def read_file(self, user, autocreate=False):
        if autocreate:
            userdir = os.path.dirname(self.config_file(user))
            if not os.path.exists(userdir):
                os.makedirs(userdir, 0o700)

        try:
            with open(self.config_file(user)) as f:
                return GoogleAuthenticatorFile.load(f.read())
        except OSError as e:
            if e.errno == errno.ENOENT:  # file doesn't exist
                if autocreate:
                    gaf = GoogleAuthenticatorFile()
                    gaf.options['RATE_LIMIT'] = '{} {}'.format(
                        asint(config.get('auth.multifactor.rate_limit.num', 3)),
                        asint(config.get('auth.multifactor.rate_limit.time', 30)))
                    gaf.options['DISALLOW_REUSE'] = None
                    gaf.options['TOTP_AUTH'] = None
                    return gaf
                else:
                    return None
            else:
                raise

    def write_file(self, user, gaf):
        conf_file = self.config_file(user)
        # using a tmp file and rename is atomic, and how PAM module does it
        # see `write_file_contents` in libpam/src/pam_google_authenticator.c
        # 377 umask gives 400 permissions, which matches how the PAM module does it (600 would be fine too)
        with umask(0o377), tempfile.NamedTemporaryFile('w',
                                                       dir=os.path.dirname(conf_file),
                                                       prefix='tmp-allura-gauth-',
                                                       delete=False) as f:
            f.write(gaf.dump())
        os.rename(f.name, conf_file)

    def enforce_rate_limit(self, user, existing_gaf=None):
        if existing_gaf:
            gaf = existing_gaf
        else:
            gaf = self.read_file(user)
        if not gaf:
            return
        rate_limits = gaf.options['RATE_LIMIT'].split(' ')
        num_allowed = int(rate_limits.pop(0))
        time_allowed = int(rate_limits.pop(0))
        prev_attempts = list(map(int, rate_limits))

        ok, attempts_in_limit = check_rate_limit(num_allowed, time_allowed, prev_attempts)

        gaf.options['RATE_LIMIT'] = ' '.join(map(str, [num_allowed, time_allowed] + attempts_in_limit))

        if not existing_gaf:
            self.write_file(user, gaf)

        if not ok:
            raise MultifactorRateLimitError


class GoogleAuthenticatorPamFilesystemTotpService(GoogleAuthenticatorPamFilesystemMixin, TotpService):
    '''
    Store in home directories, compatible with the TOTP PAM module for Google Authenticator
    https://github.com/google/google-authenticator/tree/master/libpam
    '''

    def get_secret_key(self, user):
        gaf = self.read_file(user)
        if gaf:
            return gaf.key
        else:
            return None

    def set_secret_key(self, user, key):
        if key is None:
            # this also deletes the recovery keys, since they're stored in the same file
            os.remove(self.config_file(user))
        else:
            gaf = self.read_file(user, autocreate=True)
            gaf.key = key
            self.write_file(user, gaf)


class RecoveryCodeService:
    '''
    An interface for handling multifactor recovery codes.  Common functionality
    is provided in this base class, and specific subclasses implement different storage options.
    A provider must implement :meth:`get_codes`, :meth:`replace_codes`, and :meth:`verify_and_remove_code`.


    To use a new provider, expose an entry point in setup.py::

        [allura.multifactor.recovery_code]
        myrecovery = foo.bar:MyRecoveryCodeService

    Then in your .ini file, set ``auth.multifactor.recovery_code.service=myrecovery``
    '''

    @classmethod
    def get(cls):
        '''
        :rtype: RecoveryCodeService
        '''
        method = config.get('auth.multifactor.recovery_code.service', 'mongodb')
        return g.entry_points['multifactor_recovery_code'][method]()

    def generate_one_code(self):
        # for compatibility with Google PAM file, we only do digits
        length = asint(config.get('auth.multifactor.recovery_code.length', 8))
        return ''.join([random.choice(string.digits) for i in range(length)])

    def regenerate_codes(self, user):
        '''
        Regenerate and replace existing codes

        :param user: a :class:`User <allura.model.auth.User>`
        :return: codes, ``list[str]``
        '''
        count = asint(config.get('auth.multifactor.recovery_code.count', 10))
        codes = [
            self.generate_one_code() for i in range(count)
        ]
        self.replace_codes(user, codes)
        return codes

    def delete_all(self, user):
        return self.replace_codes(user, [])

    def get_codes(self, user):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        :return: list[str]
        '''
        raise NotImplementedError('get_codes')

    def replace_codes(self, user, codes):
        '''
        :param user: a :class:`User <allura.model.auth.User>`
        '''
        raise NotImplementedError('replace_codes')

    def verify_and_remove_code(self, user, code):
        '''
        Verify and remove recovery codes.  Also check for rate limiting.

        :param user: a :class:`User <allura.model.auth.User>`
        :param code: str
        :raises: InvalidRecoveryCode
        :raises: MultifactorRateLimitError
        '''
        raise NotImplementedError('verify_and_remove_code')


class MongodbRecoveryCodeService(MongodbMultifactorCommon, RecoveryCodeService):

    def get_codes(self, user):
        return [rc.code for rc in
                RecoveryCode.query.find({'user_id': user._id}).sort('_id')]

    def replace_codes(self, user, codes):
        RecoveryCode.query.remove({'user_id': user._id})
        for code in codes:
            rc = RecoveryCode(user_id=user._id, code=code)
            session(rc).flush(rc)

    def verify_and_remove_code(self, user, code):
        self.enforce_rate_limit(user)
        rc = RecoveryCode.query.get(user_id=user._id, code=code)
        if rc:
            rc.query.delete()
            session(rc).flush(rc)
            return True
        else:
            raise InvalidRecoveryCode


class GoogleAuthenticatorPamFilesystemRecoveryCodeService(GoogleAuthenticatorPamFilesystemMixin, RecoveryCodeService):

    def get_codes(self, user):
        gaf = self.read_file(user)
        if gaf:
            return gaf.recovery_codes
        else:
            return []

    def replace_codes(self, user, codes):
        gaf = self.read_file(user)
        if gaf:
            gaf.recovery_codes = codes
            self.write_file(user, gaf)
        elif codes:
            raise OSError('No .google-authenticator file exists, cannot add recovery codes.')

    def verify_and_remove_code(self, user, code):
        gaf = self.read_file(user)
        if gaf:
            try:
                self.enforce_rate_limit(user, gaf)
                if code in gaf.recovery_codes:
                    gaf.recovery_codes.remove(code)
                    return True
            finally:
                # write both rate limit & recovery code changes
                self.write_file(user, gaf)
        raise InvalidRecoveryCode
