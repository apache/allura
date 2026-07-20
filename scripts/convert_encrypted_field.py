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


def _schema_info_for_field_path(Model: type[MappedClass], field_name: str):
    field_path = _split_field_path(field_name)
    top_level_name = field_path[0]
    try:
        top_level_prop = getattr(Model, top_level_name)
    except AttributeError as e:
        raise MissingFieldPathError(
            f'Missing field path {field_name!r}; no top-level field {top_level_name!r}') from e
    assert isinstance(top_level_prop, FieldProperty)

    current_schema = top_level_prop.field.schema
    traverses_array = False
    for i, path_part in enumerate(field_path[1:], start=1):
        traversed = '.'.join(field_path[:i])
        while isinstance(current_schema, schema.Array):
            traverses_array = True
            current_schema = current_schema.field_type
        if not isinstance(current_schema, schema.Object):
            raise AssertionError(
                f'Invalid nested field path {field_name!r}; {traversed!r} is not an object field')
        if path_part not in current_schema.fields:
            raise MissingFieldPathError(
                f'Invalid nested field path {field_name!r}; missing key {traversed + "." + path_part!r}')

        current_schema = current_schema.fields[path_part]

    return current_schema, traverses_array


def _encryption_schema_info(Model: type[MappedClass], plain_field_name: str,
                            encrypted_field_name: str):
    try:
        return _schema_info_for_field_path(Model, encrypted_field_name)
    except MissingFieldPathError:
        # Pre-migration support: infer array traversal from the plaintext
        # schema when the encrypted field has not been added to the model yet.
        _, traverses_array = _schema_info_for_field_path(Model, plain_field_name)
        return None, traverses_array


def _get_nested_value(rec: dict, field_name: str):
    value = rec
    for path_part in _split_field_path(field_name):
        value = value[path_part]
    return value


def _transform_nested_array_value(value, field_path, transform_leaf):
    if isinstance(value, list):
        transformed = []
        changed = False
        for item in value:
            transformed_item, item_changed = _transform_nested_array_value(
                item, field_path, transform_leaf)
            transformed.append(transformed_item)
            changed |= item_changed
        return (transformed, True) if changed else (value, False)

    if not isinstance(value, dict) or not field_path:
        return value, False

    field_name = field_path[0]
    if len(field_path) == 1:
        return transform_leaf(value, field_name)
    if field_name not in value:
        return value, False

    transformed_child, changed = _transform_nested_array_value(
        value[field_name], field_path[1:], transform_leaf)
    if not changed:
        return value, False

    transformed = dict(value)
    transformed[field_name] = transformed_child
    return transformed, True


def _encrypt_nested_array_value(Model, value, plain_field_path, encrypted_field_name,
                                field_schema, redo_all):
    def encrypt_leaf(item, plain_field_name):
        if plain_field_name not in item:
            return item, False

        plain_value = item[plain_field_name]
        if not redo_all and encrypted_field_name in item:
            encrypted_value = item[encrypted_field_name]
            if encrypted_value is not None or plain_value is None:
                return item, False

        transformed = dict(item)
        transformed[encrypted_field_name] = _encrypt_field_value(
            Model, plain_value, field_schema)
        return transformed, True

    return _transform_nested_array_value(value, plain_field_path, encrypt_leaf)


def _remove_nested_array_value(value, plain_field_path):
    def remove_leaf(item, plain_field_name):
        if plain_field_name not in item:
            return item, False
        transformed = dict(item)
        del transformed[plain_field_name]
        return transformed, True

    return _transform_nested_array_value(value, plain_field_path, remove_leaf)


def _is_encrypted_list_schema(field_schema) -> bool:
    return (
        isinstance(field_schema, schema.Array)
        and isinstance(field_schema.field_type, schema.Binary)
    )


def _encrypt_field_value(Model: type[MappedClass], value, field_schema):
    if _is_encrypted_list_schema(field_schema):
        return [Model.encr(v) if v is not None else None for v in value or []]
    return Model.encr(value)


def _update_nested_array_records(raw_collection, plain_field_name, transform, limit):
    field_path = _split_field_path(plain_field_name)
    top_level_field = field_path[0]
    nested_field_path = field_path[1:]
    assert nested_field_path

    query = {plain_field_name: {'$exists': True}}
    projection = {'_id': 1, top_level_field: 1}
    count = 0
    last_id = None
    while count < limit if limit else True:
        chunk_query = (
            {'$and': [query, {'_id': {'$gt': last_id}}]}
            if last_id is not None else query
        )
        docs = list(raw_collection.find(chunk_query, projection).sort('_id', 1).limit(CHUNK_SIZE))
        if not docs:
            break

        for doc in docs:
            transformed, changed = transform(doc[top_level_field], nested_field_path)
            if changed:
                raw_collection.update_one(
                    {'_id': doc['_id']},
                    {'$set': {top_level_field: transformed}},
                )
                count += 1
            if limit and count >= limit:
                break

        last_id = docs[-1]['_id']
        print(f'Updated {count} nested-array records so far...')

    return count


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
    encr_schema, traverses_array = _encryption_schema_info(
        Model, plain_field_name, encrypted_field_name)
    if encr_schema is not None:
        assert isinstance(encr_schema, schema.Binary) or _is_encrypted_list_schema(encr_schema)
    elif remove_unencrypted:
        raise AssertionError(
            f'Cannot use --remove-unencrypted because {encrypted_field_name!r} '
            'is not present in model schema yet')
    if remove_unencrypted:
        if '.' not in plain_field_name:
            plain_prop = Model.__dict__[plain_field_name]  # getattr() better but needs Ming fix released
            if _is_encrypted_list_schema(encr_schema):
                assert hasattr(plain_prop, 'encrypted_field')
            else:
                assert isinstance(plain_prop, DecryptedProperty)
            assert plain_prop.encrypted_field == encrypted_field_name

    # TODO: figure out how it works with inheritance

    sess = session(Model)
    m = mapper(Model)
    raw_collection = sess.impl.db[m.collection.m.collection_name]

    if traverses_array:
        plain_field_path = _split_field_path(plain_field_name)
        encrypted_field_path = _split_field_path(encrypted_field_name)
        assert plain_field_path[:-1] == encrypted_field_path[:-1]

        encrypted_count = _update_nested_array_records(
            raw_collection,
            plain_field_name,
            lambda value, nested_path: _encrypt_nested_array_value(
                Model,
                value,
                nested_path,
                encrypted_field_path[-1],
                encr_schema,
                redo_all,
            ),
            limit,
        )
        print(
            f'Encrypted {encrypted_count} {class_name} records with '
            f'nested-array {plain_field_name} values')

        if remove_unencrypted:
            removed_count = _update_nested_array_records(
                raw_collection,
                plain_field_name,
                _remove_nested_array_value,
                limit,
            )
            print(
                f'Removed {removed_count} {class_name} unencrypted '
                f'nested-array {plain_field_name} values')
        return

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
                '$set': {encrypted_field_name: _encrypt_field_value(Model, bulk_val, encr_schema)},
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
            encr_val = _encrypt_field_value(Model, val, encr_schema)
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
