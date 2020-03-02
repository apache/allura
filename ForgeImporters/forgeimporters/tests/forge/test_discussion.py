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

from unittest import TestCase

import mock

from allura import model as M
from forgeimporters.forge import discussion

class TestDiscussionImporter(TestCase):

    def setUp(self):
        super(TestDiscussionImporter, self).setUp()

        self.patcher_g = mock.patch('forgeimporters.base.g', mock.MagicMock())
        self.patcher_g.start()


    def tearDown(self):
        super(TestDiscussionImporter, self).tearDown()
        self.patcher_g.stop()


    def test_annotate_text_with_existing_user(self):
        """ This test tests the annotate_text method if an existing user is passed as argument """

        importer = discussion.ForgeDiscussionImporter()
        
        # Creating a mock of an existing user
        user = mock.Mock(_id=1)
        user.is_anonymous.return_value = False
        username = "testUser123"

        self.assertEqual(importer.annotate_text('foo', user, username), 'foo')


    def test_annotate_text_with_not_existing_user(self):
        """ This test tests the annotate_text method with a not existing user """

        importer = discussion.ForgeDiscussionImporter()

        # Creating a not existing user
        user = mock.Mock(_id=1)
        user.is_anonymous.return_value = True
        username = "NotAAlluraUser"

        # Text of the post
        text = 'foo'

        # Text that the method should return
        return_text = '*Originally created by:* {username}\n\n{text}'.format(username=username, text=text)

        self.assertEqual(importer.annotate_text(text, user, username), return_text)


    def test_annotate_text_with_anonymous_user(self):
        """ This test tests the annotate_text method with an anonymous user """

        importer = discussion.ForgeDiscussionImporter()

        # Creating an anonymous user
        user = mock.Mock(_id=1)
        user.is_anonymous.return_value = True

        usernames = ['nobody', '*anonymous']

        text = 'foo'

        self.assertEqual(importer.annotate_text(text, user, usernames[0]), text)
        self.assertEqual(importer.annotate_text(text, user, usernames[1]), text)

        
    def test_annotate_text_with_junk(self):
        """ This test tests if the annotate_text method correctly handles junk data """

        importer = discussion.ForgeDiscussionImporter()

        user = None
        text = None
        username = None

        self.assertEqual(importer.annotate_text(text, user, username), '')

        text = 'foo'
        self.assertEqual(importer.annotate_text(text, user, username), text)
