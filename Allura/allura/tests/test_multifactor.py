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
import shutil
import tempfile
import textwrap
import os

from paste.deploy.converters import asint
import ming
from cryptography.hazmat.primitives.twofactor import InvalidToken
from mock import patch, Mock
import pytest
from tg import config

from allura import model as M
from allura.lib.exceptions import InvalidRecoveryCode, MultifactorRateLimitError
from allura.lib.multifactor import GoogleAuthenticatorFile, TotpService, MongodbTotpService
from allura.lib.multifactor import GoogleAuthenticatorPamFilesystemTotpService
from allura.lib.multifactor import RecoveryCodeService, MongodbRecoveryCodeService
from allura.lib.multifactor import GoogleAuthenticatorPamFilesystemRecoveryCodeService


class TestGoogleAuthenticatorFile:
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
        assert gaf.key == b'\xf8\x97\xbb/\xfd\xf2%\x01S\xa7\x8dZ\x07\x0c\\\xe4'
        assert gaf.options['RATE_LIMIT'] == '3 30'
        assert gaf.options['DISALLOW_REUSE'] is None
        assert gaf.options['TOTP_AUTH'] is None
        assert gaf.recovery_codes == [
            '43504045',
            '16951331',
            '16933944',
            '38009587',
            '49571579',
        ]

    def test_dump(self):
        gaf = GoogleAuthenticatorFile.load(self.sample)
        assert gaf.dump() == self.sample

    def test_dump2(self):
        gaf = GoogleAuthenticatorFile.load(self.sample2)
        assert gaf.dump() == self.sample2


class GenericTotpService(TotpService):
    def enforce_rate_limit(self, *args, **kwargs):
        pass


class TestTotpService:

    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'
    sample_time = 1472502664
    # these generate code 283397

    def test_constructor(self):
        totp = TotpService().Totp(key=None)
        assert totp

    @patch('allura.lib.multifactor.time')
    def test_verify_types(self, time):
        time.return_value = self.sample_time
        srv = GenericTotpService()
        totp = srv.Totp(key=self.sample_key)
        srv.verify(totp, '283 397', None)
        srv.verify(totp, '283397', None)

    @patch('allura.lib.multifactor.time')
    def test_verify_window(self, time):
        time.return_value = self.sample_time
        srv = GenericTotpService()
        totp = srv.Totp(key=self.sample_key)
        srv.verify(totp, '283397', None)

        time.return_value = self.sample_time + 30
        srv.verify(totp, '283397', None)

        time.return_value = self.sample_time + 60
        with pytest.raises(InvalidToken):
            srv.verify(totp, '283397', None)

        time.return_value = self.sample_time - 30
        with pytest.raises(InvalidToken):
            srv.verify(totp, '283397', None)

    def test_get_qr_code(self):
        srv = TotpService()
        totp = srv.Totp(key=None)
        user = Mock(username='some-user-guy')
        config['site_name'] = 'Our Website'
        assert srv.get_qr_code(totp, user)


class TestAnyTotpServiceImplementation:

    __test__ = False

    sample_key = b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a'
    sample_time = 1472502664
    # these generate code 283397

    def mock_user(self):
        return M.User(username='some-user-guy')

    def test_none(self):
        srv = self.Service()
        user = self.mock_user()
        assert None == srv.get_secret_key(user)

    def test_set_get(self):
        srv = self.Service()
        user = self.mock_user()
        srv.set_secret_key(user, self.sample_key)
        assert self.sample_key == srv.get_secret_key(user)

    def test_delete(self):
        srv = self.Service()
        user = self.mock_user()
        srv.set_secret_key(user, self.sample_key)
        assert self.sample_key == srv.get_secret_key(user)
        srv.set_secret_key(user, None)
        assert None == srv.get_secret_key(user)

    @patch('allura.lib.multifactor.time')
    def test_rate_limiting(self, time):
        time.return_value = self.sample_time
        srv = self.Service()
        user = self.mock_user()
        totp = srv.Totp(key=self.sample_key)

        # 4th attempt (good or bad) will trip over the default limit of 3 in 30s
        with pytest.raises(InvalidToken):
            srv.verify(totp, '34dfvdasf', user)
        with pytest.raises(InvalidToken):
            srv.verify(totp, '234asdfsadf', user)
        srv.verify(totp, '283397', user)
        with pytest.raises(MultifactorRateLimitError):
            srv.verify(totp, '283397', user)


