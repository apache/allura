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

// This logic is the same as the inline JS from the Lightbox widget
function startLightbox($lightbox) {
    $lightbox.lightbox_me();
    $lightbox.on('click', '.close', function (e) {
        e.preventDefault();
        $lightbox.trigger('close');
    });
    return $lightbox;
}

$(function() {
    $('body').on('click', 'a.admin_modal', function(e) {
        e.preventDefault();

        $('#lightbox_admin_modal').remove();
        $('body').append('<div id="lightbox_admin_modal" class="modal" style="display:none">  \
            <a class="icon close" href="#" title="Close"><i class="fa fa-close"></i></a>  \
            <h1 id="admin_modal_title"></h1><div id="admin_modal_contents">Loading...</div>  \
        </div>');

        startLightbox($('#lightbox_admin_modal'));

        var link = this;
        $.get(link.href, function(data) {
            var $popup_title = $('#admin_modal_title');
            var $popup_contents = $('#admin_modal_contents');
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
