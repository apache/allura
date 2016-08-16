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

from nose.tools import assert_equal

from allura.lib.multifactor import GoogleAuthenticatorFile


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
