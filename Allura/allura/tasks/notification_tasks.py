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

from allura.lib.decorators import task
from allura.lib import utils
from tg import tmpl_context as c

@task
def notify(n_id, ref_ids, topic):
    from allura import model as M
    M.Mailbox.deliver(n_id, ref_ids, topic)
    M.Mailbox.fire_ready()

@task
def send_usermentions_notification(artifact_id, text, old_text=None):
    from allura import model as M
    artifact = M.ArtifactReference.query.get(_id=artifact_id).artifact
    usernames = utils.get_usernames_from_md(text)
    if old_text:
        old_usernames = utils.get_usernames_from_md(old_text)
        usernames -= old_usernames

    for username in list(usernames):
        u = M.User.by_username(username)
        if u.get_pref('mention_notifications'):
            u.send_user_mention_notification(c.user, artifact)
