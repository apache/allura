/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/
$(function() {
    var $popup_title = $('#admin_modal_title');
    var $popup_contents = $('#admin_modal_contents');
    $('a.admin_modal').click(function () {
        var link = this;
        $popup_title.html('');
        $popup_contents.html('Loading...');
        $.get(link.href, function (data) {
            $popup_title.html($(link).html());
            $popup_contents.html(data);
            var csrf_exists = $popup_contents.find('form > input[name="_session_id"]').length;
            if (!csrf_exists) {
              var cval = $.cookie('_session_id');
              var csrf_input = $('<input name="_session_id" type="hidden" value="'+cval+'">');
              $popup_contents.find('form').append(csrf_input);
            }
        });
    });
});
