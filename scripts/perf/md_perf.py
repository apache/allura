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

"""
A script for timing/profiling the Markdown conversion of an artifact discussion thread.

Example usage:

(env-allura)root@h1v1024:/var/local/allura/Allura(master)$ time paster script production.ini allura/scripts/md_perf.py -- --converter=forge
      Conversion Time (s)  Text Size Post._id
   1 0.021863937377929688         20 7d3ce86bb2c3afaee21f28547ed542d0c8c483b8
   2 0.002238035202026367         12 96b1283c6db619cd66ee092551758dc1ad5b958f
   3 0.001832962036132812          9 42c44cd72815d29069378353745bef953bdb2b98
   4 0.011796951293945312        901 cadbea52291c58bb190597c1df94527369b405fa
   5 0.143218040466308594      11018 362bee7ef1ba4e062712bda22cb96ae9fe459b95
   6 0.029596090316772461       1481 46b78785b849f55d24cf32ee1f4e4c916cb7a6fe
   7 0.045151948928833008       4144 4e2f62188080baba9b88c045ba1f7c26903bfcf9
   8 0.637056827545166016      14553 51c87f2b1d55c08147bb2353e20361236232b432
   9 4.510329008102416992      23016 f298ad88584f3dc9b5c37ffde61391bf03d5bae6
  10 3.614714860916137695      23016 8775a230b19c231daa1608bb4cea1e17aab54550
  11 0.393079042434692383      19386 ed79e0d2f89366043a007e0837e98945453508c9
  12 0.000739097595214844      43659 56ac2437ec1bd886a03d23e45aa1c947729760ec
  13 0.258469104766845703       8520 57152cefe0424b7fc9dff7ab4d21a6ef6e90bf82
  14 0.264052867889404297       8518 6788b13c90c9719ba46196a0a773f4c228df9f2a
  15 0.995774984359741211      14553 3f5cce06d2400bcd56d7b90d12c569935f0099a4
Total time: 10.930670023

real    0m14.256s
user    0m12.749s
sys     0m1.112s

"""

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import
import argparse
import cProfile
import time

try:
    import re2
    re2.set_fallback_notification(re2.FALLBACK_WARNING)
    RE2_INSTALLED = True
except ImportError:
    RE2_INSTALLED = False

from tg import app_globals as g

MAX_OUTPUT = 99999
DUMMYTEXT = None


def get_artifact():
    from forgeblog import model as BM
    return BM.BlogPost.query.get(
        slug='2013/09/watch-breaking-bad-season-5-episode-16-felina-live-streaming')


def main(opts):
    import markdown
    if opts.re2 and RE2_INSTALLED:
        markdown.inlinepatterns.re = re2
    converters = {
        'markdown': lambda: markdown.Markdown(),
        'markdown_safe': lambda: markdown.Markdown(safe_mode=True),
        'markdown_escape': lambda: markdown.Markdown(safe_mode='escape'),
        'forge': lambda: g.markdown,
    }
    md = converters[opts.converter]()
    artifact = get_artifact()
    return render(artifact, md, opts)


def render(artifact, md, opts):
    start = begin = time.time()
    print("%4s %20s %10s %s" % ('', 'Conversion Time (s)', 'Text Size', 'Post._id'))
    for i, p in enumerate(artifact.discussion_thread.posts):
        text = DUMMYTEXT or p.text
        if opts.n and i + 1 not in opts.n:
            print('Skipping post %s' % str(i + 1))
            continue
        if opts.profile:
            print('Profiling post %s' % str(i + 1))
            cProfile.runctx('output = md.convert(text)', globals(), locals())
        else:
            output = md.convert(text)
        elapsed = time.time() - start
        print("%4s %1.18f %10s %s" % (i + 1, elapsed, len(text), p._id))
        if opts.output:
            print('Input:', text[:min(300, len(text))])
            print('Output:', output[:min(MAX_OUTPUT, len(output))])
        start = time.time()
    print("Total time:", start - begin)
    return output


def parse_options():
    parser = argparse.ArgumentParser()
    parser.add_argument('--converter', default='markdown')
    parser.add_argument('--profile', action='store_true',
                        help='Run profiler and output timings')
    parser.add_argument('--output', action='store_true',
                        help='Print result of markdown conversion')
    parser.add_argument('--re2', action='store_true',
                        help='Run with re2 instead of re')
    parser.add_argument('--compare', action='store_true',
                        help='Run with re and re2, and compare results')
    parser.add_argument('-n', '--n', nargs='+', type=int,
                        help='Only convert nth post(s) in thread')
    return parser.parse_args()


if __name__ == '__main__':
    opts = parse_options()
    out1 = main(opts)
    if opts.compare:
        opts.re2 = not opts.re2
        out2 = main(opts)
        print('re/re2 outputs match: ', out1 == out2)
