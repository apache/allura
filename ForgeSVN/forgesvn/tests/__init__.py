# -*- coding: utf-8 -*-

## Make our own SVN tool test decorator
from allura.tests.decorators import with_tool

with_svn = with_tool('test', 'SVN', 'src', 'SVN')
