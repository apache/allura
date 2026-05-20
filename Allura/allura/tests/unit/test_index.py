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
import bson
import pytest

from allura.model.index import _dump_cls, _load_cls
from allura.model.repository import Commit


def test_dump_cls():
    assert _dump_cls(Commit) == b'\x80\x02callura.model.repository\nCommit\nq\x00.'


def test_roundtrip():
    assert _load_cls(_dump_cls(Commit)) is Commit


def test_load_cls_pickle_protocol_2():
    data = b'\x80\x02callura.model.repository\nCommit\nq\x00.'
    assert _load_cls(data) is Commit


def test_load_cls_pickle_protocol_0():
    data = bson.Binary(b'callura.model.repository\nCommit\np0\n.')
    assert _load_cls(data) is Commit


def test_load_cls_legacy_repo_module():
    # legacy data that still may be in mongo records:
    # the pre-rename module path allura.model.repo (now a backward-compat shim but still must load)
    data = bson.Binary(b'callura.model.repo\nCommit\np1\n.')
    assert _load_cls(data) is Commit


def test_load_cls_rejects_unknown_prefix():
    with pytest.raises(ValueError):
        _load_cls(b'xnot a pickle')


def test_load_cls_rejects_truncated():
    with pytest.raises(ValueError):
        _load_cls(b'callura.model.repository')