class TestMongodbTotpService(TestAnyTotpServiceImplementation):

    __test__ = True
    Service = MongodbTotpService

    def setup_method(self, method):
        config = {
            'ming.main.uri': 'mim://host/allura_test',
        }
        ming.configure(**config)


class TestGoogleAuthenticatorPamFilesystemMixin:

    def setup_method(self, method):
        self.totp_basedir = tempfile.mkdtemp(prefix='totp-test', dir=os.getenv('TMPDIR', '/tmp'))
        config['auth.multifactor.totp.filesystem.basedir'] = self.totp_basedir

    def teardown_method(self, method):
        if os.path.exists(self.totp_basedir):
            shutil.rmtree(self.totp_basedir)


class TestGoogleAuthenticatorPamFilesystemTotpService(TestAnyTotpServiceImplementation,
                                                      TestGoogleAuthenticatorPamFilesystemMixin):

    __test__ = True
    Service = GoogleAuthenticatorPamFilesystemTotpService

    def test_rate_limiting(self):
        # make a regular .google-authenticator file first, so rate limit info has somewhere to go
        self.Service().set_secret_key(self.mock_user(), self.sample_key)
        # then run test
        super().test_rate_limiting()


class TestRecoveryCodeService:

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

        assert recovery.saved_user == user
        assert len(recovery.saved_codes) == asint(config.get('auth.multifactor.recovery_code.count', 10))


class TestAnyRecoveryCodeServiceImplementation:

    __test__ = False

    def mock_user(self):
        return M.User(username='some-user-guy')

    def test_get_codes_none(self):
        recovery = self.Service()
        user = self.mock_user()
        assert recovery.get_codes(user) == []

    def test_regen_get_codes(self):
        recovery = self.Service()
        user = self.mock_user()
        recovery.regenerate_codes(user)
        assert recovery.get_codes(user)

    def test_replace_codes(self):
        recovery = self.Service()
        user = self.mock_user()
        codes = [
            '12345',
            '67890'
        ]
        recovery.replace_codes(user, codes)
        assert recovery.get_codes(user) == codes

    def test_verify_fail(self):
        recovery = self.Service()
        user = self.mock_user()
        with pytest.raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '11111')
        with pytest.raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '')

    def test_verify_and_remove_code(self):
        recovery = self.Service()
        user = self.mock_user()
        codes = [
            '12345',
            '67890'
        ]
        recovery.replace_codes(user, codes)
        result = recovery.verify_and_remove_code(user, '12345')
        assert result is True
        assert recovery.get_codes(user) == ['67890']

    def test_rate_limiting(self):
        recovery = self.Service()
        user = self.mock_user()
        codes = [
            '11111',
            '22222',
        ]
        recovery.replace_codes(user, codes)

        # 4th attempt (good or bad) will trip over the default limit of 3 in 30s
        with pytest.raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '13485u0233')
        with pytest.raises(InvalidRecoveryCode):
            recovery.verify_and_remove_code(user, '34123rdxafs')
        recovery.verify_and_remove_code(user, '11111')
        with pytest.raises(MultifactorRateLimitError):
            recovery.verify_and_remove_code(user, '22222')


class TestMongodbRecoveryCodeService(TestAnyRecoveryCodeServiceImplementation):

    __test__ = True

    Service = MongodbRecoveryCodeService

    def setup_method(self, method):
        config = {
            'ming.main.uri': 'mim://host/allura_test',
        }
        ming.configure(**config)


class TestGoogleAuthenticatorPamFilesystemRecoveryCodeService(TestAnyRecoveryCodeServiceImplementation,
                                                              TestGoogleAuthenticatorPamFilesystemMixin):

    __test__ = True

    Service = GoogleAuthenticatorPamFilesystemRecoveryCodeService

    def setup_method(self, method):
        super().setup_method(method)

        # make a regular .google-authenticator file first, so recovery keys have somewhere to go
        GoogleAuthenticatorPamFilesystemTotpService().set_secret_key(self.mock_user(),
                                                                     b'\x00K\xda\xbfv\xc2B\xaa\x1a\xbe\xa5\x96b\xb2\xa0Z:\xc9\xcf\x8a')

    def test_get_codes_none_when_no_file(self):
        # this deletes the file
        GoogleAuthenticatorPamFilesystemTotpService().set_secret_key(self.mock_user(), None)

        super().test_get_codes_none()

    def test_replace_codes_when_no_file(self):
        # this deletes the file
        GoogleAuthenticatorPamFilesystemTotpService().set_secret_key(self.mock_user(), None)

        # then it errors because no .google-authenticator file
        with pytest.raises(IOError):
            super().test_replace_codes()
