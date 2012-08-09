# -*- coding: utf-8 -*-

## Make our own Git tool test decorator
from allura.tests.decorators import with_tool

with_git = with_tool('test', 'Git', 'src-git', 'Git', type='git')
