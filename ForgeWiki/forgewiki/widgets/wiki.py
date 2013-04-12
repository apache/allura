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

import ew.jinja2_ew as ew
from allura.lib.widgets import form_fields as ffw

class CreatePageWidget(ffw.Lightbox):

    def resources(self):
        for r in super(CreatePageWidget, self).resources(): yield r
        yield ew.JSScript('''$(function () {
            $('#lightbox_create_wiki_page form').submit(function(){
                location.href = $('#sidebar a.add_wiki_page').attr('href') +
                    encodeURIComponent($('input[name=name]', $(this)).val().replace('/', '-')) + '/edit';
                return false;
            });
        });''');
