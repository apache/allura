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


from allura.lib.utils import permanent_redirect
from tg import expose, redirect
from tg.decorators import with_trailing_slash
from tg import tmpl_context as c

from allura.controllers import repository


class BranchBrowser(repository.BranchBrowser):

    @expose('jinja:forgegit:templates/git/index.html')
    @with_trailing_slash
    def index(self, limit=None, page=0, count=0, **kw):
        is_empty = c.app.repo.is_empty()
        latest = c.app.repo.latest(branch=self._branch)
        if is_empty or not latest:
            return dict(allow_fork=False, log=[], is_empty=is_empty)
        permanent_redirect(c.app.repo.url_for_commit(self._branch) + 'tree/')
