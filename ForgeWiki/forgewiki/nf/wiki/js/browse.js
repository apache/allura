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

var show_deleted, can_delete;

function toggle_deleted(show) {
    if (show === void(0)) {
        show = !show_deleted;
    }
    show = !!show;

    var $rows       = $('#forge_wiki_browse tbody > tr'),
        num_deleted = $rows.filter('.deleted').toggle(show).length;

    if (can_delete && num_deleted) {
        $('#toggle_deleted span').text(show ? 'Hide' : 'Show');
        var suffix = show ? '&show_deleted=True' : '';
        $('#sort_recent').attr('href', '?sort=recent' + suffix);
        $('#sort_alpha').attr('href', '?sort=alpha' + suffix);
    }
    show_deleted = show;
    return num_deleted;
}

$(function () {
    var any_deleted = toggle_deleted(show_deleted);
    $('#toggle_deleted').click(function () {
        toggle_deleted();
        return false;
    }).toggle(!!any_deleted);
});
