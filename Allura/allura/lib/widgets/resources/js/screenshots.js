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
    var updateSortOrder = function (e) {
        var params = {'_session_id': $.cookie('_session_id')};
        $(e.to).find('.screenshot').each(function (i) {
            params[$(this).data('ss-id')] = i;
        });

        $.post('sort_screenshots', params)
            .done(function () {
                flash('New sort order saved.', 'success');
            })
            .fail(function () {
                flash('Sorting failed. Please refresh the page and try again.', 'error');
            });
    };

    var el = document.getElementsByClassName('sortable')[0];
    if (el) {
        var sortable = Sortable.create(el, {onUpdate: updateSortOrder,
                                            animation: 150,
                                            delay: 50,
                                            forceFallback: 1,
                                            filter: '.controls',
                                            preventOnFilter: false,
                                           });
    }

    $('.delete_screenshot_form').submit(function () {
        return confirm('Really delete this screenshot?');
    });
});

