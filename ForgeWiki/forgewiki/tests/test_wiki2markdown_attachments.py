import os
from cStringIO import StringIO

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from forgewiki.command import wiki2markdown
from allura import model as M
from forgewiki import model as WM
from pylons import c

test_config = 'test.ini#main'

def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()

def test_wiki2markdown_attachments():
    output_dir = u'/tmp/wiki2markdown'
    projects = M.Project.query.find().all()

    for p in projects:
        wiki_app = p.app_instance('wiki')
        if wiki_app is None:
            continue
        c.app = wiki_app
        pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        for p in pages:
            p.attach('foo.text', StringIO('Hello, world!'))
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()

    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--extract-only', '--output-dir', output_dir, 'attachments'])
    cmd.command()

    projects = M.Project.query.find().all()
    for p in projects:
        wiki_app = p.app_instance('wiki')
        if wiki_app is None:
            continue

        pid = "%s" % p._id
        file_path = os.path.join(output_dir, pid, "attachments.json")
        assert os.path.isfile(file_path)

    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--load-only', '--output-dir', '/tmp/wiki2markdown', 'attachments'])
    cmd.command()

    for p in projects:
        wiki_app = p.app_instance('wiki')
        if wiki_app is None:
            continue

        pages = WM.Page.query.find(dict(app_config_id=wiki_app.config._id)).all()
        for p in pages:
            assert '[foo.text](' in p.text
            assert 'attachment/foo.text)' in p.text
