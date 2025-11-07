#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an
#  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#  KIND, either express or implied.  See the License for the
#  specific language governing permissions and limitations
#  under the License.

from __future__ import annotations

from importlib import import_module

import defopt

from allura.lib.utils import chunked_find
from ming import schema
from ming.odm import session
from ming.odm.declarative import MappedClass
from ming.odm.property import FieldProperty, DecryptedProperty


def main(class_name: str, plain_field_name: str,
         *, remove_unencrypted: bool = False, redo_all: bool = False):
    """
    :param class_name: full class name, e.g. allura.model.user.User
    :param plain_field_name: name of the unencrypted field, e.g. display_name
    :param remove_unencrypted: WARNING only run this after your codebase is already on the latest code
    :param redo_all: re-encrypt records that already have encrypted values (in case they changed since last run)
    """
    encrypted_field_name = f'{plain_field_name}_encrypted'

    module_name, class_basename = class_name.rsplit('.', 1)
    module = import_module(module_name)
    Model: type[MappedClass] = getattr(module, class_basename)

    # sanity checks that the fields are correct and ready
    encr_prop = getattr(Model, encrypted_field_name)
    assert isinstance(encr_prop, FieldProperty)
    assert encr_prop.field.type == schema.Binary
    if remove_unencrypted:
        plain_prop = Model.__dict__[plain_field_name]  # getattr() better but needs Ming fix released
        assert isinstance(plain_prop, DecryptedProperty)
        assert plain_prop.encrypted_field == encrypted_field_name

    # TODO: figure out how it works with inheritance

    sess = session(Model)

    # encrypt all records that need it.  Even for --remove-unencrypted, to make sure everything's converted first
    bulk_update_values = ["", None]
    for bulk_val in bulk_update_values:
        bulk_update_result = Model.query.update(
            {
                plain_field_name: {'$exists': True, '$eq': bulk_val},  # $exists to avoid converting missing fields
            },
            {
                '$set': {encrypted_field_name: Model.encr(bulk_val)},
            },
            multi=True,
        )
        print(f'Converted {bulk_update_result.modified_count} {class_name} records with {plain_field_name}={bulk_val!r}')
        # bulk_update_result.matched_count has # matches, already handled if run multiple times

    q = {
        plain_field_name: {'$nin': bulk_update_values},
    }
    if not redo_all:
        q[encrypted_field_name] = None
    count = 0
    for chunk in chunked_find(Model, q):
        for rec in chunk:
            val = rec[plain_field_name]
            encr_val = Model.encr(val)
            Model.query.update({'_id': rec['_id']}, {
                '$set': {encrypted_field_name: encr_val},
            })
            count += 1
            sess.expunge(rec)
        print(f'Converted {count} so far...')
    if not count:
        print(f'Did not find any {class_name} records with {plain_field_name} values to encrypt')
    else:
        print(f'Encrypted {count} {class_name} records with {plain_field_name} values')

    if remove_unencrypted:
        remove_result = Model.query.update(
            {},
            {
                "$unset": {plain_field_name: True}
            },
            multi=True,
        )
        print(f'Removed {remove_result.modified_count} {class_name} unencrypted {plain_field_name} values')


if __name__ == "__main__":
    defopt.run(main, no_negated_flags=True, short={})
