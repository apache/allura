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

import logging
import csv
from sys import getsizeof

import ipaddress
from tg import request

from allura.lib import utils
from allura.lib.spam import SpamFilter
import six

log = logging.getLogger(__name__)


class StopForumSpamSpamFilter(SpamFilter):
    """Spam checking by IP address, using StopForumSpam data files

    To enable StopForumSpam spam filtering in your Allura instance,
    include the following parameters in your .ini file::

        spam.method = stopforumspam
        spam.stopforumspam.ip_addr_file = /path/to/listed_ip_180_all.txt

    Of course you'll need to download the file from https://www.stopforumspam.com/downloads and do so on a regular
    basis to keep it updated.
    """

    def __init__(self, config):
        self.packed_ips = set()
        threshold = int(config.get('spam.stopforumspam.threshold', 20))
        threshold_strs = {str(i) for i in range(threshold+1)}  # make strs, so that in the loop no int cast needed
        with open(config['spam.stopforumspam.ip_addr_file']) as f:
            csv_file = csv.reader(f)
            for record in csv_file:
                if record[1] not in threshold_strs:
                    ip = record[0]
                    # int is the smallest memory representation of an IP addr
                    ip_int = int(ipaddress.ip_address(str(ip)))
                    self.packed_ips.add(ip_int)
        # to get actual memory usage, use: from pympler.asizeof import asizeof
        log.info('Read stopforumspam file; %s recs, probably %s bytes stored in memory', len(self.packed_ips),
                 len(self.packed_ips) * getsizeof(next(iter(self.packed_ips))) * 2)

    def check(self, text, artifact=None, user=None, content_type='comment', **kw):
        ip = utils.ip_address(request)
        if ip:
            ip_int = int(ipaddress.ip_address(str(ip)))
            res = ip_int in self.packed_ips
            self.record_result(res, artifact, user)
        else:
            res = False
        return res
