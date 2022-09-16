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

from dateutil.parser import parse

from ming.odm import ThreadLocalORMSession
import webtest

from allura.tests import TestController
from allura.tests.decorators import with_discussion

from allura import model as M
from forgeimporters.forge import discussion
from forgediscussion import utils


class TestDiscussionImporter(TestCase):

    def setup_method(self, method):
        self.patcher_g = mock.patch('forgeimporters.base.g', mock.MagicMock())
        self.patcher_g.start()

    def teardown_method(self, method):
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
                                'author_icon_url': 'bla',
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
        importer.get_user = mock.Mock(side_effect=[admin])

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
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
            import_id={'source': 'Allura'}
        )

        h.push_config.assert_called_once_with(c, app=app)

        forum_json = _json['forums'][0]
        new_forum = self.__get_forum_dict(app, forum_json)

        utils.create_forum.assert_called_once_with(app, new_forum=new_forum)
        forum.get_discussion_thread(
              dict(headers=dict(Subject=_json["forums"][0]["threads"][0]["subject"])))
        importer.add_posts.assert_called_once_with(
                                    thread1,
                                    _json["forums"][0]["threads"][0]["posts"],
                                    app
        )

        m.AuditLog.log.assert_called_once_with(
                        "import tool mount_point from exported Allura JSON",
                        project=project,
                        user=user,
                        url='foo'
                    )
        g.post_event.assert_called_once_with("project_updated")

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_unicode(self, tlos, h, session, m, g, c):
        """ This method tests if the import tool method supports unicode characters """

        importer = discussion.ForgeDiscussionImporter()

        # Creating the json to test for
        _json = {
            "forums": [{
                "shortname": "general",
                "_id": "538f7240f697c62562ed9e6f",
                "description": "Forum about anything you want to talk about.",
                "name": "General Discussion",
                "threads": [{
                        "limit": None,
                        "discussion_id": "538f7240f697c62562ed9e6f",
                        "_id": "88983164e3",
                        "posts": [{
                            "attachments": [],
                            "author": "admin1",
                            "timestamp": "2020-01-29 22:32:00.584000",
                            "author_icon_url": "bla",
                            "text": "test with un\u00ef\u00e7\u00f8\u2202\u00e9 text",
                            "last_edited": None,
                            "slug": "0e0e",
                            "subject": "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
                        }],
                        "page": None,
                        "subject": "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
                    }]
                }]
        }

        importer._load_json = mock.Mock(return_value=_json)

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []
        utils.create_forum = mock.Mock()
        forum = mock.Mock()
        thread1 = mock.Mock()
        p = mock.Mock()
        thread1.add_post = mock.Mock(return_value=p)
        forum.get_discussion_thread.return_value = (thread1, mock.Mock())
        utils.create_forum.return_value = forum
        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()
        admin = mock.Mock(is_anonymous=lambda: False)
        admin._id = 1
        importer.get_user = mock.Mock(return_value=admin)
        importer.annotate_text = mock.Mock(return_value='aa')

        importer.import_tool(project, user, mount_point='mount_point', mount_label='mount_label')

        project.install_app.assert_called_once_with(
            'discussion', 'mount_point', 'mount_label',
            import_id={'source': 'Allura'}
        )

        forum_json = _json["forums"][0]
        new_forum = self.__get_forum_dict(app, forum_json)

        utils.create_forum.assert_called_once_with(app, new_forum=new_forum)
        forum.get_discussion_thread.assert_called_once_with(dict(
            headers=dict(Subject=_json["forums"][0]["threads"][0]["subject"])
            ))

        importer.get_user.assert_called_once_with('admin1')

        self.assertEqual(h.push_config.call_args_list, [
            mock.call(c, app=app),
            mock.call(c, user=admin, app=app)
        ])

        post = _json["forums"][0]["threads"][0]["posts"][0]
        thread1.add_post.assert_called_once_with(
            subject=post["subject"],
            text='aa',
            timestamp=parse(post["timestamp"]),
            ignore_security=True,
            parent_id=None
        )
        importer.annotate_text.assert_called_once_with(
                post["text"],
                admin,
                post["author"]
        )
        p.add_multiple_attachments.assert_called_once_with([])

        g.post_event.assert_called_once_with('project_updated')

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_multiple_forums(self, tlos, h, session, m, g, c):
        """ This test tests if it is possible to create a discussion with multiple forums """

        importer = discussion.ForgeDiscussionImporter()

        _json = {
            "forums": [
                {
                    "shortname": "general",
                    "description": "Forum about anything you want to talk about.",
                    "name": "General Discussion",
                    "threads": []
                },
                {
                    "shortname": "dev",
                    "description": "Forum for Devs.",
                    "name": "Developers' Corner",
                    "threads": []
                },
                {
                    "shortname": "announcements",
                    "description": "Announcements are posted here",
                    "name": "Announcements",
                    "threads": []
                },
                {
                    "shortname": "cc",
                    "description": "Forum about improvements of our codebase",
                    "name": "Clean Code",
                    "threads": []
                }
            ]
        }

        importer._load_json = mock.Mock(return_value=_json)
        importer.add_posts = mock.Mock()
        importer._clear_forums = mock.Mock()

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        utils.create_forum = mock.Mock()
        forum = mock.Mock()
        utils.create_forum.return_value = forum

        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        h.push_config.assert_called_once_with(c, app=app)
        importer._clear_forums.assert_called_once_with(app)

        forum0 = self.__get_forum_dict(app, _json['forums'][0])
        forum1 = self.__get_forum_dict(app, _json['forums'][1])
        forum2 = self.__get_forum_dict(app, _json['forums'][2])
        forum3 = self.__get_forum_dict(app, _json['forums'][3])

        utils.create_forum.assert_has_calls([
            mock.call(app, new_forum=forum0),
            mock.call(app, new_forum=forum1),
            mock.call(app, new_forum=forum2),
            mock.call(app, new_forum=forum3)
        ])

        forum.get_discussion_thread.assert_not_called()
        importer.add_posts.assert_not_called()

        m.AuditLog.log.assert_called_once()
        g.post_event.assert_called_once()

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_multiple_threads(self, tlos, h, session, m, g, c):
        """ This method tests if import_tool can handle multiple threads """

        importer = discussion.ForgeDiscussionImporter()

        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "shortname": "general",
                "name": "General Discussion",
                "threads": [
                        {
                            "page": None,
                            "subject": "Thread0",
                            "posts": []
                        },
                        {
                            "page": None,
                            "subject": "Thread1",
                            "posts": []
                        },
                        {
                            "page": None,
                            "subject": "Thread2",
                            "posts": []
                        },
                        {
                            "page": None,
                            "subject": "Thread3",
                            "posts": []
                        },
                        {
                            "page": None,
                            "subject": "Thread4",
                            "posts": []
                        }
                    ]}
                ]
            }

        importer._load_json = mock.Mock(return_value=_json)
        importer.add_posts = mock.Mock()
        importer._clear_forums = mock.Mock()

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        utils.create_forum = mock.Mock()
        forum = mock.Mock()
        forum.get_discussion_thread.return_value = (mock.Mock(), mock.Mock())

        utils.create_forum.return_value = forum

        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        project.install_app.assert_called_once_with(
                'discussion',
                'mount_point',
                'mount_label',
                import_id={'source': 'Allura'}
        )
        h.push_config.assert_called_once_with(c, app=app)

        utils.create_forum.assert_called_once()

        thread_json = _json["forums"][0]["threads"]
        forum.get_discussion_thread.assert_has_calls([
            mock.call(dict(headers=dict(Subject=thread_json[0]["subject"]))),
            mock.call(dict(headers=dict(Subject=thread_json[1]["subject"]))),
            mock.call(dict(headers=dict(Subject=thread_json[2]["subject"]))),
            mock.call(dict(headers=dict(Subject=thread_json[3]["subject"]))),
            mock.call(dict(headers=dict(Subject=thread_json[4]["subject"])))
        ])

        self.assertEqual(importer.add_posts.call_count, 5)
        m.AuditLog.log.assert_called_once()
        g.post_event.assert_called_once()

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_forum_import_id(self, tlos, h, session, m, g, c):
        """ This method tests if an import id is added to a forum """

        importer = discussion.ForgeDiscussionImporter()

        # Test with import id
        import_id = "qwert258"
        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "shortname": "general",
                "name": "General Discussion",
                "import_id": import_id,
                "threads": []
                }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        importer.add_posts = mock.Mock()
        importer._clear_forums = mock.Mock()

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        forum = mock.Mock()
        utils.create_forum = mock.Mock(return_value=forum)
        forum.get_discussion_thread.return_value = (mock.Mock(), mock.Mock())

        utils.create_forum.return_value = forum

        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        self.assertEqual(import_id, forum.import_id)

        # Test without import id
        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "shortname": "general",
                "name": "General Discussion",
                "threads": []
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        forum = mock.Mock()
        forum.import_id = ''
        utils.create_forum(return_value=forum)

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        self.assertEqual('', forum.import_id)

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_thread_import_id(self, tlos, h, session, m, g, c):
        """ This method tests if an import id is assigned to a thread """

        importer = discussion.ForgeDiscussionImporter()

        # Test with import id
        import_id = "qwert123"
        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "shortname": "general",
                "name": "General Discussion",
                "threads": [{
                        "limit": None,
                        "posts": [],
                        "subject": "Thread",
                        "import_id": import_id
                    }]
                }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        importer.add_posts = mock.Mock()
        importer._clear_forums = mock.Mock()

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        forum = mock.Mock()
        utils.create_forum = mock.Mock(return_value=forum)
        thread = mock.Mock()
        forum.get_discussion_thread.return_value = (thread, mock.Mock())

        utils.create_forum.return_value = forum

        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        self.assertEqual(import_id, thread.import_id)

        # Test with no import id
        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "shortname": "general",
                "name": "General Discussion",
                "threads": [{
                        "limit": None,
                        "posts": [],
                        "subject": "Thread",
                    }]
                }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        thread = mock.Mock()
        thread.import_id = ''

        forum.get_discussion_thread.return_value = (thread, mock.Mock())

        importer.import_tool(project, user, 'mount_point', 'mount_label')

        self.assertEqual('', thread.import_id)

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'g')
    @mock.patch.object(discussion, 'M')
    @mock.patch.object(discussion, 'session')
    @mock.patch.object(discussion, 'h')
    @mock.patch.object(discussion, 'ThreadLocalORMSession')
    def test_import_tool_missing_keys(self, tlos, h, session, m, g, c):
        """ This method tests if missing keys are handled correctly """

        # Check when shortname missing
        _json = {
            "forums": [{
                "description": "Forum about anything you want to talk about.",
                "name": "General Discussion",
                "threads": []
            }]
        }

        importer = discussion.ForgeDiscussionImporter()
        importer._load_json = mock.Mock(return_value=_json)

        u = mock.Mock(_id=123, is_anonymous=lambda: False)
        importer.get_user = mock.Mock(return_value=u)

        project, user = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        forum = mock.Mock()
        utils.create_forum = mock.Mock(return_value=forum)
        thread = mock.Mock()
        forum.get_discussion_thread.return_value = (thread, mock.Mock())

        utils.create_forum.return_value = forum

        g.post_event = mock.Mock()
        m.AuditLog.log = mock.Mock()

        self.__check_missing(project, user, importer, h, g, utils)

        # Check when description is missing
        _json = {
            "forums": [{
                "shortname": "general",
                "name": "General Discussion",
                "threads": []
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        self.__check_missing(project, user, importer, h, g, utils)
        utils.create_forum.assert_not_called()

        # Check when name is missing
        _json = {
            "forums": [{
                "shortname": "general",
                "description": "Description of forum",
                "threads": []
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        self.__check_missing(project, user, importer, h, g, utils)
        utils.create_forum.assert_not_called()

        # Check when threads are missing
        _json = {
            "forums": [{
                "shortname": "general",
                "description": "Description of forum",
                "name": "General Discussion"
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        self.__check_missing(project, user, importer, h, g, utils)

        # Check when subject of threads are missing
        _json = {
            "forums": [{
                "shortname": "general",
                "description": "Description of forum",
                "name": "General Discussion",
                "threads": [{
                   "posts": []
                }]
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        self.__check_missing(project, user, importer, h, g, utils)

        # Check when posts of threads are missing
        _json = {
            "forums": [{
                "shortname": "general",
                "description": "Description of forum",
                "name": "General Discussion",
                "threads": [{
                    "subject": "Thread"
                }]
            }]
        }

        importer._load_json = mock.Mock(return_value=_json)
        self.__check_missing(project, user, importer, h, g, utils)

        self.assertEqual(h.make_app_admin_only.call_count, 6)

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts(self, h, c):
        """ This methods tests if a post is correctly added to a thread """

        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "attachments": [],
            "author": "admin1",
            "timestamp": "2020-01-29 22:30:42.497000",
            "text": "foo",
            "subject": "Foo subject"
        }]

        importer.add_posts(thread, _json, app)

        importer.get_user.assert_called_once_with('admin1')
        h.push_config.assert_called_once_with(c, user=user, app=app)
        thread.add_post.assert_called_once_with(
                subject=_json[0]['subject'],
                text='foo',
                timestamp=parse(_json[0]['timestamp']),
                ignore_security=True,
                parent_id=None
        )
        post.add_multiple_attachments.assert_called_once_with([])

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_with_many_posts(self, h, c):
        """ This methods tests if many posts of a thread are added to this thread """

        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo0",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo1",
                "subject": "Foo subject"
            },
            {

                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo2",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo3",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo4",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo5",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo6",
                "subject": "Foo subject"
            },
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "foo7",
                "subject": "Foo subject"
            }
        ]

        importer.add_posts(thread, _json, app)

        self.assertEqual(8, importer.get_user.call_count)
        self.assertEqual(8, h.push_config.call_count)
        self.assertEqual(8, thread.add_post.call_count)
        self.assertEqual(8, post.add_multiple_attachments.call_count)

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_with_unicode(self, h, c):
        """ This method tests if it is possible to add posts which contain unicode characters in subject and text """

        importer, app, thread, user, post = self.__init_add_posts_tests()
        importer.annotate_text.return_value = "test with un\u00ef\u00e7\u00f8\u2202\u00e9 text"

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "test with un\u00ef\u00e7\u00f8\u2202\u00e9 text",
                "subject": "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
            }
        ]

        importer.add_posts(thread, _json, app)

        importer.get_user.assert_called_once()
        h.push_config.assert_called_once()
        thread.add_post.assert_called_once_with(
            subject=_json[0]['subject'],
            text=importer.annotate_text.return_value,
            timestamp=parse(_json[0]['timestamp']),
            ignore_security=True,
            parent_id=None
        )
        post.add_multiple_attachments.assert_called_once_with([])

    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_with_last_edited(self, h, c):
        """ This method tests if the last edited attribute of a post is correctly updated if specified """

        # Test with legit timestamp
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "test",
                "subject": "post with last edited",
                "last_edited": "2020-01-29 22:47:52.951000"
            }
        ]

        importer.add_posts(thread, _json, app)

        self.assertEqual(post.last_edit_date, parse(_json[0]['last_edited']))

        # Test with none
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "test",
                "subject": "post with last edited",
                "last_edited": None
            }
        ]

        post.last_edit_date = '-'
        importer.add_posts(thread, _json, app)

        self.assertEqual(post.last_edit_date, '-')

        # Test with no last edited
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "test",
                "subject": "post with last edited",
            }
        ]

        post.last_edit_date = '-'
        importer.add_posts(thread, _json, app)

        self.assertEqual(post.last_edit_date, '-')

        # Test with junk last edited
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [
            {
                "attachments": [],
                "author": "admin1",
                "timestamp": "2020-01-29 22:30:42.497000",
                "text": "test",
                "subject": "post with last edited",
                "last_edited": "asdf asd"
            }
        ]

        try:
            importer.add_posts(thread, _json, app)
            self.fail("add_posts() didn't throw exception even last_edited was junk data")
        except Exception:
            pass

    @mock.patch.object(discussion, 'File')
    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_with_attachments(self, h, c, File):
        """ This method checks if add_posts supports posts with attachment """

        importer, app, thread, user, post = self.__init_add_posts_tests()
        File.side_effect = ['a1', 'a2', 'a3']

        _json = [
            {
                "attachments": [
                    {
                        "url": "http://www.foo.com/attachment0",
                        "path": "path/to/attachment0",
                        "bytes": 145
                    },
                    {
                        "url": "http://www.foo.com/attachment1",
                        "path": "path/to/attachment1",
                        "bytes": 184
                    },
                    {
                        "url": "http://www.foo.com/attachment2",
                        "path": "path/to/attachment2",
                        "bytes": 145
                    },
                ],
                "author": "user02",
                "timestamp": "2020-01-29 22:42:58.478000",
                "text": "asdf as",
                "subject": "topic with attachments"
            }
        ]

        importer.add_posts(thread, _json, app)

        post.add_multiple_attachments.assert_called_once()
        self.assertEqual(File.call_args_list, [
            mock.call('http://www.foo.com/attachment0'),
            mock.call('http://www.foo.com/attachment1'),
            mock.call('http://www.foo.com/attachment2'),
        ])

    @mock.patch.object(discussion, 'File')
    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_nested_posts(self, h, c, File):
        """ This method tests if nested posts were handled correctly """

        # Test with author attribute missing
        importer, app, _, user, post = self.__init_add_posts_tests()
        thread = mock.Mock()
        thread.add_post.side_effect = [
            mock.Mock(_id=0),
            mock.Mock(_id=1),
            mock.Mock(_id=2),
            mock.Mock(_id=3),
            mock.Mock(_id=4),
            mock.Mock(_id=5),
        ]

        _json = [
            {
              "attachments": [],
              "author": "admin1",
              "timestamp": "2020-01-29 22:39:31.483000",
              "text": "hi",
              "slug": "0d1d",
              "subject": "topic with lots of replies"
            },
            {
              "attachments": [],
              "author": "admin1",
              "timestamp": "2020-01-29 22:39:43.525000",
              "text": "hello",
              "slug": "0d1d/d421",
              "subject": "topic with lots of replies"
            },
            {
              "attachments": [],
              "author": "admin1",
              "timestamp": "2020-01-29 22:39:50.086000",
              "text": "goodbye",
              "slug": "0d1d/d421/f37d",
              "subject": "topic with lots of replies"
            },
            {
              "attachments": [],
              "author": "admin1",
              "timestamp": "2020-01-29 22:42:13.740000",
              "text": "hi again",
              "slug": "012f",
              "subject": "topic with lots of replies"
            },
            {
              "attachments": [],
              "author": "user02",
              "timestamp": "2020-01-29 22:42:51.645000",
              "text": "hi there",
              "slug": "012f/211a",
              "subject": "topic with lots of replies"
            },
            {
              "attachments": [],
              "author": "user02",
              "timestamp": "2020-01-29 22:42:58.478000",
              "text": "hi here",
              "slug": "0d1d/00a0",
              "subject": "topic with lots of replies"
            }
         ]

        importer.add_posts(thread, _json, app)

        thread.add_post.assert_has_calls([
            mock.call(
                subject=_json[0]['subject'],
                text='foo',
                timestamp=parse(_json[0]['timestamp']),
                ignore_security=True,
                parent_id=None
            ),
            mock.call(
                subject=_json[1]['subject'],
                text='foo',
                timestamp=parse(_json[1]['timestamp']),
                ignore_security=True,
                parent_id=0
            ),
            mock.call(
                subject=_json[2]['subject'],
                text='foo',
                timestamp=parse(_json[2]['timestamp']),
                ignore_security=True,
                parent_id=1
            ),
            mock.call(
                subject=_json[3]['subject'],
                text='foo',
                timestamp=parse(_json[3]['timestamp']),
                ignore_security=True,
                parent_id=None
            ),
            mock.call(
                subject=_json[4]['subject'],
                text='foo',
                timestamp=parse(_json[4]['timestamp']),
                ignore_security=True,
                parent_id=3
            ),
            mock.call(
                subject=_json[5]['subject'],
                text='foo',
                timestamp=parse(_json[5]['timestamp']),
                ignore_security=True,
                parent_id=0
            )
        ])

    @mock.patch.object(discussion, 'File')
    @mock.patch.object(discussion, 'c')
    @mock.patch.object(discussion, 'h')
    def test_add_posts_with_missing_keys(self, h, c, File):
        """ This method checks if add_posts will throw an error if required keys are missing """

        # Test with author attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "subject": "foo",
            "text": "foo",
            "timestamp": "2020-01-29 22:42:58.478000",
            "attachments": []
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

        # Test with subject attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "author": "admin1",
            "text": "foo",
            "timestamp": "2020-01-29 22:42:58.478000",
            "attachments": []
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

        # Test with text attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "author": "admin1",
            "timestamp": "2020-01-29 22:42:58.478000",
            "subject": "foo",
            "attachments": []
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

        # Test with timestamp attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "author": "admin1",
            "text": "foo",
            "subject": "foo",
            "attachments": []
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

        # Test with attachments attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "author": "admin1",
            "text": "foo",
            "subject": "foo",
            "timestamp": "2020-01-29 22:42:58.478000"
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

        # Test with url of attachments attribute missing
        importer, app, thread, user, post = self.__init_add_posts_tests()

        _json = [{
            "author": "admin1",
            "text": "foo",
            "subject": "foo",
            "timestamp": "2020-01-29 22:42:58.478000",
            "attachments": [
                {
                    "byte": 147,
                    "path": "path/to/attachment"
                }
            ]
        }]

        self.__check_posts_exceptions(importer, thread, _json, app)

    def __check_posts_exceptions(self, importer, thread, posts, app):
        try:
            importer.add_posts(thread, posts, app)
            self.fail("add_posts() didn't throw an exception even though attribute are missing")
        except Exception:
            pass

    def __init_add_posts_tests(self):
        importer = discussion.ForgeDiscussionImporter()

        user1 = mock.Mock(_id=1, is_anonymous=lambda: False)

        importer.get_user = mock.Mock(return_value=user1)
        importer.annotate_text = mock.Mock(return_value='foo')

        project, _ = mock.Mock(), mock.Mock()
        app = project.install_app.return_value
        app.config.options.mount_point = 'mount_point'
        app.config.options.import_id = {'source': 'Allura'}
        app.config.options.get = lambda *a: getattr(app.config.options, *a)
        app.url = 'foo'
        app.forums = []

        thread = mock.Mock()
        post = mock.Mock()
        thread.add_post.return_value = post

        return importer, app, thread, user1, post

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
        return_text = f'*Originally created by:* {username}\n\n{text}'

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

    def test_annotate_text_with_unicode(self):
        """ This method tests if annotate text can handle unicode characters """

        importer = discussion.ForgeDiscussionImporter()

        # unicode in text of an existing user
        text = "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
        user = mock.Mock(_id=1, is_anonymous=lambda: False)
        username = "username1"
        try:
            importer.annotate_text(text, user, username)
        except Exception:
            self.fail("annotate_text() can't handle unicode characters")

        # unicode in text of a not existing user
        text = "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
        user = mock.Mock(is_anonymous=lambda: True)
        username = "user2"

        try:
            importer.annotate_text(text, user, username)
        except Exception:
            self.fail("annotate_text() can't handle unicode characters")

        # unicode in text of an anonymous user
        text = "post with un\u00ef\u00e7\u00f8\u2202\u00e9"
        user = mock.Mock(is_anonymous=lambda: True)
        username = "*anonymous"

        try:
            importer.annotate_text(text, user, username)
        except Exception:
            self.fail("annotate_text() can't handle unicode characters")

    def test_annotate_text_with_junk(self):
        """ This test tests if the annotate_text method correctly handles junk data """

        importer = discussion.ForgeDiscussionImporter()

        user = None
        text = None
        username = None

        self.assertEqual(importer.annotate_text(text, user, username), '')

        text = 'foo'
        self.assertEqual(importer.annotate_text(text, user, username), text)

    def __get_forum_dict(self, app, forum_json):
        new_forum = dict(
            app_config_id=app.config._id,
            shortname=forum_json['shortname'],
            description=forum_json['description'],
            name=forum_json['name'],
            create='on',
            parent='',
            members_only=False,
            anon_posts=False,
            monitoring_email=None
        )

        return new_forum

    def __check_missing(self, project, user, importer, h, g, utils):
        try:
            importer.import_tool(project, user, 'mount_point', 'mount_label')
            self.fail("import_tool() didn't raise Exception")
        except Exception:
            pass

        print("after try except")

        g.post_event.assert_not_called()


