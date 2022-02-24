#!/usr/bin/env python

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

import sys
from optparse import OptionParser

from tracwikiimporter.scripts.wiki_from_trac.extractors import WikiExporter


def parse_options():
    parser = OptionParser(
        usage='%prog <Trac URL>\n\nExport wiki pages from a trac instance')

    parser.add_option('-o', '--out-file', dest='out_filename',
                      help='Write to file (default stdout)')
    parser.add_option('-v', '--verbose', dest='verbose', action='store_true',
                      help='Verbose operation')
    parser.add_option('-c', '--converter', dest='converter',
                      default='html2text',
                      help='Converter to use on wiki text. '
                           'Available options: html2text (default) or regex')
    options, args = parser.parse_args()
    if len(args) != 1:
        parser.error('Wrong number of arguments.')
    converters = ['html2text', 'regex']
    if options.converter not in converters:
        parser.error('Wrong converter. Available options: ' +
                     ', '.join(converters))
    return options, args


if __name__ == '__main__':
    options, args = parse_options()
    exporter = WikiExporter(args[0], options)

    out = sys.stdout
    if options.out_filename:
        out = open(options.out_filename, 'w', encoding='utf-8')

    exporter.export(out)
