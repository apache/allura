# -*- coding: utf-8 -*-

## Make our own Mercurial tool test decorator
from allura.tests.decorators import with_tool

with_hg = with_tool('test', 'Hg', 'src-hg', 'Mercurial', type='hg')
