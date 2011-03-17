#!/usr/bin/env python
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
SIZE = 10 * (2**10)
EMAIL_TEXT = 'X' * SIZE

def main():
    threads = [ threading.Thread(target=stress) for x in xrange(C) ]
    begin = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    end = time.time()
    elapsed = end - begin
    print '%d requests completed in %f seconds' % (N, elapsed)
    print '%f requests/second' % (N/elapsed)

def stress():
    server = smtplib.SMTP(SERVER, PORT)
    for x in xrange(N/C):
        server.sendmail('sstress@localhost', TOADDR, EMAIL_TEXT)

if __name__ == '__main__':
    main()
