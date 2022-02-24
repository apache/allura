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

from functools import wraps

from ming.orm import ThreadLocalORMSession

from allura.model.project import Project, Neighborhood, AppConfig
from allura.model.auth import User
from allura.model.discuss import Discussion, Thread, Post


def flush_on_return(fn):
    @wraps(fn)
    def new_fn(*args, **kwargs):
        result = fn(*args, **kwargs)
        ThreadLocalORMSession.flush_all()
        return result
    return new_fn


@flush_on_return
def create_project(shortname):
    neighborhood = create_neighborhood()
    return Project(shortname=shortname,
                   neighborhood_id=neighborhood._id,
                   is_root=True)


@flush_on_return
def create_neighborhood():
    neighborhood = Neighborhood(url_prefix='http://example.com/myproject')
    return neighborhood


@flush_on_return
def create_app_config(project, mount_point):
    return AppConfig(
        project_id=project._id,
        tool_name='myapp',
        options={
            'mount_point': 'my_mounted_app',
            'mount_label': 'My Mounted App',
        },
        acl=[])


@flush_on_return
def create_post(slug):
    discussion = create_discussion()
    thread = create_thread(discussion=discussion)
    author = create_user(username='someguy')
    return Post(slug=slug,
                thread_id=thread._id,
                full_slug=f'{thread._id}:{slug}',
                discussion_id=discussion._id,
                author_id=author._id)


@flush_on_return
def create_thread(discussion):
    return Thread.new(discussion_id=discussion._id)


@flush_on_return
def create_discussion():
    return Discussion()


@flush_on_return
def create_user(**kw):
    return User(**kw)
