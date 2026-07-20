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

from ming import schema as S
from ming.encryption import NestedEncryptedProperty
from ming.odm import FieldProperty

from scripts.convert_encrypted_field import (
    _encryption_schema_info,
    _encrypt_nested_array_value,
    _remove_nested_array_value,
)


class TestModel:
    socialnetworks = NestedEncryptedProperty([dict(
        socialnetwork=str,
        accounturl_encrypted=S.Binary,
    )])

    @classmethod
    def encr(cls, value):
        return None if value is None else f'encrypted:{value}'.encode()


def test_encryption_schema_info_uses_encrypted_nested_array_path():
    field_schema, traverses_array = _encryption_schema_info(
        TestModel,
        'socialnetworks.accounturl',
        'socialnetworks.accounturl_encrypted',
    )

    assert isinstance(field_schema, S.Binary)
    assert traverses_array is True


def test_encryption_schema_info_supports_model_without_encrypted_field():
    class PreMigrationTestModel:
        socialnetworks = FieldProperty([dict(
            socialnetwork=str,
            accounturl=str,
        )])

    field_schema, traverses_array = _encryption_schema_info(
        PreMigrationTestModel,
        'socialnetworks.accounturl',
        'socialnetworks.accounturl_encrypted',
    )

    assert field_schema is None
    assert traverses_array is True


def test_encrypt_nested_array_value_updates_every_item():
    socialnetworks = [
        {'socialnetwork': 'Mastodon', 'accounturl': 'https://example.com/@user'},
        {'socialnetwork': 'LinkedIn', 'accounturl': 'https://example.com/in/user'},
        {'socialnetwork': 'Other', 'accounturl': None},
    ]

    encrypted, changed = _encrypt_nested_array_value(
        TestModel,
        socialnetworks,
        ['accounturl'],
        'accounturl_encrypted',
        S.Binary(),
        redo_all=False,
    )

    assert changed is True
    assert encrypted == [
        {
            'socialnetwork': 'Mastodon',
            'accounturl': 'https://example.com/@user',
            'accounturl_encrypted': b'encrypted:https://example.com/@user',
        },
        {
            'socialnetwork': 'LinkedIn',
            'accounturl': 'https://example.com/in/user',
            'accounturl_encrypted': b'encrypted:https://example.com/in/user',
        },
        {
            'socialnetwork': 'Other',
            'accounturl': None,
            'accounturl_encrypted': None,
        },
    ]


def test_remove_nested_array_value_preserves_encrypted_and_other_fields():
    socialnetworks = [
        {
            'socialnetwork': 'Mastodon',
            'accounturl': 'https://example.com/@user',
            'accounturl_encrypted': b'encrypted:https://example.com/@user',
        },
        {
            'socialnetwork': 'Other',
            'accounturl': None,
            'accounturl_encrypted': None,
        },
    ]

    encrypted_only, changed = _remove_nested_array_value(
        socialnetworks, ['accounturl'])

    assert changed is True
    assert encrypted_only == [
        {
            'socialnetwork': 'Mastodon',
            'accounturl_encrypted': b'encrypted:https://example.com/@user',
        },
        {
            'socialnetwork': 'Other',
            'accounturl_encrypted': None,
        },
    ]
