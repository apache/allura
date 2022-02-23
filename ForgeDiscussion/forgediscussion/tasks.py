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

from tg import tmpl_context as c
from allura.lib.decorators import task

log = logging.getLogger(__name__)


@task
def calc_forum_stats(shortname):
    from forgediscussion import model as DM
    forum = DM.Forum.query.get(
        shortname=shortname, app_config_id=c.app.config._id)
    if forum is None:
        log.error("Error looking up forum: %r", shortname)
        return
    forum.update_stats()


@task
def calc_thread_stats(thread_id):
    from forgediscussion import model as DM
    thread = DM.ForumThread.query.get(_id=thread_id)
    if thread is None:
        log.error("Error looking up thread: %r", thread_id)
    thread.update_stats()