class TestForgeDiscussionController(TestController, TestCase):

    def setup_method(self, method):
        super().setup_method(method)

    @with_discussion
    def test_index(self):
        r = self.app.get('/p/test/admin/ext/import/forge-discussion/')
        self.assertIsNotNone(r.html.find(attrs=dict(name="discussions_json")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_label")))
        self.assertIsNotNone(r.html.find(attrs=dict(name="mount_point")))

    @with_discussion
    @mock.patch('forgeimporters.forge.discussion.save_importer_upload')
    @mock.patch('forgeimporters.base.import_tool')
    def test_create(self, import_tool, siu):
        project = M.Project.query.get(shortname='test')
        params = {
            'discussions_json': webtest.Upload('discussions.json',
                                               b'{"key": "val"}'),
            'mount_label': 'mylabel',
            'mount_point': 'mymount',
        }
        r = self.app.post('/p/test/admin/ext/import/forge-discussion/create', params, status=302)
        self.assertEqual(r.location, 'http://localhost/p/test/admin/')
        siu.assert_called_once_with(project,
                                    'discussions.json',
                                    '{"key": "val"}'
                                    )
        self.assertEqual('mymount', import_tool.post.call_args[1]['mount_point'])
        self.assertEqual('mylabel', import_tool.post.call_args[1]['mount_label'])

    @with_discussion
    @mock.patch('forgeimporters.forge.discussion.save_importer_upload')
    @mock.patch('forgeimporters.base.import_tool')
    def test_create_limit(self, import_tool, siu):
        project = M.Project.query.get(shortname='test')
        project.set_tool_data('ForgeDiscussionImporter', pending=1)
        ThreadLocalORMSession.flush_all()
        params = {
            'discussions_json': webtest.Upload('discussions.json', b'{"key": "val"}'),
            'mount_label': 'mylabel',
            'mount_point': 'mymount',
        }
        r = self.app.post('/p/test/admin/ext/import/forge-discussion/create',
                          params,
                          status=302).follow()
        self.assertIn('Please wait and try again', r)
        self.assertEqual(import_tool.post.call_count, 0)
