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


import textwrap
import os

import bson
from allura.lib.exceptions import InvalidRecoveryCode
from paste.deploy.converters import asint

import ming
from cryptography.hazmat.primitives.twofactor import InvalidToken
from mock import patch, Mock
from nose.tools import assert_equal, assert_raises
from tg import config

from allura.lib.multifactor import GoogleAuthenticatorFile, TotpService, MongodbTotpService
from allura.lib.multifactor import GoogleAuthenticatorPamFilesystemTotpService
from allura.lib.multifactor import RecoveryCodeService, MongodbRecoveryCodeService


class TestGoogleAuthenticatorFile(object):
    sample = textwrap.dedent('''\
        7CL3WL756ISQCU5HRVNAODC44Q
        " RATE_LIMIT 3 30
        " DISALLOW_REUSE
        " TOTP_AUTH
        43504045
        16951331
        16933944
        38009587
        49571579
        ''')
    # different key length
    sample2 = textwrap.dedent('''\
        LQQTTQUEW3VAGA6O5XICCWGBXUWXI737
        " TOTP_AUTH
        ''')

    def test_parse(self):
        gaf = GoogleAuthenticatorFile.load(self.sample)
        assert_equal(gaf.key, b'\xf8\x97\xbb/\xfd\xf2%\x01S\xa7\x8dZ\x07\x0c\\\xe4')
        assert_equal(gaf.options['RATE_LIMIT'], '3 30')
        assert_equal(gaf.options['DISALLOW_REUSE'], None)
        assert_equal(gaf.options['TOTP_AUTH'], None)
        assert_equal(gaf.recovery_codes, [
            '43504045',
            '16951331',
            '16933944',
            '38009587',
            '49571579',
        ])

    def test_dump(self):
        gaf = GoogleAuthenticatorFile.load(self.sample)
        assert_equal(gaf.dump(), self.sample)

    def test_dump2(self):
        gaf = GoogleAuthenticatorFile.load(self.sample2)
        assert_equal(gaf.dump(), self.sample2)


class TestTotpService(object):

    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'
    sample_time = 1472502664
    # these generate code 283397

    def test_constructor(self):
        totp = TotpService().Totp(key=None)
        assert totp

    @patch('allura.lib.multifactor.time')
    def test_verify_types(self, time):
        time.return_value = self.sample_time
        srv = TotpService()
        totp = srv.Totp(key=self.sample_key)
        srv.verify(totp, u'283 397')
        srv.verify(totp, b'283397')

    @patch('allura.lib.multifactor.time')
    def test_verify_window(self, time):
        time.return_value = self.sample_time
        srv = TotpService()
        totp = srv.Totp(key=self.sample_key)
        srv.verify(totp, b'283397')

        time.return_value = self.sample_time + 30
        srv.verify(totp, b'283397')

        time.return_value = self.sample_time + 60
        with assert_raises(InvalidToken):
            srv.verify(totp, b'283397')

        time.return_value = self.sample_time - 30
        with assert_raises(InvalidToken):
            srv.verify(totp, b'283397')

    def test_get_qr_code(self):
        srv = TotpService()
        totp = srv.Totp(key=None)
        user = Mock(username='some-user-guy')
        config['site_name'] = 'Our Website'
        assert srv.get_qr_code(totp, user)


class TestMongodbTotpService():
    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'

    def setUp(self):
        config = {
            'ming.main.uri': 'mim://allura_test',
        }
        ming.configure(**config)

    def test_none(self):
        srv = MongodbTotpService()
        user = Mock(_id=bson.ObjectId(),
                    is_anonymous=lambda: False,
                    )
        assert_equal(None, srv.get_secret_key(user))

    def test_set_get(self):
        srv = MongodbTotpService()
        user = Mock(_id=bson.ObjectId(),
                    is_anonymous=lambda: False,
                    )
        srv.set_secret_key(user, self.sample_key)
        assert_equal(self.sample_key, srv.get_secret_key(user))

    def test_delete(self):
        srv = MongodbTotpService()
        user = Mock(_id=bson.ObjectId(),
                    is_anonymous=lambda: False,
                    )
        srv.set_secret_key(user, self.sample_key)
        assert_equal(self.sample_key, srv.get_secret_key(user))
        srv.set_secret_key(user, None)
        assert_equal(None, srv.get_secret_key(user))


class TestGoogleAuthenticatorPamFilesystemTotpService():
    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'

    def setUp(self):
        config['auth.multifactor.totp.filesystem.basedir'] = os.path.join(os.getenv('TMPDIR', '/tmp'), 'totp-test')

    def test_none(self):
        srv = GoogleAuthenticatorPamFilesystemTotpService()
        user = Mock(username='some-user-guy')
        assert_equal(None, srv.get_secret_key(user))

    def test_set_get(self):
        srv = GoogleAuthenticatorPamFilesystemTotpService()
        user = Mock(username='some-user-guy')
        srv.set_secret_key(user, self.sample_key)
        assert_equal(self.sample_key, srv.get_secret_key(user))

    def test_delete(self):
        srv = GoogleAuthenticatorPamFilesystemTotpService()
        user = Mock(username='some-user-guy')
        srv.set_secret_key(user, self.sample_key)
        assert_equal(self.sample_key, srv.get_secret_key(user))
        srv.set_secret_key(user, None)
        assert_equal(None, srv.get_secret_key(user))


class TestRecoveryCodeService(object):

    def test_generate_one_code(self):
        code = RecoveryCodeService().generate_one_code()
        assert code
        another_code = RecoveryCodeService().generate_one_code()
        assert code != another_code

    def test_regenerate_codes(self):
        class DummyRecoveryService(RecoveryCodeService):
            def replace_codes(self, user, codes):
                self.saved_user = user
                self.saved_codes = codes
        recovery = DummyRecoveryService()
        user = Mock(username='some-user-guy')

        recovery.regenerate_codes(user)

        assert_equal(recovery.saved_user, user)
        assert_equal(len(recovery.saved_codes), asint(config.get('auth.multifactor.recovery_code.count', 10)))


class TestMongodbRecoveryCodeService(object):

    def setUp(self):
        config = {
            'ming.main.uri': 'mim://allura_test',
        }
        ming.configure(**config)

    def test_get_codes(self):
        recovery = MongodbRecoveryCodeService()
        user = Mock(_id=bson.ObjectId())
        assert_equal(recovery.get_codes(user), [])
        recovery.regenerate_codes(user)
        assert recovery.get_codes(user)

    def test_replace_codes(self):
        recovery = MongodbRecoveryCodeService()
        user = Mock(_id=bson.ObjectId())
        codes = [
            '12345',
            '67890'
        ]
        recovery.replace_codes(user, codes)
        assert_equal(recovery.get_codes(user), codes)

    def test_verify_fail(self):
        recovery = MongodbRecoveryCodeService()
        user = Mock(_id=bson.ObjectId())
        with assert_raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '11111')
        with assert_raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '')

    def test_verify_and_remove_code(self):
        recovery = MongodbRecoveryCodeService()
        user = Mock(_id=bson.ObjectId())
        codes = [
            '12345',
            '67890'
        ]
        recovery.replace_codes(user, codes)
        result = recovery.verify_and_remove_code(user, '12345')
        assert_equal(result, True)
        assert_equal(recovery.get_codes(user), ['67890'])
