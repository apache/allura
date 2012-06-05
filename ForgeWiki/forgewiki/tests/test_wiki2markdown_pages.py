import os

from ming.orm.ormsession import ThreadLocalORMSession

from alluratest.controller import setup_basic_test, setup_global_objects
from forgewiki.command import wiki2markdown
from forgewiki import model as WM
from allura import model as M

test_config = 'test.ini#main'

def setUp(self):
    """Method called by nose before running each test"""
    setup_basic_test()
    setup_global_objects()

def test_wiki2markdown_pages():
    output_dir = u'/tmp/wiki2markdown'
    for p in WM.Page.query.find().all():
        p.text = "'''bold''' ''italics''"

    for p in M.Post.query.find().all():
        p.text = "'''bold''' ''italics''"
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--extract-only', '--output-dir', output_dir, 'pages'])
    cmd.command()

    projects = M.Project.query.find().all()
    for p in projects:
        wiki_app = p.app_instance('wiki')
        if wiki_app is None: 
            continue

        pid = "%s" % p._id
        file_path = os.path.join(output_dir, pid, "pages.json")
        assert os.path.isfile(file_path)

    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--load-only', '--output-dir', '/tmp/wiki2markdown', 'pages'])
    cmd.command()
    for p in WM.Page.query.find().all():
        assert "**bold** _italics_" in p.text

    for p in M.Post.query.find().all():
        assert "**bold** _italics_" in p.text
