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

'''
sstress - an SMTP stress testing tool
'''

import smtplib
import threading
import time

C = 5
N = 1000
TOADDR = 'nobody@localhost'
SERVER = 'localhost'
PORT = 8825
SIZE = 10 * (2 ** 10)
EMAIL_TEXT = 'X' * SIZE


def main():
    threads = [threading.Thread(target=stress) for x in range(C)]
    begin = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    end = time.time()
    elapsed = end - begin
    print('%d requests completed in %f seconds' % (N, elapsed))
    print('%f requests/second' % (N / elapsed))


def stress():
    server = smtplib.SMTP(SERVER, PORT)
    for x in range(N / C):
        server.sendmail('sstress@localhost', TOADDR, EMAIL_TEXT)

if __name__ == '__main__':
    main()
