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

""" ForgeDiscussion utilities. """

from bson import ObjectId
from tg import flash
from allura.lib import helpers as h
from allura.model import ProjectRole, ACE, ALL_PERMISSIONS, DENY_ALL, AuditLog
from forgediscussion import model as DM


def create_forum(app, new_forum):
    if 'parent' in new_forum and new_forum['parent']:
        parent_id = ObjectId(str(new_forum['parent']))
        shortname = (DM.Forum.query.get(_id=parent_id).shortname + '/'
                     + new_forum['shortname'])
    else:
        parent_id = None
        shortname = new_forum['shortname']
    description = new_forum.get('description', '')

    f = DM.Forum(app_config_id=app.config._id,
                 parent_id=parent_id,
                 name=h.really_unicode(new_forum['name']),
                 shortname=h.really_unicode(shortname),
                 description=h.really_unicode(description),
                 members_only=new_forum.get('members_only', False),
                 anon_posts=new_forum.get('anon_posts', False),
                 monitoring_email=new_forum.get('monitoring_email', None),
                 )
    AuditLog.log('created forum "{}" for {}'.format(
        f.name, app.config.options['mount_point']))
    if f.members_only and f.anon_posts:
        flash('You cannot have anonymous posts in a members only forum.',
              'warning')
        f.anon_posts = False
    if f.members_only:
        role_developer = ProjectRole.by_name('Developer')._id
        f.acl = [
            ACE.allow(role_developer, ALL_PERMISSIONS),
            DENY_ALL]
    elif f.anon_posts:
        role_anon = ProjectRole.anonymous()._id
        f.acl = [ACE.allow(role_anon, 'post')]
    else:
        f.acl = []
    return f
