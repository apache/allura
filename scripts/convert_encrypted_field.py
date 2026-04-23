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

from ming import schema
from ming.odm import mapper, session
from ming.odm.declarative import MappedClass
from ming.odm.property import FieldProperty, DecryptedProperty


CHUNK_SIZE = 1000


class MissingFieldPathError(Exception):
    pass


def _default_encrypted_field_name(plain_field_name: str) -> str:
    parent, sep, leaf = plain_field_name.rpartition('.')
    return f'{parent}{sep}{leaf}_encrypted'


def _split_field_path(field_name: str) -> list[str]:
    field_path = field_name.split('.')
    assert field_path and all(field_path), f'Invalid dotted field path: {field_name!r}'
    return field_path


def _schema_for_field_path(Model: type[MappedClass], field_name: str):
    field_path = _split_field_path(field_name)
    top_level_name = field_path[0]
    try:
        top_level_prop = getattr(Model, top_level_name)
    except AttributeError as e:
        raise MissingFieldPathError(
            f'Missing field path {field_name!r}; no top-level field {top_level_name!r}') from e
    assert isinstance(top_level_prop, FieldProperty)

    current_schema = top_level_prop.field.schema
    for i, path_part in enumerate(field_path[1:], start=1):
        traversed = '.'.join(field_path[:i])
        if isinstance(current_schema, schema.Array):
            raise AssertionError(
                f'Nested array paths are not supported: {field_name!r} (array at {traversed!r})')
        if not isinstance(current_schema, schema.Object):
            raise AssertionError(
                f'Invalid nested field path {field_name!r}; {traversed!r} is not an object field')
        if path_part not in current_schema.fields:
            raise MissingFieldPathError(
                f'Invalid nested field path {field_name!r}; missing key {traversed + "." + path_part!r}')

        current_schema = current_schema.fields[path_part]

    return current_schema


def _get_nested_value(rec: dict, field_name: str):
    value = rec
    for path_part in _split_field_path(field_name):
        value = value[path_part]
    return value


def main(class_name: str, plain_field_name: str,
         *, remove_unencrypted: bool = False, redo_all: bool = False, limit: int | None = None):
    """
    :param class_name: full class name, e.g. allura.model.user.User
    :param plain_field_name: name of the unencrypted field, e.g. display_name
    :param remove_unencrypted: WARNING only run this after your codebase is already on the latest code
    :param redo_all: re-encrypt records that already have encrypted values (in case they changed since last run)
    :param limit: convert this many records per update type (bulk, individual, removal) default All
    """
    encrypted_field_name = _default_encrypted_field_name(plain_field_name)

    module_name, class_basename = class_name.rsplit('.', 1)
    module = import_module(module_name)
    Model: type[MappedClass] = getattr(module, class_basename)

    # sanity checks that the fields are correct and ready
    try:
        encr_schema = _schema_for_field_path(Model, encrypted_field_name)
    except MissingFieldPathError:
        # pre-migration support: encrypted field might not yet be present in
        # model schema, but we can still create it with raw MongoDB updates
        encr_schema = None
    if encr_schema is not None:
        assert isinstance(encr_schema, schema.Binary)
    elif remove_unencrypted:
        raise AssertionError(
            f'Cannot use --remove-unencrypted because {encrypted_field_name!r} '
            'is not present in model schema yet')
    if remove_unencrypted:
        if '.' not in plain_field_name:
            plain_prop = Model.__dict__[plain_field_name]  # getattr() better but needs Ming fix released
            assert isinstance(plain_prop, DecryptedProperty)
            assert plain_prop.encrypted_field == encrypted_field_name

    # TODO: figure out how it works with inheritance

    sess = session(Model)

    # encrypt all records that need it.  Even for --remove-unencrypted, to make sure everything's converted first
    bulk_update_values = ["", None]
    for bulk_val in bulk_update_values:
        query = {
            plain_field_name: {'$exists': True, '$eq': bulk_val},  # $exists to avoid converting missing fields
        }
        if not redo_all:
            query[encrypted_field_name] = {'$exists': False}
        if limit:
            ids_to_remove = [rec._id for rec in Model.query.find(query).limit(limit)]
            query |= {'_id': {'$in': ids_to_remove}}
        bulk_update_result = Model.query.update(
            query,
            {
                '$set': {encrypted_field_name: Model.encr(bulk_val)},
            },
            multi=True,
        )
        print(f'Converted {bulk_update_result.modified_count} (of {bulk_update_result.matched_count}) {class_name} records with {plain_field_name}={bulk_val!r}')
        # bulk_update_result.matched_count has # matches, already handled if run multiple times

    q = {
        plain_field_name: {'$nin': bulk_update_values},
    }
    if not redo_all:
        q[encrypted_field_name] = None

    m = mapper(Model)
    raw_collection = sess.impl.db[m.collection.m.collection_name]

    count = 0
    projection = {'_id': 1, plain_field_name: 1}
    last_id = None
    while count < limit if limit else True:
        chunk_q = {'$and': [q, {'_id': {'$gt': last_id}}]} if last_id is not None else q
        docs = list(raw_collection.find(chunk_q, projection).sort('_id', 1).limit(CHUNK_SIZE))
        if not docs:
            break

        for rec_doc in docs:
            val = _get_nested_value(rec_doc, plain_field_name)
            encr_val = Model.encr(val)
            raw_collection.update_one({'_id': rec_doc['_id']}, {
                '$set': {encrypted_field_name: encr_val},
            })
            count += 1
            if limit and count >= limit:
                break

        last_id = docs[-1]['_id']
        print(f'Converted {count} so far...')
    if not count:
        print(f'Did not find any {class_name} records with {plain_field_name} values to encrypt')
    else:
        print(f'Encrypted {count} {class_name} records with {plain_field_name} values')

    if remove_unencrypted:
        query = {}
        if limit:
            ids_to_remove = [rec._id for rec in Model.query.find(query).limit(limit)]
            query |= {'_id': {'$in': ids_to_remove}}
        remove_result = Model.query.update(
            query,
            {
                "$unset": {plain_field_name: True}
            },
            multi=True,
        )
        print(f'Removed {remove_result.modified_count} {class_name} unencrypted {plain_field_name} values')


if __name__ == "__main__":
    defopt.run(main, no_negated_flags=True, short={})
