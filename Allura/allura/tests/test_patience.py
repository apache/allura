from os import path, environ
from collections import defaultdict

from allura.lib import patience

def text2lines(text):
    return [l + '\n' for l in text.split('\n')]

def test_region():
    r = patience.Region('foobar')
    r2 = r.clone()
    assert id(r) != id(r2)
    assert '-'.join(r) == '-'.join(r2)
    subr = r[1:5]
    assert type(subr) is type(r)
    assert ''.join(subr) == ''.join(r)[1:5]
    repr(r)
    repr(patience.Region('fffffffffffffffffffffffffffffffffffffffff'))

def test_unified_diff():
    text1 = '''\
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand
from paste.script.appinstall import SetupCommand
from paste.script.appinstall import SetupCommand
from paste.script.appinstall import SetupCommand
from paste.deploy import appconfig
'''
    text2 = '''\
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.deploy import loadapp
from paste.script.appinstall import SetupCommand2
from paste.script.appinstall import SetupCommand3
from paste.script.appinstall import SetupCommand4
from paste.deploy import appconfig
'''
    line_uni_diff = '''\
 from paste.deploy import loadapp
 from paste.deploy import loadapp
 from paste.deploy import loadapp
-from paste.script.appinstall import SetupCommand
-from paste.script.appinstall import SetupCommand
-from paste.script.appinstall import SetupCommand
-from paste.script.appinstall import SetupCommand
+from paste.script.appinstall import SetupCommand2
+from paste.script.appinstall import SetupCommand3
+from paste.script.appinstall import SetupCommand4
 from paste.deploy import appconfig'''

    line_diff = '''\
 from paste.deploy import loadapp
''' + line_uni_diff

    lines1 = text2lines(text1)
    lines2 = text2lines(text2)
    diff = patience.unified_diff(lines1, lines2)
    diff = ''.join(diff)
    assert diff == '''\
---  
+++  
@@ -2,9 +2,8 @@
%s
 
''' % line_uni_diff, '=' + diff + '='

    sm = patience.SequenceMatcher(None, lines1, lines2)
    buf = ''
    for prefix, line in patience.diff_gen(lines1, lines2, sm.get_opcodes()):
        assert prefix[1] == ' '
        buf += prefix[0] + line
    assert buf == line_diff + '\n \n', '=' + buf + '='
