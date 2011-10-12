import sys

from pylons import c

from allura.lib import helpers as h
from allura.model.repo import CommitDoc, TreeDoc, TreesDoc, DiffInfoDoc
from allura.model.repo import LastCommitDoc, CommitRunDoc
from allura.model.repo_refresh import refresh_repo

def main():
    if len(sys.argv) > 1:
        h.set_context('test')
        c.project.install_app('Git', 'code', 'Code', init_from_url='/home/rick446/src/forge')
        c.project.install_app('Hg', 'code2', 'Code2', init_from_url='/home/rick446/src/Kajiki')
    CommitDoc.m.remove({})
    TreeDoc.m.remove({})
    TreesDoc.m.remove({})
    DiffInfoDoc.m.remove({})
    LastCommitDoc.m.remove({})
    CommitRunDoc.m.remove({})

    h.set_context('test', 'code')
    refresh_repo(c.app.repo, notify=False)
    h.set_context('test', 'code2')
    refresh_repo(c.app.repo, notify=False)


if __name__ == '__main__':
    main()
    # dolog()
