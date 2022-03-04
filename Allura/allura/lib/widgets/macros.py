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

import ew


class Include(ew.Widget):
    template = 'jinja:allura:templates/widgets/include.html'
    params = ['artifact', 'attrs']
    artifact = None
    attrs = {
        'style': 'width:270px;float:right;background-color:#ccc'
    }


class NeighborhoodFeeds(ew.Widget):
    template = 'jinja:allura:templates/macro/neighborhood_feeds.html'
    params = ['feeds']
    feeds = None


class BlogPosts(ew.Widget):
    template = 'jinja:allura:templates/macro/blog_posts.html'
    params = ['posts']
    posts = None


class ProjectAdmins(ew.Widget):
    template = 'jinja:allura:templates/macro/project_admins.html'
    params = ['users']
    users = None


class Members(ew.Widget):
    template = 'jinja:allura:templates/macro/members.html'
    params = ['users', 'over_limit']
    users = None
    over_limit = None
