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

from ming.odm import ThreadLocalORMSession

from allura import model as M
from forgeimporters.forge import discussion
from forgediscussion import utils


class TestDiscussionImporter(TestCase):

    def setUp(self):
        super(TestDiscussionImporter, self).setUp()

        self.patcher_g = mock.patch('forgeimporters.base.g', mock.MagicMock())
        self.patcher_g.start()


    def tearDown(self):
        super(TestDiscussionImporter, self).tearDown()
        self.patcher_g.stop()


    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_with_general_discussion(self, tlos, h, session, m, g, c):
        """ This test creates a general discussion forum with one thread and one post from admin """
        importer = discussion.ForgeDiscussionImporter()
        _json = { 
            'forums': [{
                'shortname': 'general',
                '_id': '538f7240f697c62562ed9e6f',
                'description': 'Forum about anything you want to talk about.',
                'name': 'General Discussion',
                'threads': [
                    {
                        'limit': None,
                        'discussion_id': '538f7240f697c62562ed9e6f',
                        '_id': 'ef260a33d2',
                        'page': None,
                        'subject': 'Thread1',
                        'posts': [
                            {
                                'attachments': [],
                                'author': 'admin1',
                                'timestamp': '2020-01-29 22:30:42.497000',
                                'author_icon_url': 'https://secure.gravatar.com/avatar/2ba5bfa33e6faca31f7dd150960ce926?r=pg&d=https%3A%2F%2F4.xb.sf.net%2Fnf%2F0%2F_ew_%2Ftheme%2Fsftheme%2Fimages%2Fsandiego%2Ficons%2Fdefault-avatar.png',
                                'text': 'hi',
                                'last_edited': None,
                                'slug': '00aa',
                                'subject':  'A post'
                            }
                        ]
                    }
                ]
            }]
        }
        importer._load_json = mock.Mock(return_value=_json)

        admin = mock.Mock(_id=1, is_anonymous=lambda: False)
        importer.get_user = mock.Mock(side_effect=[ admin ])

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = { 'source': 'Allura' }
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []
        utils.create_forum = mock.Mock()
        forum = mock.Mock()
        thread1 = mock.Mock()
        forum.get_discussion_thread.return_value = (thread1, mock.Mock())
        utils.create_forum.return_value = forum
        importer.add_posts = mock.Mock()
        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        importer.import_tool(project, user, mount_point='mount_point', mount_label='mount_label')

        project.install_app.assert_called_once_with(
            'discussion', 'mount_point', 'mount_label',
            import_id={ 'source': 'Allura' }
        )

        h.push_config.assert_called_once_with(c, app=app)

        forum_json = _json['forums'][0]
        new_forum = dict(
            app_config_id = app.config._id,
            shortname=forum_json['shortname'],
            description=forum_json['description'],
            name=forum_json['name'],
            create='on',
            parent='',
            members_only=False,
            anon_posts=False,
            monitoring_email=None
        )
        utils.create_forum.assert_called_once_with(app, new_forum=new_forum)
        forum.get_discussion_thread(dict(headers=dict(Subject=_json["forums"][0]["threads"][0]["subject"])))
        importer.add_posts.assert_called_once_with(thread1, _json["forums"][0]["threads"][0]["posts"], app)

        m.AuditLog.log.assert_called_once_with("import tool mount_point from exported Allura JSON", project=project, user=user, url='foo')
        g.post_event.assert_called_once_with("project_updated")


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
