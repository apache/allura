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


from allura.tests import TestController


class TestStaticFilesMiddleware(TestController):

    # this tests StaticFilesMiddleware
    # the URLs are /nf/_static_/... because test.ini has:
    #   static.script_name = /nf/_static_/

    def test_static_controller(self):
        # package directory
        self.app.get('/nf/_static_/wiki/js/browse.js')
        self.app.get('/nf/_static_/wiki/js/no_such_file.js', status=404)
        self.app.get('/nf/_static_/no_such_tool/js/comments.js', status=404)
        # main allura resource
        self.app.get('/nf/_static_/images/user.png')

    def test_path_traversal(self):
        # package directory
        self.app.get('/nf/_static_/wiki/../../../setup.py', status=404)
        self.app.get('/nf/_static_/wiki/..%2F..%2F..%2Fsetup.py', status=404)
        self.app.get('/nf/_static_/wiki/.%2E/.%2E/.%2E/setup.py', status=404)
        # main allura resource
        self.app.get('/nf/_static_/../../../setup.py', status=404)
