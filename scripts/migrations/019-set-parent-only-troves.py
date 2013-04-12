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

from tg import config

from ming.orm import ThreadLocalORMSession

import sfx
from allura import model as M
from allura.lib import helpers as h
from sfx.model import tables as T

log = logging.getLogger(__name__)

def main():
    sfx.middleware.configure_databases(h.config_with_prefix(config, 'sfx.'))
    parent_only_troves = T.trove_cat.select(T.trove_cat.c.parent_only==1).execute()
    parent_only_ids = [t.trove_cat_id for t in parent_only_troves]
    allura_troves = M.TroveCategory.query.find(dict(
        trove_cat_id={'$in': parent_only_ids})).all()
    print 'Found %s parent-only troves in alexandria.' % len(parent_only_ids)
    print 'Setting parent-only Allura troves...'
    for t in allura_troves:
        print ' %s: %s' % (t.trove_cat_id, t.fullpath)
        t.parent_only = True
    print 'Updated %s Allura troves.' % len(allura_troves)
    ThreadLocalORMSession.flush_all()

if __name__ == '__main__':
    main()
