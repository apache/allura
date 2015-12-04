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

(function() {

    // sorting
    $('#sortable').sortable({items: ".fleft:not(.isnt_sorted)"}).bind( "sortupdate", function (e) {
        var sortables = $('#sortable .fleft');
        var tools = 0;
        var subs = 0;
        var params = {'_session_id':$.cookie('_session_id')};
        var action = $('#install_form').attr('action');
        var limit = action.match(/limit=(\d+)/)[1];
        var page = action.match(/page=(\d+)/)[1];
        var first_tool_ordinal = parseInt(limit) * parseInt(page);
        for (var i = 0, len = sortables.length; i < len; i++) {
            var item = $(sortables[i]);
            var mount_point = item.find('input.mount_point');
            var shortname = item.find('input.shortname');
            if (mount_point.length) {
                params['tools-' + tools + '.mount_point'] = mount_point.val();
                params['tools-' + tools + '.ordinal'] = i + first_tool_ordinal;
                tools++;
            }
            if (shortname.length) {
                params['subs-' + subs + '.shortname'] = shortname.val();
                params['subs-' + subs + '.ordinal'] = i + first_tool_ordinal;
                subs++;
            }
        }
        $.ajax({
            type: 'POST',
            url: 'update_mount_order',
            data: params,
            success: function(xhr, textStatus, errorThrown) {
                $('#messages').notify('Tool order updated, refresh this page to see the updated project navigation.',
                                      {status: 'confirm'});
            },
            error: function(xhr, textStatus, errorThrown) {
                $('#messages').notify('Error saving tool order.',
                                      {status: 'error'});
            }
        });
    });
    // fix firefox scroll offset bug
    var userAgent = navigator.userAgent.toLowerCase();
    if(userAgent.match(/firefox/)) {
      $('#sortable').bind( "sortstart", function (event, ui) {
        ui.helper.css('margin-top', $(window).scrollTop() );
      });
      $('#sortable').bind( "sortbeforestop", function (event, ui) {
        ui.helper.css('margin-top', 0 );
      });
    }
})();
