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

def test_wiki2markdown_history():
    output_dir = u'/tmp/wiki2markdown'
    for p in WM.Page.query.find().all():
        for hist in WM.PageHistory.query.find(dict(artifact_id=p._id)).all():
            hist.data['text'] = "'''bold''' ''italics''"
    ThreadLocalORMSession.flush_all()
    ThreadLocalORMSession.close_all()
    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--extract-only', '--output-dir', output_dir, 'history'])
    cmd.command()

    projects = M.Project.query.find().all()
    for p in projects:
        wiki_app = p.app_instance('wiki')
        if wiki_app is None: 
            continue

        pid = "%s" % p._id
        file_path = os.path.join(output_dir, pid, "history.json")
        assert os.path.isfile(file_path)

    cmd = wiki2markdown.Wiki2MarkDownCommand('wiki2markdown')
    cmd.run([test_config, '--load-only', '--output-dir', '/tmp/wiki2markdown', 'history'])
    cmd.command()
    for p in WM.Page.query.find().all():
        for hist in WM.PageHistory.query.find(dict(artifact_id=p._id)).all():
            assert "**bold** _italics_" in hist.data['text']
