"""ASCII, Dammit

Stupid library to turn MS chars (like smart quotes) and ISO-Latin
chars into ASCII, dammit. Will do plain text approximations, or more
accurate HTML representations. Can also be jiggered to just fix the
smart quotes and leave the rest of ISO-Latin alone.

Sources:
 http://www.cs.tut.fi/~jkorpela/latin1/all.html
 http://www.webreference.com/html/reference/character/isolat1.html

1.0 Initial Release (2004-11-28)

The author hereby irrevocably places this work in the public domain.
To the extent that this statement does not divest the copyright,
the copyright holder hereby grants irrevocably to every recipient
all rights in this work otherwise reserved under copyright.
"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
__author__ = "Leonard Richardson (leonardr@segfault.org)"
__version__ = "$Revision: 1.3 $"
__date__ = "$Date: 2009/04/28 10:45:03 $"
__license__ = "Public domain"

import re
import types

CHARS = {b'\x80': ('EUR', 'euro'),
         b'\x81': ' ',
         b'\x82': (',', 'sbquo'),
         b'\x83': ('f', 'fnof'),
         b'\x84': (',,', 'bdquo'),
         b'\x85': ('...', 'hellip'),
         b'\x86': ('+', 'dagger'),
         b'\x87': ('++', 'Dagger'),
         b'\x88': ('^', 'caret'),
         b'\x89': '%',
         b'\x8A': ('S', 'Scaron'),
         b'\x8B': ('<', 'lt;'),
         b'\x8C': ('OE', 'OElig'),
         b'\x8D': '?',
         b'\x8E': 'Z',
         b'\x8F': '?',
         b'\x90': '?',
         b'\x91': ("'", 'lsquo'),
         b'\x92': ("'", 'rsquo'),
         b'\x93': ('"', 'ldquo'),
         b'\x94': ('"', 'rdquo'),
         b'\x95': ('*', 'bull'),
         b'\x96': ('-', 'ndash'),
         b'\x97': ('--', 'mdash'),
         b'\x98': ('~', 'tilde'),
         b'\x99': ('(TM)', 'trade'),
         b'\x9a': ('s', 'scaron'),
         b'\x9b': ('>', 'gt'),
         b'\x9c': ('oe', 'oelig'),
         b'\x9d': '?',
         b'\x9e': 'z',
         b'\x9f': ('Y', 'Yuml'),
         b'\xa0': (' ', 'nbsp'),
         b'\xa1': ('!', 'iexcl'),
         b'\xa2': ('c', 'cent'),
         b'\xa3': ('GBP', 'pound'),
         b'\xa4': ('$', 'curren'),  # This approximation is especially lame.
         b'\xa5': ('YEN', 'yen'),
         b'\xa6': ('|', 'brvbar'),
         b'\xa7': ('S', 'sect'),
         b'\xa8': ('..', 'uml'),
         b'\xa9': ('', 'copy'),
         b'\xaa': ('(th)', 'ordf'),
         b'\xab': ('<<', 'laquo'),
         b'\xac': ('!', 'not'),
         b'\xad': (' ', 'shy'),
         b'\xae': ('(R)', 'reg'),
         b'\xaf': ('-', 'macr'),
         b'\xb0': ('o', 'deg'),
         b'\xb1': ('+-', 'plusmm'),
         b'\xb2': ('2', 'sup2'),
         b'\xb3': ('3', 'sup3'),
         b'\xb4': ("'", 'acute'),
         b'\xb5': ('u', 'micro'),
         b'\xb6': ('P', 'para'),
         b'\xb7': ('*', 'middot'),
         b'\xb8': (',', 'cedil'),
         b'\xb9': ('1', 'sup1'),
         b'\xba': ('(th)', 'ordm'),
         b'\xbb': ('>>', 'raquo'),
         b'\xbc': ('1/4', 'frac14'),
         b'\xbd': ('1/2', 'frac12'),
         b'\xbe': ('3/4', 'frac34'),
         b'\xbf': ('?', 'iquest'),
         b'\xc0': ('A', "Agrave"),
         b'\xc1': ('A', "Aacute"),
         b'\xc2': ('A', "Acirc"),
         b'\xc3': ('A', "Atilde"),
         b'\xc4': ('A', "Auml"),
         b'\xc5': ('A', "Aring"),
         b'\xc6': ('AE', "Aelig"),
         b'\xc7': ('C', "Ccedil"),
         b'\xc8': ('E', "Egrave"),
         b'\xc9': ('E', "Eacute"),
         b'\xca': ('E', "Ecirc"),
         b'\xcb': ('E', "Euml"),
         b'\xcc': ('I', "Igrave"),
         b'\xcd': ('I', "Iacute"),
         b'\xce': ('I', "Icirc"),
         b'\xcf': ('I', "Iuml"),
         b'\xd0': ('D', "Eth"),
         b'\xd1': ('N', "Ntilde"),
         b'\xd2': ('O', "Ograve"),
         b'\xd3': ('O', "Oacute"),
         b'\xd4': ('O', "Ocirc"),
         b'\xd5': ('O', "Otilde"),
         b'\xd6': ('O', "Ouml"),
         b'\xd7': ('*', "times"),
         b'\xd8': ('O', "Oslash"),
         b'\xd9': ('U', "Ugrave"),
         b'\xda': ('U', "Uacute"),
         b'\xdb': ('U', "Ucirc"),
         b'\xdc': ('U', "Uuml"),
         b'\xdd': ('Y', "Yacute"),
         b'\xde': ('b', "Thorn"),
         b'\xdf': ('B', "szlig"),
         b'\xe0': ('a', "agrave"),
         b'\xe1': ('a', "aacute"),
         b'\xe2': ('a', "acirc"),
         b'\xe3': ('a', "atilde"),
         b'\xe4': ('a', "auml"),
         b'\xe5': ('a', "aring"),
         b'\xe6': ('ae', "aelig"),
         b'\xe7': ('c', "ccedil"),
         b'\xe8': ('e', "egrave"),
         b'\xe9': ('e', "eacute"),
         b'\xea': ('e', "ecirc"),
         b'\xeb': ('e', "euml"),
         b'\xec': ('i', "igrave"),
         b'\xed': ('i', "iacute"),
         b'\xee': ('i', "icirc"),
         b'\xef': ('i', "iuml"),
         b'\xf0': ('o', "eth"),
         b'\xf1': ('n', "ntilde"),
         b'\xf2': ('o', "ograve"),
         b'\xf3': ('o', "oacute"),
         b'\xf4': ('o', "ocirc"),
         b'\xf5': ('o', "otilde"),
         b'\xf6': ('o', "ouml"),
         b'\xf7': ('/', "divide"),
         b'\xf8': ('o', "oslash"),
         b'\xf9': ('u', "ugrave"),
         b'\xfa': ('u', "uacute"),
         b'\xfb': ('u', "ucirc"),
         b'\xfc': ('u', "uuml"),
         b'\xfd': ('y', "yacute"),
         b'\xfe': ('b', "thorn"),
         b'\xff': ('y', "yuml"),
         }


def _makeRE(limit):
    """Returns a regular expression object that will match special characters
    up to the given limit."""
    return re.compile("([\x80-\\x%s])" % limit, re.M)
ALL = _makeRE('ff')
ONLY_WINDOWS = _makeRE('9f')


def _replHTML(match):
    "Replace the matched character with its HTML equivalent."
    return _repl(match, 1)


def _repl(match, html=0):
    "Replace the matched character with its HTML or ASCII equivalent."
    g = match.group(0)
    a = CHARS.get(g, g)
    if type(a) == types.TupleType:
        a = a[html]
        if html:
            a = '&' + a + ';'
    return a


def _dammit(t, html=0, fixWindowsOnly=0):
    "Turns ISO-Latin-1 into an ASCII representation, dammit."

    r = ALL
    if fixWindowsOnly:
        r = ONLY_WINDOWS
    m = _repl
    if html:
        m = _replHTML

    return re.sub(r, m, t)


def asciiDammit(t, fixWindowsOnly=0):
    "Turns ISO-Latin-1 into a plain ASCII approximation, dammit."
    return _dammit(t, 0, fixWindowsOnly)


def htmlDammit(t, fixWindowsOnly=0):
    "Turns ISO-Latin-1 into plain ASCII with HTML codes, dammit."
    return _dammit(t, 1, fixWindowsOnly=fixWindowsOnly)


def demoronise(t):
    """Helper method named in honor of the original smart quotes
    remover, The Demoroniser:

    http://www.fourmilab.ch/webtools/demoroniser/"""
    return asciiDammit(t, 1)

if __name__ == '__main__':

    french = b'\x93Sacr\xe9 bleu!\x93'
    print("First we mangle some French.")
    print(asciiDammit(french))
    print(htmlDammit(french))

    print()
    print("And now we fix the MS-quotes but leave the French alone.")
    print(demoronise(french))
    print(htmlDammit(french, 1))
