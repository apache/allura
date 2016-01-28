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
import os

from nose.tools import assert_equal
from pylons import tmpl_context as c
from cStringIO import StringIO
from ming.orm import ThreadLocalORMSession
from cgi import FieldStorage

from allura import model as M
from forgediscussion.tests.functional.test_rest import TestDiscussionApiBase
from forgediscussion.model.forum import Forum


class TestBulkExport(TestDiscussionApiBase):

    def test_bulk_export(self):
        # Clear out some context vars, to properly simulate how this is run from the export task
        # Besides, it's better not to need c context vars
        c.app = c.project = None

        project = M.Project.query.get(shortname='test')
        discussion = project.app_instance('discussion')
        f = tempfile.TemporaryFile()
        discussion.bulk_export(f)
        f.seek(0)
        discussion = json.loads(f.read())
        forums = sorted(discussion['forums'], key=lambda x: x['name'])

        assert_equal(forums[0]['shortname'], u'general')
        assert_equal(
            forums[0]['description'], u'Forum about anything you want to talk about.')
        assert_equal(forums[0]['name'], u'General Discussion')
        forums[0]['threads'] = sorted(forums[0]['threads'],
                                      key=lambda x: x['posts'][0]['subject'])
        assert_equal(
            forums[0]['threads'][0]['posts'][0]['text'], u'Hi boys and girls')
        assert_equal(
            forums[0]['threads'][0]['posts'][0]['subject'], u'Hi guys')
        assert_equal(forums[0]['threads'][1]['posts'][0]['text'], u'1st post')
        assert_equal(
            forums[0]['threads'][1]['posts'][0]['subject'], u"Let's talk")
        assert_equal(forums[1]['shortname'], u'héllo')
        assert_equal(forums[1]['description'], u'Say héllo here')
        assert_equal(forums[1]['name'], u'Say Héllo')

    def test_export_with_attachments(self):
        project = M.Project.query.get(shortname='test')
        discussion = project.app_instance('discussion')
        post = Forum.query.get(shortname='general').sorted_threads[0].first_post
        test_file1 = FieldStorage()
        test_file1.name = 'file_info'
        test_file1.filename = 'test_file'
        test_file1.file = StringIO('test file1\n')
        post.add_attachment(test_file1)
        ThreadLocalORMSession.flush_all()

        f = tempfile.TemporaryFile()
        temp_dir = tempfile.mkdtemp()
        discussion.bulk_export(f, temp_dir, True)
        f.seek(0)
        discussion = json.loads(f.read())
        forums = sorted(discussion['forums'], key=lambda x: x['name'])
        threads = sorted(forums[0]['threads'], key=lambda x: x['subject'])
        file_path = os.path.join(
            'discussion',
            str(post.discussion_id),
            str(post.thread_id),
            post.slug,
            'test_file'
        )
        assert_equal(threads[0]['posts'][0]['attachments'][0]['path'], file_path)
        os.path.exists(file_path)
