# -*- coding: utf-8 -*-

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

#-*- python -*-

import tempfile
import json
from nose.tools import assert_equal

from allura import model as M
from forgediscussion.tests.functional.test_rest import TestDiscussionApiBase


class TestBulkExport(TestDiscussionApiBase):

    def test_bulk_export(self):
        project = M.Project.query.get(shortname='test')
        discussion = project.app_instance('discussion')
        f = tempfile.TemporaryFile()
        discussion.bulk_export(f)
        f.seek(0)
        discussion = json.loads(f.read())
        forums = sorted(discussion['forums'], key=lambda x: x['name'])

        assert_equal(forums[0]['shortname'], u'general')
        assert_equal(forums[0]['description'], u'Forum about anything you want to talk about.')
        assert_equal(forums[0]['name'], u'General Discussion')
        assert_equal(forums[0]['threads'][0]['posts'][0]['text'], u'Hi boys and girls')
        assert_equal(forums[0]['threads'][0]['posts'][0]['subject'], u'Hi guys')
        assert_equal(forums[0]['threads'][1]['posts'][0]['text'], u'1st post')
        assert_equal(forums[0]['threads'][1]['posts'][0]['subject'], u"Let's talk")
        assert_equal(forums[1]['shortname'], u'héllo')
        assert_equal(forums[1]['description'], u'Say héllo here')
        assert_equal(forums[1]['name'], u'Say Héllo')
