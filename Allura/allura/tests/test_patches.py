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

import webob
from mock import patch
import pytest
import tg

from allura.lib import patches


def empty_func():
    pass


@patch.object(patches, 'request', webob.Request.blank('/foo/bar'))
def test_with_trailing_slash():
    patches.apply()
    with pytest.raises(webob.exc.HTTPMovedPermanently) as raised:
        tg.decorators.with_trailing_slash(empty_func)()
    assert raised.value.location == 'http://localhost/foo/bar/'


@patch.object(patches, 'request', webob.Request.blank('/foo/bar/?a=b'))
def test_with_trailing_slash_ok():
    patches.apply()
    # no exception raised
    tg.decorators.with_trailing_slash(empty_func)()


@patch.object(patches, 'request', webob.Request.blank('/foo/bar?foo=bar&baz=bam'))
def test_with_trailing_slash_qs():
    patches.apply()
    with pytest.raises(webob.exc.HTTPMovedPermanently) as raised:
        tg.decorators.with_trailing_slash(empty_func)()
    assert raised.value.location == 'http://localhost/foo/bar/?foo=bar&baz=bam'


@patch.object(patches, 'request', webob.Request.blank('/foo/bar/'))
def test_without_trailing_slash():
    patches.apply()
    with pytest.raises(webob.exc.HTTPMovedPermanently) as raised:
        tg.decorators.without_trailing_slash(empty_func)()
    assert raised.value.location == 'http://localhost/foo/bar'


@patch.object(patches, 'request', webob.Request.blank('/foo/bar?a=b'))
def test_without_trailing_slash_ok():
    patches.apply()
    # no exception raised
    tg.decorators.without_trailing_slash(empty_func)()


@patch.object(patches, 'request', webob.Request.blank('/foo/bar/?foo=bar&baz=bam'))
def test_without_trailing_slash_qs():
    patches.apply()
    with pytest.raises(webob.exc.HTTPMovedPermanently) as raised:
        tg.decorators.without_trailing_slash(empty_func)()
    assert raised.value.location == 'http://localhost/foo/bar?foo=bar&baz=bam'
